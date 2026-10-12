"""Ingest and run steps, wired together. Each step falls back to synthetic data if a live source fails."""

from __future__ import annotations

import json
import logging
from datetime import timedelta

import pandas as pd

from psycopg.types.json import Jsonb

from . import agent, alerts, attribution, audit, backtest as bt, db, dust_score, fill, forecast, windows
from . import verify as verify_mod
from .config import Settings, load_seed
from .sources import cams, openaq, openmeteo, overpass, synthetic

log = logging.getLogger("dusttrace")

# Real readings older than this can't anchor a forecast for the next 48 h; synthetic samples stand in.
FRESH_HOURS = 6


def now_hour() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC").floor("h")


def ingest(conn, settings: Settings, mode: str = "auto", days: int = 120) -> dict:
    """Load weather (history + 3-day forecast) and station readings. Returns what was loaded and how."""
    seed = load_seed()
    ward = seed["ward"]
    now = now_hour()
    report = {"weather": None, "readings": None}

    # Weather
    wx, wx_live, gap = None, False, None
    if mode in ("auto", "live"):
        try:
            past = min(days, 92)
            wx = openmeteo.fetch_forecast(ward["center_lat"], ward["center_lon"], past_days=past, forecast_days=3)
            wx_live = not wx.empty
        except Exception as e:  # network blocked, API down, etc.
            if mode == "live":
                raise
            log.warning("Open-Meteo unavailable (%s); using synthetic weather", e)
        if wx_live and days > 92:
            start = (now - timedelta(days=days)).date()
            end = (now - timedelta(days=90)).date()
            try:
                hist = openmeteo.fetch_archive(ward["center_lat"], ward["center_lon"], start, end)
                wx = pd.concat([hist, wx]).drop_duplicates("ts", keep="last").sort_values("ts")
            except Exception as e:  # keep the live recent weather; only the older history is synthetic
                if mode == "live":
                    raise
                log.warning("Open-Meteo archive unavailable (%s); weather before %s is synthetic", e, wx["ts"].min())
                gap = synthetic.weather(now - timedelta(days=days), wx["ts"].min() - timedelta(hours=1))
    if not wx_live:
        wx = synthetic.weather(now - timedelta(days=days), now + timedelta(hours=72))
    n = db.write_weather(conn, ward["id"], wx, now, synthetic=not wx_live)
    if gap is not None:
        n += db.write_weather(conn, ward["id"], gap, now, synthetic=True)
        wx = pd.concat([gap, wx]).sort_values("ts")
    report["weather"] = {"rows": n, "live": wx_live, "history_live": wx_live and gap is None}

    # Readings
    rd_live = False
    total = 0
    latest = None  # newest real PM10 hour
    if mode in ("auto", "live") and settings.openaq_api_key:
        try:
            stations = openaq.find_stations(settings.openaq_api_key, _expand(ward["bbox"], 0.04),
                                            active_since=(now - timedelta(days=30)).to_pydatetime())
            log.info("OpenAQ: %d PM stations near the ward reported in the last 30 days", len(stations))
            for st in stations:
                try:  # one bad station shouldn't cost us the others
                    frames = {}
                    for param, sensor_id in st["sensors"].items():
                        df = openaq.fetch_sensor_hours(settings.openaq_api_key, sensor_id,
                                                       (now - timedelta(days=days)).to_pydatetime(), now.to_pydatetime())
                        frames[param] = df.set_index("ts")["value"]
                except Exception as e:
                    log.warning("OpenAQ station %s skipped (%s)", st["id"], e)
                    continue
                merged = pd.DataFrame({"pm10": frames.get("pm10"), "pm25": frames.get("pm25")})
                merged = merged.reset_index().rename(columns={"index": "ts"})
                if merged.empty:
                    continue
                merged["station_id"] = st["id"]
                db.upsert_station(conn, {**st, "source": "openaq"}, ward["id"])
                total += db.write_readings(conn, merged, synthetic=False)
                last = merged.loc[merged["pm10"].notna(), "ts"].max()
                if pd.notna(last) and (latest is None or last > latest):
                    latest = last
            rd_live = latest is not None and now - latest <= timedelta(hours=FRESH_HOURS)
            if total and not rd_live:
                log.warning("OpenAQ PM10 is stale (newest %s); synthetic readings anchor this run", latest)
        except Exception as e:
            if mode == "live":
                raise
            log.warning("OpenAQ unavailable (%s); using synthetic readings", e)
    elif mode == "live":
        raise RuntimeError("OPENAQ_API_KEY is required for live readings")
    if mode in ("auto", "live"):
        try:
            report["cams"] = ingest_cams(conn, ward["id"], now, max(days, 70))
        except Exception as e:  # CAMS is only a fallback; never fail the run for it
            log.warning("CAMS unavailable (%s)", e)
            report["cams"] = {"rows": 0, "error": str(e)[:200]}

    n_synthetic = 0
    if not rd_live and mode != "live":
        hist_wx = wx[wx["ts"] <= now]
        ids = [s["id"] for s in seed["stations"]]
        n_synthetic = db.write_readings(conn, synthetic.readings(hist_wx, ids), synthetic=True)
    report["readings"] = {"rows": total, "synthetic_rows": n_synthetic, "live": rd_live,
                          "newest_live": latest.isoformat() if latest is not None else None}
    return report


