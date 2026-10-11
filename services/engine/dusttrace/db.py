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


def write_readings(conn, df: pd.DataFrame, synthetic: bool) -> int:
    if df.empty:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """insert into readings (station_id, ts, pm10, pm25, synthetic) values (%s,%s,%s,%s,%s)
               on conflict (station_id, ts) do update set pm10=excluded.pm10, pm25=excluded.pm25,
               synthetic=excluded.synthetic""",
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
               fetched_at=now()""",
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
