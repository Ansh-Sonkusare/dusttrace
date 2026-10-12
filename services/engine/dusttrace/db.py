"""Postgres access (works with Supabase or local PostGIS)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import psycopg

from .config import REPO_ROOT

MIGRATIONS = REPO_ROOT / "supabase" / "migrations"


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, autocommit=False)


def migrate(conn: psycopg.Connection) -> list[str]:
    applied = []
    for f in sorted(Path(MIGRATIONS).glob("*.sql")):
        conn.execute(f.read_text(encoding="utf-8"))
        applied.append(f.name)
    conn.commit()
    return applied


def upsert_seed(conn: psycopg.Connection, seed: dict) -> None:
    w = seed["ward"]
    conn.execute(
        """insert into wards (id, name, center_lat, center_lon, bbox) values (%s,%s,%s,%s,%s)
           on conflict (id) do update set name=excluded.name, center_lat=excluded.center_lat,
           center_lon=excluded.center_lon, bbox=excluded.bbox""",
        (w["id"], w["name"], w["center_lat"], w["center_lon"], w["bbox"]),
    )
    for s in seed["stations"]:
        upsert_station(conn, {**s, "source": "seed"}, w["id"])
    for s in seed["sites"]:
        conn.execute(
            """insert into sites (id, name, activity, developer, lat, lon, ward_id, area_m2, sensor_status, demo)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,true)
               on conflict (id) do update set name=excluded.name, activity=excluded.activity,
               developer=excluded.developer, lat=excluded.lat, lon=excluded.lon, area_m2=excluded.area_m2,
               sensor_status=excluded.sensor_status""",
            (s["id"], s["name"], s["activity"], s.get("developer"), s["lat"], s["lon"], w["id"],
             s.get("area_m2", 5000), s.get("sensor_status", "unknown")),
        )
    for s in seed["sites"]:
        sn = s.get("sensor")
        if sn:
            conn.execute(
                """insert into site_sensors (id, site_id, vendor, has_relay, simulated, injected_fault)
                   values (%s,%s,%s,%s,true,%s)
                   on conflict (id) do update set site_id=excluded.site_id, vendor=excluded.vendor,
                   has_relay=excluded.has_relay, injected_fault=excluded.injected_fault""",
                (sn["id"], s["id"], sn.get("vendor"), bool(sn.get("relay")), sn.get("fault", "none")),
            )
    upsert_receptors(conn, [{**r, "source": "seed"} for r in seed["receptors"]], w["id"])
    conn.commit()


def upsert_station(conn, s: dict, ward_id: str) -> None:
    meta = {k: v for k, v in s.items() if k in ("sensors", "provider")}
    conn.execute(
        """insert into stations (id, name, source, lat, lon, ward_id, meta) values (%s,%s,%s,%s,%s,%s,%s)
           on conflict (id) do update set name=excluded.name, lat=excluded.lat, lon=excluded.lon,
           meta=excluded.meta""",
        (s["id"], s["name"], s["source"], s["lat"], s["lon"], ward_id, json.dumps(meta)),
    )


def upsert_receptors(conn, recs: list[dict], ward_id: str) -> None:
    for r in recs:
        conn.execute(
            """insert into receptors (id, name, kind, lat, lon, ward_id, population, source)
               values (%s,%s,%s,%s,%s,%s,%s,%s)
               on conflict (id) do update set name=excluded.name, kind=excluded.kind, lat=excluded.lat,
               lon=excluded.lon, population=excluded.population, source=excluded.source""",
            (r["id"], r["name"], r["kind"], r["lat"], r["lon"], ward_id, r.get("population", 500),
             r.get("source", "seed")),
        )


# Real OSM schools and hospitals replace the demo ones once loaded. Demo housing stays until a real
# population source exists.
RECEPTORS_SQL = """select id, name, kind, lat, lon, population, source from receptors r
  where ward_id=%s and not (source = 'seed' and kind in ('school', 'hospital') and exists (
    select 1 from receptors o where o.ward_id = r.ward_id and o.source = 'osm'))
  order by id"""


def read_receptors(conn, ward_id: str) -> pd.DataFrame:
    return read_frame(conn, RECEPTORS_SQL, (ward_id,))


def write_readings(conn, df: pd.DataFrame, synthetic: bool) -> int:
    if df.empty:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """insert into readings (station_id, ts, pm10, pm25, synthetic) values (%s,%s,%s,%s,%s)
               on conflict (station_id, ts) do update set pm10=excluded.pm10, pm25=excluded.pm25,
               synthetic=excluded.synthetic
               where readings.synthetic or not excluded.synthetic""",  # never overwrite real with synthetic
            [(r.station_id, r.ts.to_pydatetime(), _f(r.pm10), _f(r.pm25), synthetic)
             for r in df.itertuples()],
        )
    conn.commit()
    return len(df)


def write_weather(conn, ward_id: str, df: pd.DataFrame, now: pd.Timestamp, synthetic: bool) -> int:
    if df.empty:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """insert into weather_hourly (ward_id, ts, wind_speed, wind_dir, blh, temp, rh, precip,
               is_forecast, synthetic, fetched_at) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
               on conflict (ward_id, ts) do update set wind_speed=excluded.wind_speed,
               wind_dir=excluded.wind_dir, blh=excluded.blh, temp=excluded.temp, rh=excluded.rh,
               precip=excluded.precip, is_forecast=excluded.is_forecast, synthetic=excluded.synthetic,
               fetched_at=now()
               where weather_hourly.synthetic or not excluded.synthetic""",  # never overwrite real with synthetic
            [(ward_id, r.ts.to_pydatetime(), _f(r.wind_speed), _f(r.wind_dir), _f(r.blh), _f(r.temp),
              _f(r.rh), _f(r.precip), bool(r.ts > now), synthetic) for r in df.itertuples()],
        )
    conn.commit()
    return len(df)


def read_frame(conn, sql: str, params=()) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def create_run(conn, ward_id: str, issued_at, data_mode: str, model: str, metrics: dict) -> int:
    row = conn.execute(
        "insert into runs (ward_id, issued_at, data_mode, model, metrics) values (%s,%s,%s,%s,%s) returning id",
        (ward_id, issued_at, data_mode, model, json.dumps(metrics)),
    ).fetchone()
    return int(row[0])


def write_forecasts(conn, run_id: int, df: pd.DataFrame) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "insert into forecasts (run_id, station_id, ts, pm10, pm10_lo, pm10_hi, p_exceed) values (%s,%s,%s,%s,%s,%s,%s)",
            [(run_id, r.station_id, pd.Timestamp(r.ts).to_pydatetime(), float(r.pm10), float(r.pm10_lo),
              float(r.pm10_hi), float(r.p_exceed)) for r in df.itertuples()],
        )


def write_site_hours(conn, run_id: int, hours) -> None:
    with conn.cursor() as cur:
        plumes, exps, wins = [], [], []
        for sh in hours:
            ts = sh.ts.to_pydatetime()
            gj = json.dumps({"type": "Polygon", "coordinates": [sh.ring]}) if len(sh.ring) >= 4 else None
            plumes.append((run_id, sh.site_id, ts, gj, sh.max_conc, sh.length_m))
            for rid, c in sh.exposures:
                exps.append((run_id, sh.site_id, rid, ts, c))
            wins.append((run_id, sh.site_id, ts, sh.status, sh.exposed_people, sh.sensitive_hit, sh.reason))
        cur.executemany(
            """insert into plumes (run_id, site_id, ts, geom, max_conc, length_m)
               values (%s,%s,%s, case when %s::text is null then null
                 else st_setsrid(st_geomfromgeojson(%s::text),4326) end, %s,%s)""",
            [(a, b, c, d, d, e, f) for a, b, c, d, e, f in plumes],
        )
        cur.executemany("insert into exposures (run_id, site_id, receptor_id, ts, conc) values (%s,%s,%s,%s,%s)", exps)
        cur.executemany(
            """insert into safe_windows (run_id, site_id, ts, status, exposed_people, sensitive_hit, reason)
               values (%s,%s,%s,%s,%s,%s,%s)""", wins)


def _f(v):
    try:
        if v is None or pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def read_sensor_specs(conn, ward_id: str) -> pd.DataFrame:
    return read_frame(conn, """select n.id as sensor_id, n.site_id, s.lat, s.lon, s.area_m2, s.activity,
                                      coalesce(n.injected_fault, 'none') as fault
                                 from site_sensors n join sites s on s.id = n.site_id
                                where s.ward_id=%s order by n.id""", (ward_id,))


def write_site_readings(conn, df: pd.DataFrame) -> int:
    """Simulated site-sensor readings. Always synthetic until BMC's feed is connected."""
    if df.empty:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """insert into site_readings (sensor_id, ts, pm10, pm25, rh, synthetic) values (%s,%s,%s,%s,%s,true)
               on conflict (sensor_id, ts) do update set pm10=excluded.pm10, pm25=excluded.pm25, rh=excluded.rh
               where site_readings.synthetic""",
            [(r.sensor_id, pd.Timestamp(r.ts).to_pydatetime(), _f(r.pm10), _f(r.pm25), _f(r.rh)) for r in df.itertuples()],
        )
    return len(df)