def ingest_cams(conn, ward_id: str, now: pd.Timestamp, days: int) -> dict:
    """CAMS PM at every real station's position, `days` back to 3 days ahead (issue #28)."""
    st = db.read_frame(conn, "select id, lat, lon from stations where ward_id=%s and source='openaq'", (ward_id,))
    if st.empty:
        return {"rows": 0, "stations": 0}
    stations = [{"id": r.id, "lat": float(r.lat), "lon": float(r.lon)} for r in st.itertuples()]
    df = cams.fetch(stations, (now - timedelta(days=days)).date().isoformat(), (now + timedelta(days=3)).date().isoformat())
    n = db.write_cams(conn, df)
    conn.commit()
    return {"rows": n, "stations": len(stations)}


def receptor_bbox(ward_bbox: list[float], margin_deg: float = 0.01) -> list[float]:
    """Ward bbox plus about 1 km, so plumes that cross the ward boundary still find receptors."""
    return _expand(ward_bbox, margin_deg)


def load_receptors_osm(conn, settings: Settings) -> int:
    seed = load_seed()
    recs = overpass.fetch(receptor_bbox(seed["ward"]["bbox"]))
    db.upsert_receptors(conn, recs, seed["ward"]["id"])
    conn.commit()
    return len(recs)


def load_sites_osm(conn, settings: Settings) -> int:
    """Construction sites mapped in OpenStreetMap inside the ward (issue #30). Real, not demo."""
    seed = load_seed()
    sites = overpass.fetch_sites(seed["ward"]["bbox"])
    db.upsert_sites(conn, sites, seed["ward"]["id"])
    conn.commit()
    return len(sites)


