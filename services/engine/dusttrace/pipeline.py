"""Ingest and run steps, wired together. Each step falls back to synthetic data if a live source fails."""

from __future__ import annotations

import logging
from datetime import timedelta

import pandas as pd

from . import audit, db, forecast, windows
from .config import Settings, load_seed
from .sources import openaq, openmeteo, overpass, synthetic

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
    n_synthetic = 0
    if not rd_live and mode != "live":
        hist_wx = wx[wx["ts"] <= now]
        ids = [s["id"] for s in seed["stations"]]
        n_synthetic = db.write_readings(conn, synthetic.readings(hist_wx, ids), synthetic=True)
    report["readings"] = {"rows": total, "synthetic_rows": n_synthetic, "live": rd_live,
                          "newest_live": latest.isoformat() if latest is not None else None}
    return report


def receptor_bbox(ward_bbox: list[float], margin_deg: float = 0.01) -> list[float]:
    """Ward bbox plus about 1 km, so plumes that cross the ward boundary still find receptors."""
    return _expand(ward_bbox, margin_deg)


def load_receptors_osm(conn, settings: Settings) -> int:
    seed = load_seed()
    recs = overpass.fetch(receptor_bbox(seed["ward"]["bbox"]))
    db.upsert_receptors(conn, recs, seed["ward"]["id"])
    conn.commit()
    return len(recs)


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

    t0, active = anchor(rd, now_hour())
    rd = rd[rd["station_id"].isin(active)]

    model = forecast.train(rd[["station_id", "ts", "pm10"]], wx, settings.horizon_hours, settings.exceed_threshold)
    fc = forecast.predict(model, rd[["station_id", "ts", "pm10"]], wx, t0, settings.horizon_hours)

    data_mode = _mode(wx["synthetic"].any(), wx["synthetic"].all(), rd["synthetic"].any(), rd["synthetic"].all())
    audits, bench = audit_sensors(conn, ward_id, rd, wx, t0)
    metrics = {**model.metrics, "stations": list(active), "audit": bench}
    run_id = db.create_run(conn, ward_id, t0.to_pydatetime(), data_mode, "lightgbm-direct-v1", metrics)
    db.write_forecasts(conn, run_id, fc)
    db.write_audits(conn, run_id, audits)

    ward_fc = fc[fc["station_id"] == "ward"].set_index("ts")["p_exceed"]
    future = wx[(wx["ts"] > t0) & (wx["ts"] <= t0 + pd.Timedelta(hours=settings.horizon_hours))]
    sites = db.read_frame(conn, "select id, name, activity, lat, lon, area_m2 from sites where ward_id=%s", (ward_id,))
    recs = db.read_receptors(conn, ward_id)
    for c in ["lat", "lon", "area_m2"]:
        sites[c] = sites[c].astype(float)
    for c in ["lat", "lon"]:
        recs[c] = recs[c].astype(float)
    hours = windows.evaluate(sites, recs, future, ward_fc, settings)
    db.write_site_hours(conn, run_id, hours)
    conn.commit()

    counts = pd.Series([h.status for h in hours]).value_counts().to_dict()
    return {"run_id": run_id, "issued_at": t0.isoformat(), "data_mode": data_mode,
            "metrics": metrics, "window_counts": counts, "stations": list(active),
            "sensor_trust": {a.site_id: a.score for a in audits}}


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
    return results, audit.benchmark(ambient, wx, t0)


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