def write_audits(conn, run_id: int, results) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """insert into sensor_audits (run_id, sensor_id, site_id, score, band, checks, reasons)
               values (%s,%s,%s,%s,%s,%s,%s)""",
            [(run_id, a.sensor_id, a.site_id, a.score, a.band, json.dumps(a.checks), a.reasons) for a in results],
        )


def site_signals(conn, ward_id: str) -> dict:
    """Per site: citizen reports in 7 days (not rejected) and verified ones in 30 days; confirmed
    violations in 30 and 90 days, and whether an officer confirmed one in the last 7 days."""
    rows = conn.execute("""select s.id,
            (select count(*) from inspections i where i.site_id=s.id and i.outcome='violation' and i.at > now() - interval '30 days'),
            (select count(*) from inspections i where i.site_id=s.id and i.outcome='violation' and i.at > now() - interval '7 days'),
            (select count(*) from inspections i where i.site_id=s.id and i.outcome='violation' and i.at > now() - interval '90 days'),
            (select count(*) from citizen_reports c where c.site_id=s.id and c.status <> 'rejected' and c.at > now() - interval '7 days'),
            (select count(*) from citizen_reports c where c.site_id=s.id and c.status = 'verified' and c.at > now() - interval '30 days'),
            exists (select 1 from site_candidates k where k.site_id=s.id and k.status <> 'rejected'
                      and k.found_at > now() - interval '120 days')
          from sites s where s.ward_id=%s""", (ward_id,)).fetchall()
    return {r[0]: {"reports": int(r[4]), "verified_reports": int(r[5]), "violations": int(r[1]),
                   "violations_90d": int(r[3]), "confirmed_violation": r[2] > 0, "satellite": bool(r[6])} for r in rows}