def run(conn, settings: Settings) -> dict:
    """Train, forecast 48 h, model plumes and issue Safe-Work Windows. Writes one `runs` row."""
    ward_id = settings.ward_id
    wx = db.read_frame(conn, "select ts, wind_speed, wind_dir, blh, temp, rh, precip, synthetic from weather_hourly where ward_id=%s order by ts", (ward_id,))
    rd = db.read_frame(conn, """select r.station_id, r.ts, r.pm10, r.synthetic from readings r
                                join stations s on s.id = r.station_id where s.ward_id=%s order by r.ts""", (ward_id,))
    if wx.empty or rd.empty:
        raise RuntimeError("No weather or readings yet. Run `dusttrace ingest` first.")
    for c in ["wind_speed", "wind_dir", "blh", "temp", "rh", "precip"]:
        wx[c] = wx[c].astype(float)
    rd["pm10"] = rd["pm10"].astype(float)
    wx["ts"] = pd.to_datetime(wx["ts"], utc=True)
    rd["ts"] = pd.to_datetime(rd["ts"], utc=True)

    real_ts = rd.loc[~rd["synthetic"].astype(bool) & rd["pm10"].notna(), "ts"]
    newest_real = real_ts.max().isoformat() if len(real_ts) else None  # shown when the live feed lags
    rd["filled"] = False
    filled, fill_info = fill_from_cams(conn, ward_id, rd, now_hour())
    if not filled.empty:
        rd = pd.concat([rd, filled], ignore_index=True)
    t0, active = anchor(rd, now_hour())
    rd = rd[rd["station_id"].isin(active)]

    # Train on measured hours only; filled hours only let the forecast start from now.
    train_rd = rd[~rd["filled"].astype(bool)]
    model = forecast.train(train_rd[["station_id", "ts", "pm10"]], wx, settings.horizon_hours, settings.exceed_threshold)
    fc = forecast.predict(model, rd[["station_id", "ts", "pm10"]], wx, t0, settings.horizon_hours)

    data_mode = _mode(wx["synthetic"].any(), wx["synthetic"].all(), rd["synthetic"].any(), rd["synthetic"].all())
    if data_mode == "live" and rd["filled"].astype(bool).any():
        data_mode = "filled"  # real stations, recent hours from corrected CAMS
    audits, bench, hot = audit_sensors(conn, ward_id, rd, wx, t0)
    used = rd[rd["filled"].astype(bool)]
    fill_info["stations"] = int(used["station_id"].nunique())
    fill_info["hours"] = int(used.groupby("station_id").size().max()) if len(used) else 0
    metrics = {**model.metrics, "stations": list(active), "audit": bench, "newest_real_reading": newest_real,
               "filled": fill_info, "inputs": verify_mod.input_shares(rd, t0)}
    run_id = db.create_run(conn, ward_id, t0.to_pydatetime(), data_mode, "lightgbm-direct-v1", metrics)
    db.write_forecasts(conn, run_id, fc)
    db.write_audits(conn, run_id, audits)

    ward_fc = fc[fc["station_id"] == "ward"].set_index("ts")["p_exceed"]
    future = wx[(wx["ts"] > t0) & (wx["ts"] <= t0 + pd.Timedelta(hours=settings.horizon_hours))]
    sites = db.read_sites(conn, ward_id)
    recs = db.read_receptors(conn, ward_id)
    for c in ["lat", "lon"]:
        recs[c] = recs[c].astype(float)
    hours = windows.evaluate(sites, recs, future, ward_fc, settings)
    db.write_site_hours(conn, run_id, hours)
    ranked = rank_sites(conn, ward_id, sites, list(active), future, ward_fc, audits)
    db.write_ranking(conn, run_id, ranked)
    known = sites.set_index("id")["sensor_known"].to_dict()
    db.write_dust_scores(conn, run_id, score_sites(conn, ward_id, ranked, audits, known))
    states = respond(conn, ward_id, run_id, now_hour(), hours, recs, ward_fc, audits, hot, sites)
    db.write_alerts(conn, run_id, alerts.derive(states))
    conn.commit()

    counts = pd.Series([h.status for h in hours]).value_counts().to_dict()
    return {"run_id": run_id, "issued_at": t0.isoformat(), "data_mode": data_mode,
            "metrics": metrics, "window_counts": counts, "stations": list(active),
            "sensor_trust": {a.site_id: a.score for a in audits}}