def write_ranking(conn, run_id: int, ranked) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """insert into inspection_rank (run_id, site_id, rank, score, components, reasons)
               values (%s,%s,%s,%s,%s,%s)""",
            [(run_id, r.site_id, r.rank, r.score, json.dumps(r.components), r.reasons) for r in ranked],
        )


def pending_requests(conn, site_id: str) -> list[dict]:
    rows = conn.execute("""select a.action, a.deadline from case_actions a join cases c on c.id = a.case_id
                            where c.site_id=%s and c.closed_at is null and a.phase='final'
                              and a.status='requested' and a.deadline is not null""", (site_id,)).fetchall()
    return [{"action": r[0], "deadline": r[1]} for r in rows]


def write_case(conn, run_id: int, site_id: str, d) -> int | None:
    """Update the site's open case with this run's decision, or open one; close it when nothing triggers.
    Existing actions keep their status and deadline, so officer decisions and D7 clocks survive runs.
    Returns the open case id, or None when there is no open case."""
    row = conn.execute("select id from cases where site_id=%s and closed_at is null", (site_id,)).fetchone()
    if d is None:
        if row:
            conn.execute("""update cases set state='DONE', closed_at=now(), updated_at=now(), last_run_id=%s,
                            stop_reason='Nothing triggers in the latest run.' where id=%s""", (run_id, row[0]))
        return None
    vals = (d.state, d.triggers, d.signals, json.dumps(d.hypotheses), d.what_changed, d.stop_reason, run_id)
    if row:
        case_id = row[0]
        conn.execute("""update cases set state=%s, triggers=%s, signals=%s, hypotheses=%s, what_changed=%s,
                        stop_reason=%s, last_run_id=%s, updated_at=now() where id=%s""", (*vals, case_id))
    else:
        case_id = conn.execute("""insert into cases (state, triggers, signals, hypotheses, what_changed, stop_reason,
                                  last_run_id, opened_run_id, site_id) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                  returning id""", (*vals, run_id, site_id)).fetchone()[0]
    with conn.cursor() as cur:
        for phase, acts in (("initial", d.initial), ("final", d.final)):
            cur.executemany(
                """insert into case_actions (case_id, phase, action, type, route, rule, reason, status, at, deadline)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   on conflict (case_id, phase, action, rule) do update set reason=excluded.reason, at=excluded.at""",
                [(case_id, phase, a.action, a.type, a.route, a.rule, a.reason, a.status,
                  a.at.to_pydatetime() if a.at is not None else None,
                  a.deadline.to_pydatetime() if a.deadline is not None else None) for a in acts],
            )
    if d.expired:
        conn.execute("""update case_actions set status='expired' where case_id=%s and status='requested'
                        and action = any(%s)""", (case_id, d.expired))
    return case_id