def rank_sites(conn, ward_id: str, sites: pd.DataFrame, station_ids: list[str], future: pd.DataFrame,
               ward_p: pd.Series, audits) -> list:
    """The ranked inspection list (F4) for the next 24 h of the forecast."""
    st = db.read_frame(conn, "select id, name, lat, lon from stations where id = any(%s)", (station_ids,))
    stations = [{"id": r.id, "name": r.name, "lat": float(r.lat), "lon": float(r.lon)} for r in st.itertuples()]
    site_list = [{"id": r.id, "name": r.name, "lat": r.lat, "lon": r.lon,
                  "sensor_known": bool(getattr(r, "sensor_known", True))} for r in sites.itertuples()]
    up = attribution.upwind_details(site_list, stations, future.head(24), ward_p)
    trust = {a.site_id: a.score for a in audits}
    signals = db.site_signals(conn, ward_id)
    rows = [{"site_id": s["id"], "name": s["name"], "upwind": up[s["id"]]["exposure"],
             "upwind_station": up[s["id"]]["station"], "upwind_hours": up[s["id"]]["hours"],
             "trust": trust.get(s["id"]), "has_sensor": s["id"] in trust, "sensor_known": s["sensor_known"],
             "reports": signals.get(s["id"], {}).get("reports", 0),
             "violations": signals.get(s["id"], {}).get("violations", 0)} for s in site_list]
    return attribution.rank(rows)


def score_sites(conn, ward_id: str, ranked, audits, sensor_known: dict | None = None) -> dict:
    """Dust Score (F8) per site. Windows followed comes from accepted site-manager plans (F7)."""
    trust = {a.site_id: a.score for a in audits}
    signals = db.site_signals(conn, ward_id)
    followed = db.windows_followed(conn, ward_id)
    out = {}
    for r in ranked:
        sig = signals.get(r.site_id, {})
        hours = int(r.upwind_hours or 0)
        out[r.site_id] = dust_score.compute(
            trust=trust.get(r.site_id), has_sensor=r.site_id in trust, spike_hours=hours,
            windows_followed=followed.get(r.site_id), verified_reports=sig.get("verified_reports", 0),
            violations=sig.get("violations_90d", 0),
            sensor_known=bool((sensor_known or {}).get(r.site_id, True)))
    return out


def audit_sensors(conn, ward_id: str, rd: pd.DataFrame, wx: pd.DataFrame, t0: pd.Timestamp):
    """Simulate each site's sensor from the ambient series, store the readings, and score them (F1).

    Also scores a 50-sensor benchmark with known faults, so each run reports the audit's precision
    and recall under the current weather.
    """
    specs = [audit.SensorSpec(r.sensor_id, r.site_id, float(r.lat), float(r.lon), float(r.area_m2),
                              r.activity, r.fault) for r in db.read_sensor_specs(conn, ward_id).itertuples()]
    ambient = rd.groupby("ts")["pm10"].mean()
    sim = audit.simulate(specs, ambient, wx, t0)
    db.write_site_readings(conn, sim)
    results = [audit.score(s, sim, ambient, wx, t0) for s in specs]
    by_site = {s.sensor_id: s.site_id for s in specs}
    hot = {by_site[k]: v for k, v in audit.hot_hours(sim, ambient, t0).items()}
    return results, audit.benchmark(ambient, wx, t0), hot