def plans_accepted_today(conn, ward_id: str) -> set[str]:
    rows = conn.execute("""select distinct p.site_id from plan_acceptances p join sites s on s.id = p.site_id
                            where s.ward_id=%s and (p.accepted_at at time zone 'Asia/Kolkata')::date
                                  = (now() at time zone 'Asia/Kolkata')::date""", (ward_id,)).fetchall()
    return {r[0] for r in rows}


def write_alerts(conn, run_id: int, rows) -> None:
    with conn.cursor() as cur:
        cur.executemany("insert into alerts (run_id, kind, site_id, case_id, title, action) values (%s,%s,%s,%s,%s,%s)",
                        [(run_id, a.kind, a.site_id, a.case_id, a.title, a.action) for a in rows])


def write_dust_scores(conn, run_id: int, scores: dict) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """insert into dust_scores (run_id, site_id, score, band, components, notes) values (%s,%s,%s,%s,%s,%s)""",
            [(run_id, sid, s.score, s.band, json.dumps(s.components), s.notes) for sid, s in scores.items()],
        )


def windows_followed(conn, ward_id: str) -> dict:
    """Per site, over the last 7 days: days the manager accepted the plan / days the site had Avoid
    windows (IST dates of the runs). Sites with nothing to avoid are left out (unknown)."""
    rows = conn.execute("""
        with avoid_days as (
          select distinct w.site_id, (r.created_at at time zone 'Asia/Kolkata')::date as d
            from safe_windows w join runs r on r.id = w.run_id join sites s on s.id = w.site_id
           where s.ward_id=%s and w.status='avoid' and r.created_at > now() - interval '7 days'),
        accepted as (
          select distinct site_id, (accepted_at at time zone 'Asia/Kolkata')::date as d
            from plan_acceptances where accepted_at > now() - interval '7 days')
        select a.site_id, count(*), count(x.d) from avoid_days a
          left join accepted x on x.site_id = a.site_id and x.d = a.d group by a.site_id""", (ward_id,)).fetchall()
    return {r[0]: round(r[2] / r[1], 3) for r in rows}


def write_candidates(conn, ward_id: str, before: str, after: str, cands: list[dict]) -> int:
    """Replace the ward's unverified candidates with this scene pair's; confirmed or rejected ones stay."""
    conn.execute("delete from site_candidates where ward_id=%s and status='unverified'", (ward_id,))
    with conn.cursor() as cur:
        cur.executemany(
            """insert into site_candidates (ward_id, scene_before, scene_after, lat, lon, area_m2, site_id)
               values (%s,%s,%s,%s,%s,%s,%s)""",
            [(ward_id, before, after, c["lat"], c["lon"], c["area_m2"], c.get("site_id")) for c in cands],
        )
    conn.commit()
    return len(cands)