def respond(conn, ward_id: str, run_id: int, now: pd.Timestamp, hours, recs: pd.DataFrame,
            ward_p: pd.Series, audits, hot: dict, run_sites: pd.DataFrame | None = None) -> dict:
    """Dust Response Agent (F12): build each site's context from this run, let the policy engine
    decide, and update the site's open case. Returns each site's state for the ward alerts (F11)."""
    names = recs.set_index("id")["name"].to_dict()
    kinds = recs.set_index("id")["kind"].to_dict()
    sites = db.read_frame(conn, """select s.id, s.name, s.activity, n.id is not null as has_sensor,
                                          coalesce(n.has_relay, false) as has_relay
                                     from sites s left join site_sensors n on n.site_id = s.id
                                    where s.ward_id=%s order by s.id""", (ward_id,))
    if run_sites is not None:  # the sites this run covers (demo ones may be switched off)
        known = run_sites.set_index("id")["sensor_known"].to_dict()
        sites = sites[sites["id"].isin(known)]
    else:
        known = {}
    trust = {a.site_id: a.score for a in audits}
    signals = db.site_signals(conn, ward_id)
    accepted = db.plans_accepted_today(conn, ward_id)
    states = []
    for s in sites.itertuples():
        # Only hours when dusty work is allowed (06:00-22:00 IST) can need a site to act.
        mine = [h for h in hours if h.site_id == s.id and 6 <= plume_hour(h.ts) < 22]
        spikes = [h for h in mine if float(ward_p.get(h.ts, 0.0)) >= 0.6 and h.exposures]
        ctx = agent.SiteContext(
            site_id=s.id, name=s.name, activity=s.activity, has_sensor=bool(s.has_sensor),
            has_relay=bool(s.has_relay), trust=trust.get(s.id), now=now,
            sensor_known=bool(known.get(s.id, True)),
            spike_hours=[h.ts for h in spikes],
            spike_receptors=_unique(names[r] for h in spikes for r, _ in h.exposures),
            sensitive_avoid=_unique_pairs((h.ts, names[r]) for h in mine if h.status == "avoid" and h.sensitive_hit
                                          for r, c in h.exposures if kinds.get(r) in ("school", "hospital")),
            sensor_hot_hours=hot.get(s.id, 0),
            pending_requests=db.pending_requests(conn, s.id),
            citizen_reports=signals.get(s.id, {}).get("reports", 0),
            confirmed_violation=signals.get(s.id, {}).get("confirmed_violation", False),
            satellite_active=signals.get(s.id, {}).get("satellite", False),
        )
        decision = agent.decide(ctx)
        case_id = db.write_case(conn, run_id, s.id, decision)
        first = min((h for h in hours if h.site_id == s.id), key=lambda h: h.ts, default=None)
        states.append(alerts.SiteState(ctx, decision, case_id, s.id in accepted,
                                       avoid_now=first is not None and first.status == "avoid"))
    return states


FILL_MAX_STALE = pd.Timedelta(days=30)  # a station silent for longer is treated as closed, not filled


def verify(conn, settings: Settings) -> dict:
    """Data check (issue #29) for the latest run: freshness per source, the real/filled/synthetic
    split, and the CAMS fill's error on a hold-out month. Stores one `data_checks` row."""
    ward_id = settings.ward_id
    run = conn.execute("select id, issued_at, metrics from runs where ward_id=%s order by id desc limit 1",
                       (ward_id,)).fetchone()
    if not run:
        raise RuntimeError("No run yet. Run `dusttrace run` first.")
    run_id, issued, metrics = run[0], pd.Timestamp(run[1]), run[2] or {}
    now = now_hour()

    newest = dict(conn.execute("""select s.id, max(r.ts) from stations s
                                    left join readings r on r.station_id = s.id and not r.synthetic and r.pm10 is not null
                                   where s.ward_id=%s and s.source <> 'seed' group by s.id""", (ward_id,)).fetchall())
    stations = verify_mod.station_freshness(newest, now)

    cams = {}
    cm = db.read_frame(conn, """select c.station_id, c.ts, c.pm10 from cams_hourly c join stations s on s.id = c.station_id
                                 where s.ward_id=%s and c.pm10 is not null""", (ward_id,))
    if not cm.empty:
        ob = db.read_frame(conn, """select r.station_id, r.ts, r.pm10 from readings r join stations s on s.id = r.station_id
                                     where s.ward_id=%s and not r.synthetic and r.pm10 is not null
                                       and r.ts > now() - interval '120 days'""", (ward_id,))
        for f in (cm, ob):
            f["ts"] = pd.to_datetime(f["ts"], utc=True)
            f["pm10"] = f["pm10"].astype(float)
        for sid, o in ob.groupby("station_id"):
            h = verify_mod.cams_holdout(o.set_index("ts")["pm10"], cm[cm["station_id"] == sid].set_index("ts")["pm10"])
            if h:
                cams[sid] = h

    horizon = conn.execute("""select count(*), count(*) filter (where not synthetic) from weather_hourly
                               where ward_id=%s and ts > %s and ts <= %s""",
                           (ward_id, issued, issued + pd.Timedelta(hours=settings.horizon_hours))).fetchone()
    weather_live = round(horizon[1] / horizon[0], 4) if horizon[0] else 0.0
    receptors_osm = conn.execute("select count(*) from receptors where ward_id=%s and source='osm'", (ward_id,)).fetchone()[0]
    sites_real = conn.execute("select count(*) from sites where ward_id=%s and not demo", (ward_id,)).fetchone()[0]
    scene = conn.execute("select max(scene_after), max(found_at) from site_candidates where ward_id=%s", (ward_id,)).fetchone()
    shares = metrics.get("inputs") or {"hours": 0, "real": 0.0, "filled": 0.0, "synthetic": 0.0}
    probs = verify_mod.problems(stations, shares, weather_live, receptors_osm, sites_real)
    sources = {"weather_live": weather_live, "receptors_osm": int(receptors_osm), "sites_real": int(sites_real),
               "satellite_scene": scene[0], "satellite_found_at": scene[1].isoformat() if scene[1] else None,
               "run_issued_at": issued.isoformat(), "data_mode": None}
    sources["data_mode"] = conn.execute("select data_mode from runs where id=%s", (run_id,)).fetchone()[0]
    ok = not probs
    conn.execute("""insert into data_checks (ward_id, run_id, ok, shares, stations, cams, sources, problems)
                    values (%s,%s,%s,%s,%s,%s,%s,%s)""",
                 (ward_id, run_id, ok, Jsonb(shares), Jsonb(stations), Jsonb(cams), Jsonb(sources), Jsonb(probs)))
    conn.commit()
    return {"run_id": run_id, "ok": ok, "shares": shares, "stations": stations, "cams": cams, "problems": probs,
            **sources}


def fill_from_cams(conn, ward_id: str, rd: pd.DataFrame, now: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    """Corrected CAMS rows for real stations whose feed is stale (issue #28). Never written to readings."""
    info = {"stations": 0, "hours": 0, "corrections": {}}
    real = rd[~rd["synthetic"].astype(bool) & rd["pm10"].notna()]
    if real.empty:
        return pd.DataFrame(columns=rd.columns), info
    cm = db.read_frame(conn, """select c.station_id, c.ts, c.pm10 from cams_hourly c join stations s on s.id = c.station_id
                                 where s.ward_id=%s and c.pm10 is not null order by c.ts""", (ward_id,))
    if cm.empty:
        return pd.DataFrame(columns=rd.columns), info
    cm["ts"] = pd.to_datetime(cm["ts"], utc=True)
    cm["pm10"] = cm["pm10"].astype(float)
    rows = []
    for sid, obs in real.groupby("station_id"):
        last = obs["ts"].max()
        if now - last <= pd.Timedelta(hours=FRESH_HOURS) or now - last > FILL_MAX_STALE:
            continue
        model = cm[cm["station_id"] == sid].set_index("ts")["pm10"]
        o = obs.set_index("ts")["pm10"]
        k = fill.fit(o, model)
        if k.method == "none":
            continue
        g = fill.gap(o, model, k, now)
        if g.empty:
            continue
        info["corrections"][sid] = {"slope": k.slope, "intercept": k.intercept, "hours": k.hours, "mae": k.mae,
                                    "method": k.method, "last_real": last.isoformat()}
        rows.append(pd.DataFrame({"station_id": sid, "ts": g.index, "pm10": g.to_numpy(), "synthetic": False, "filled": True}))
    return (pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=rd.columns)), info


def backtest(conn, settings: Settings, days: int = 60) -> dict:
    """Back-test the forecast over the last `days` days of data (F3). Uses only real station readings
    when there are any, so the report's numbers are real; otherwise synthetic, and labelled so."""
    wx = db.read_frame(conn, "select ts, wind_speed, wind_dir, blh, temp, rh, precip, synthetic from weather_hourly where ward_id=%s order by ts", (settings.ward_id,))
    rd = db.read_frame(conn, """select r.station_id, r.ts, r.pm10, r.synthetic from readings r
                                join stations s on s.id = r.station_id where s.ward_id=%s and r.pm10 is not null
                                order by r.ts""", (settings.ward_id,))
    for c in ["wind_speed", "wind_dir", "blh", "temp", "rh", "precip"]:
        wx[c] = wx[c].astype(float)
    wx["ts"] = pd.to_datetime(wx["ts"], utc=True)
    rd["ts"] = pd.to_datetime(rd["ts"], utc=True)
    rd["pm10"] = rd["pm10"].astype(float)
    real = rd[~rd["synthetic"].astype(bool)]
    is_real = not real.empty
    use = real if is_real else rd
    # Stations with enough history to learn from (at least 60 days of hours).
    counts = use.groupby("station_id")["pm10"].count()
    use = use[use["station_id"].isin(counts[counts >= 24 * 60].index)]
    end = use["ts"].max().floor("D")
    start = end - pd.Timedelta(days=days)
    res = bt.run(use[["station_id", "ts", "pm10"]], wx, start, end, settings.horizon_hours, 24, settings.exceed_threshold)
    wx_used = wx[(wx["ts"] >= use["ts"].min()) & (wx["ts"] <= end)]
    mode = ("live" if not wx_used["synthetic"].any() else "mixed") if is_real else "synthetic"
    row = conn.execute(
        """insert into backtests (ward_id, data_mode, stations, train_end, test_end, origins, metrics, spike_day, note)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
        (settings.ward_id, mode, res.stations, res.train_end.to_pydatetime(), res.test_end.to_pydatetime(), res.origins,
         json.dumps(res.metrics), json.dumps(res.spike_day) if res.spike_day else None, res.note)).fetchone()
    conn.commit()
    return {"id": row[0], "data_mode": mode, "stations": res.stations, "origins": res.origins,
            "metrics": res.metrics, "spike_day": res.spike_day}


def discover_sites(conn, settings: Settings, months_back: int = 12) -> dict:
    """Sentinel-2 change over the ward (F2): the clearest dry-season scene this year against the same
    months a year earlier. Stores the candidates; matched ones count as a signal for the agent."""
    from . import discover

    seed = load_seed()
    sites = [{"id": r.id, "lat": float(r.lat), "lon": float(r.lon)} for r in
             db.read_frame(conn, "select id, lat, lon from sites where ward_id=%s", (settings.ward_id,)).itertuples()]
    now = pd.Timestamp.now(tz="UTC")
    year = now.year if now.month >= 6 else now.year - 1  # the latest finished dry season (Jan-May)
    after = (f"{year}-01-01T00:00:00Z", f"{year}-05-31T00:00:00Z")
    before = (f"{year - months_back // 12}-01-01T00:00:00Z", f"{year - months_back // 12}-05-31T00:00:00Z") \
        if months_back >= 12 else after
    res = discover.discover(seed["ward"]["bbox"], sites, after, before)
    n = db.write_candidates(conn, settings.ward_id, res["before"], res["after"], res["candidates"])
    return {"before": res["before"], "after": res["after"], "candidates": n,
            "matched": sorted({c["site_id"] for c in res["candidates"] if c["site_id"]})}


def replay_outage(conn, settings: Settings, days: int = 30, outage_h: int = 96) -> dict:
    """Verify the CAMS fill on real history (issue #28) and store the result as a back-test."""
    rd = db.read_frame(conn, """select r.station_id, r.ts, r.pm10 from readings r join stations s on s.id = r.station_id
                                where s.ward_id=%s and not r.synthetic and r.pm10 is not null order by r.ts""", (settings.ward_id,))
    cm = db.read_frame(conn, """select c.station_id, c.ts, c.pm10 from cams_hourly c join stations s on s.id = c.station_id
                                where s.ward_id=%s and c.pm10 is not null""", (settings.ward_id,))
    wx = db.read_frame(conn, "select ts, wind_speed, wind_dir, blh, temp, rh, precip, synthetic from weather_hourly where ward_id=%s order by ts", (settings.ward_id,))
    if rd.empty or cm.empty:
        raise RuntimeError("Needs real readings and CAMS: run `dusttrace ingest` online first.")
    for c in ["wind_speed", "wind_dir", "blh", "temp", "rh", "precip"]:
        wx[c] = wx[c].astype(float)
    wx["ts"] = pd.to_datetime(wx["ts"], utc=True)
    for f in (rd, cm):
        f["ts"] = pd.to_datetime(f["ts"], utc=True)
        f["pm10"] = f["pm10"].astype(float)
    counts = rd.groupby("station_id")["pm10"].count()
    rd = rd[rd["station_id"].isin(counts[counts >= 24 * 60].index)]
    end = rd["ts"].max().floor("D")
    start = end - pd.Timedelta(days=days)
    res = bt.outage_replay(rd, cm, wx, start, end, outage_h, settings.horizon_hours, 24, settings.exceed_threshold)
    note = (f"Outage replay: the last {outage_h} h before each forecast hidden and filled from corrected CAMS. "
            "Weather at the target hour is observed weather.")
    mode = "live" if not wx[(wx["ts"] >= rd["ts"].min()) & (wx["ts"] <= end)]["synthetic"].any() else "mixed"
    row = conn.execute(
        """insert into backtests (ward_id, kind, data_mode, stations, train_end, test_end, origins, metrics, note)
           values (%s,'outage_replay',%s,%s,%s,%s,%s,%s,%s) returning id""",
        (settings.ward_id, mode, res["stations"], start.to_pydatetime(), end.to_pydatetime(), res["origins"],
         json.dumps(res["metrics"]), note)).fetchone()
    conn.commit()
    return {"id": row[0], "data_mode": mode, **{k: res[k] for k in ("origins", "outage_hours", "stations", "metrics")}}


def plume_hour(ts) -> float:
    return (ts.hour + ts.minute / 60 + 5.5) % 24


def _unique(names) -> list[str]:
    """Sorted names with case-insensitive duplicates removed (OSM often maps a place twice)."""
    seen = {}
    for n in names:
        seen.setdefault(n.casefold(), n)
    return sorted(seen.values())


def _unique_pairs(pairs) -> list:
    seen = {}
    for ts, n in pairs:
        seen.setdefault((ts, n.casefold()), (ts, n))
    return sorted(seen.values())


def anchor(rd: pd.DataFrame, now: pd.Timestamp) -> tuple[pd.Timestamp, pd.Index]:
    """Forecast origin t0 and the stations to use: stations with 6+ readings in the 24 h before t0.

    Real stations win while their newest reading is under FRESH_HOURS old. Otherwise the synthetic
    samples anchor the run, so a stalled feed can't push the 48 h forecast into the past.
    """
    ok = rd.dropna(subset=["pm10"])
    is_syn = ok["synthetic"].astype(bool)
    real, syn = ok[~is_syn], ok[is_syn]
    fresh = not real.empty and now - real["ts"].max() <= pd.Timedelta(hours=FRESH_HOURS)
    t0, active = ok["ts"].max().floor("h"), pd.Index([])
    for pool in ([real] if fresh else []) + [syn, ok]:
        if pool.empty:
            continue
        t0 = pool["ts"].max().floor("h")
        recent = pool[pool["ts"] > t0 - pd.Timedelta(hours=24)].groupby("station_id")["pm10"].count()
        active = recent[recent >= 6].index
        if len(active):
            break
    return t0, active


def _mode(wx_any, wx_all, rd_any, rd_all) -> str:
    if not wx_any and not rd_any:
        return "live"
    if wx_all and rd_all:
        return "synthetic"
    return "mixed"


def _expand(bbox, d):
    return [bbox[0] - d, bbox[1] - d, bbox[2] + d, bbox[3] + d]
