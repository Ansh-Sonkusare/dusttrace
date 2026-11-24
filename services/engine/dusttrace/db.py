"""Postgres access (works with Supabase or local PostGIS)."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
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
        """insert into wards (id, name, center_lat, center_lon, bbox, boundary) values (%s,%s,%s,%s,%s,%s)
           on conflict (id) do update set name=excluded.name, center_lat=excluded.center_lat,
           center_lon=excluded.center_lon, bbox=excluded.bbox, boundary=excluded.boundary""",
        (w["id"], w["name"], w["center_lat"], w["center_lon"], w["bbox"],
         json.dumps(w["boundary"]) if w.get("boundary") else None),
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


def upsert_sites(conn, sites: list[dict], ward_id: str) -> int:
    """Real construction sites (OSM, or satellite candidates an officer confirmed). Never demo.

    Their monitor feed isn't connected, so sensor_status is 'not_connected'. A refresh updates the
    name, shape and position but keeps any status an officer has set since.
    """
    for s in sites:
        conn.execute(
            """insert into sites (id, name, activity, developer, lat, lon, ward_id, area_m2, sensor_status, demo, source)
               values (%s,%s,%s,%s,%s,%s,%s,%s,'not_connected',false,%s)
               on conflict (id) do update set name=excluded.name, activity=excluded.activity,
               lat=excluded.lat, lon=excluded.lon, area_m2=excluded.area_m2, active=true, updated_at=now()""",
            (s["id"], s["name"], s["activity"], s.get("developer"), s["lat"], s["lon"], ward_id,
             s.get("area_m2", 5000), s.get("source", "osm")),
        )
    return len(sites)


def add_node(conn, n: dict, ward_id: str) -> str:
    """Provision a DustTrace Node, or rotate its key. Returns the key: shown once, stored only as SHA-256."""
    key = secrets.token_urlsafe(32)
    conn.execute(
        """insert into nodes (id, ward_id, name, host_kind, receptor_id, site_id, lat, lon, key_hash)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
           on conflict (id) do update set ward_id=excluded.ward_id, name=excluded.name, host_kind=excluded.host_kind,
           receptor_id=excluded.receptor_id, site_id=excluded.site_id, lat=excluded.lat, lon=excluded.lon,
           key_hash=excluded.key_hash, active=true""",
        (n["id"], ward_id, n["name"], n["host_kind"], n.get("receptor_id"), n.get("site_id"), n["lat"], n["lon"],
         hashlib.sha256(key.encode()).hexdigest()),
    )
    return key


def hot_node_sites(conn, ward_id: str, now, hours: int = 6, threshold: float = 100.0,
                   kinds: list[str] | None = None) -> set[str]:
    """Sites whose plume, in the forecast in force at the time, reached a receptor in an hour when that
    receptor's DustTrace Node read PM10 above the threshold, within the last few hours. `kinds` limits
    it to nodes hosted by those kinds of place (a school or hospital node is a D-rule trigger)."""
    rows = conn.execute("""select distinct e.site_id
                             from nodes n
                             join node_hourly h on h.node_id = n.id
                             join exposures e on e.receptor_id = n.receptor_id and e.ts = h.ts
                            where n.ward_id=%s and n.active and h.ts > %s and h.ts <= %s and h.pm10 > %s
                              and (%s::text[] is null or n.host_kind = any(%s::text[]))
                              and e.run_id = (select r.id from runs r where r.ward_id = n.ward_id and r.issued_at < h.ts
                                               order by r.issued_at desc, r.id desc limit 1)""",
                        (ward_id, (now - pd.Timedelta(hours=hours)).to_pydatetime(), now.to_pydatetime(), threshold,
                         kinds, kinds)).fetchall()
    return {r[0] for r in rows}


def upsert_station(conn, s: dict, ward_id: str) -> None:
    meta = {k: v for k, v in s.items() if k in ("sensors", "provider")}
    conn.execute(
        # A station belongs to the ward whose centre is nearest, whichever ward's search found it.
        """insert into stations (id, name, source, lat, lon, ward_id, meta)
           values (%s,%s,%s,%s,%s, coalesce((
             select w.id from wards w
              order by power(w.center_lat - %s, 2) + power((w.center_lon - %s) * cos(radians(%s)), 2), w.id
              limit 1), %s), %s)
           on conflict (id) do update set name=excluded.name, lat=excluded.lat, lon=excluded.lon,
           meta=excluded.meta, ward_id=excluded.ward_id""",
        (s["id"], s["name"], s["source"], s["lat"], s["lon"], s["lat"], s["lon"], s["lat"], ward_id, json.dumps(meta)),
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


# Real OSM receptors replace the demo ones once loaded: OSM schools and hospitals replace the demo
# schools and hospitals, and census-based OSM housing (issue #31) replaces the demo housing.
RECEPTORS_SQL = """select id, name, kind, lat, lon, population, source from receptors r
  where ward_id=%s and not (source = 'seed' and exists (
    select 1 from receptors o where o.ward_id = r.ward_id and o.source = 'osm'
       and (o.kind = 'housing') = (r.kind = 'housing')))
  order by id"""


def replace_osm_housing(conn, recs: list[dict], ward_id: str) -> None:
    """Upsert the estimated housing cells and drop cells that no longer qualify."""
    upsert_receptors(conn, recs, ward_id)
    conn.execute("""delete from receptors where ward_id=%s and source='osm' and kind='housing'
                    and not (id = any(%s))""", (ward_id, [r["id"] for r in recs]))


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


def retire_osm_sites(conn, ward_id: str, keep: list[str]) -> int:
    """OSM sites the latest pull no longer returns inside the ward stop being planned; history stays."""
    return conn.execute("""update sites set active=false, updated_at=now() where ward_id=%s and source='osm'
                           and active and not (id = any(%s))""", (ward_id, keep)).rowcount


def demo_sites() -> bool:
    """Whether the run includes the demo sites. DUSTTRACE_DEMO_SITES=0 leaves only real ones."""
    return os.environ.get("DUSTTRACE_DEMO_SITES", "1").strip().lower() not in ("0", "false", "no", "off")


def read_sites(conn, ward_id: str) -> pd.DataFrame:
    """The ward's sites for a run, with whether each site's monitor status is known."""
    df = read_frame(conn, """select s.id, s.name, s.activity, s.lat, s.lon, s.area_m2,
                                    s.sensor_status <> 'not_connected' as sensor_known
                               from sites s where s.ward_id=%s and s.active and (%s or not s.demo) order by s.id""",
                    (ward_id, demo_sites()))
    for c in ["lat", "lon", "area_m2"]:
        df[c] = df[c].astype(float)
    return df


def read_sensor_specs(conn, ward_id: str, as_of, imagery_days: int) -> pd.DataFrame:
    """Each site sensor, its calibration date, and the date of the newest Sentinel-2 scene matched to its
    site (not rejected) taken in the `imagery_days` up to `as_of`, the end of the audited week, if any.
    The id gives the scene's UTC day but not its hour, so a scene counts only once that whole day is
    before `as_of`. A scene id without a date counts for nothing."""
    return read_frame(conn, r"""select n.id as sensor_id, n.site_id, s.lat, s.lon, s.area_m2, s.activity,
                                      coalesce(n.injected_fault, 'none') as fault, n.simulated, n.calibrated_on,
                                      (select to_char(max(c.d), 'YYYY-MM-DD')
                                         from (select to_date(substring(k.scene_after from '_(\d{8})_'), 'YYYYMMDD') as d
                                                 from site_candidates k
                                                where k.site_id = s.id and k.status <> 'rejected') c
                                        where (c.d + 1)::timestamp at time zone 'UTC' <= %s
                                          and (c.d + 1)::timestamp at time zone 'UTC' > %s - make_interval(days => %s)) as imagery
                                 from site_sensors n join sites s on s.id = n.site_id
                                where s.ward_id=%s and (%s or not s.demo) order by n.id""",
                      (as_of.to_pydatetime(), as_of.to_pydatetime(), imagery_days, ward_id, demo_sites()))


def write_calibration(conn, dates: dict[str, pd.Timestamp]) -> None:
    """Simulated calibration dates; a real sensor's date on record is never overwritten."""
    with conn.cursor() as cur:
        cur.executemany("update site_sensors set calibrated_on=%s where id=%s and simulated",
                        [(pd.Timestamp(d).date(), k) for k, d in dates.items()])


def node_pm10(conn, ward_id: str, start, end) -> pd.DataFrame | None:
    """Hourly PM10 at the ward's DustTrace Nodes, one column per node; None if it has none reporting."""
    df = read_frame(conn, """select h.node_id, h.ts, h.pm10 from node_hourly h join nodes n on n.id = h.node_id
                              where n.ward_id=%s and n.active and h.ts > %s and h.ts <= %s""",
                    (ward_id, start.to_pydatetime(), end.to_pydatetime()))
    if df.empty:
        return None
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.pivot_table(index="ts", columns="node_id", values="pm10").astype(float)


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


def site_signals(conn, ward_id: str, now=None) -> dict:
    """Per site: citizen reports in 7 days (not rejected) and verified ones in 30 days; confirmed
    violations in 30 and 90 days, whether an officer confirmed one in the last 7 days, and whether an
    officer approved a D10 referral in the last 7 days. As of `now` (default: the database clock);
    nothing after it counts."""
    rows = conn.execute("""with t as (select coalesce(%s::timestamptz, now()) as now)
        select s.id,
            (select count(*) from inspections i where i.site_id=s.id and i.outcome='violation' and i.at > t.now - interval '30 days' and i.at <= t.now),
            (select count(*) from inspections i where i.site_id=s.id and i.outcome='violation' and i.at > t.now - interval '7 days' and i.at <= t.now),
            (select count(*) from inspections i where i.site_id=s.id and i.outcome='violation' and i.at > t.now - interval '90 days' and i.at <= t.now),
            (select count(*) from citizen_reports c where c.site_id=s.id and c.status <> 'rejected' and c.at > t.now - interval '7 days' and c.at <= t.now),
            (select count(*) from citizen_reports c where c.site_id=s.id and c.status = 'verified' and c.at > t.now - interval '30 days' and c.at <= t.now),
            exists (select 1 from site_candidates k where k.site_id=s.id and k.status <> 'rejected'
                      and k.found_at > t.now - interval '120 days' and k.found_at <= t.now),
            exists (select 1 from case_actions a join cases c on c.id = a.case_id where c.site_id=s.id
                      and a.action='REFER_NON_CONSTRUCTION' and a.status='approved'
                      and a.decided_at > t.now - interval '7 days' and a.decided_at <= t.now)
          from sites s, t where s.ward_id=%s""", (now.to_pydatetime() if now is not None else None, ward_id)).fetchall()
    return {r[0]: {"reports": int(r[4]), "verified_reports": int(r[5]), "violations": int(r[1]),
                   "violations_90d": int(r[3]), "confirmed_violation": r[2] > 0, "satellite": bool(r[6]),
                   "referred": bool(r[7])} for r in rows}


def ignored_windows(conn, ward_id: str, now, days: int = 7) -> dict:
    """D8 (issue #56), per site: IST days in the last `days` with an Avoid hour (06:00-22:00 IST) of a plan the
    site manager had accepted before that hour, in which the DustTrace Node at the site's gate read PM10 above
    twice the ambient (D4's test; ambient is the mean of the ward's measured station readings that hour).
    Silence is not evidence: no accepted plan, no gate node, no node reading or no measured ambient counts
    as followed. The BMC site-sensor feed is simulated today, so it is not used."""
    rows = conn.execute("""
        with given as (
          select distinct p.site_id, w.ts
            from plan_acceptances p
            join runs r on r.id = p.run_id
            join safe_windows w on w.run_id = p.run_id and w.site_id = p.site_id and w.status = 'avoid'
           where r.ward_id = %(ward)s and p.accepted_at <= w.ts
             and w.ts > r.issued_at and w.ts <= r.issued_at + interval '24 hours'
             and w.ts > %(since)s and w.ts <= %(now)s
             and extract(hour from w.ts at time zone 'Asia/Kolkata') between 6 and 21),
        ambient as (
          select r.ts, avg(r.pm10) as pm10 from readings r join stations st on st.id = r.station_id
           where st.ward_id = %(ward)s and not r.synthetic and r.pm10 is not null
             and r.ts > %(since)s and r.ts <= %(now)s
           group by r.ts)
        select g.site_id, count(distinct (g.ts at time zone 'Asia/Kolkata')::date)
          from given g
          join nodes n on n.site_id = g.site_id and n.host_kind = 'site_gate'
          join node_hourly h on h.node_id = n.id and h.ts = g.ts
          join ambient a on a.ts = g.ts
         where h.pm10 > 2 * a.pm10
         group by g.site_id""",
        {"ward": ward_id, "now": now.to_pydatetime(), "since": (now - pd.Timedelta(days=days)).to_pydatetime()}).fetchall()
    return {r[0]: int(r[1]) for r in rows}


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


def write_actions(conn, case_id: int, phase: str, acts) -> None:
    """Record actions on a case. An action already there keeps its status and deadline."""
    with conn.cursor() as cur:
        cur.executemany(
            """insert into case_actions (case_id, phase, action, type, route, rule, reason, status, at, deadline)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               on conflict (case_id, phase, action, rule) do update set reason=excluded.reason, at=excluded.at""",
            [(case_id, phase, a.action, a.type, a.route, a.rule, a.reason, a.status,
              a.at.to_pydatetime() if a.at is not None else None,
              a.deadline.to_pydatetime() if a.deadline is not None else None) for a in acts],
        )


def write_case(conn, run_id: int, site_id: str, d) -> int | None:
    """Update the site's open case with this run's decision, or open one; close it when nothing triggers,
    or when the decision closes it (D10 after an approved referral). Existing actions keep their status and
    deadline, so officer decisions and D7 clocks survive runs.
    Returns the open case id, or None when there is no open case."""
    row = conn.execute("select id from cases where site_id=%s and closed_at is null", (site_id,)).fetchone()
    if d is None:
        if row:
            conn.execute("""update cases set state='DONE', closed_at=now(), updated_at=now(), last_run_id=%s,
                            stop_reason='Nothing triggers in the latest run.' where id=%s""", (run_id, row[0]))
        return None
    if d.state == "DONE" and not row:  # already closed with no action; don't open a case just to close it
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
    write_actions(conn, case_id, "initial", d.initial)
    write_actions(conn, case_id, "final", d.final)
    if d.expired:
        conn.execute("""update case_actions set status='expired' where case_id=%s and status='requested'
                        and action = any(%s)""", (case_id, d.expired))
    if d.state == "DONE":
        conn.execute("update cases set closed_at=now() where id=%s", (case_id,))
        return None
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
            """insert into dust_scores (run_id, site_id, score, band, components, notes, inputs)
               values (%s,%s,%s,%s,%s,%s,%s)""",
            [(run_id, sid, s.score, s.band, json.dumps(s.components), s.notes, json.dumps(s.inputs)) for sid, s in scores.items()],
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


def write_cams(conn, df: pd.DataFrame) -> int:
    """CAMS model values at station positions; refreshed on every ingest (the forecast part changes)."""
    df = df.dropna(subset=["pm10"]) if not df.empty else df
    if df.empty:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """insert into cams_hourly (station_id, ts, pm10, pm25) values (%s,%s,%s,%s)
               on conflict (station_id, ts) do update set pm10=excluded.pm10, pm25=excluded.pm25, fetched_at=now()""",
            [(r.station_id, pd.Timestamp(r.ts).to_pydatetime(), _f(r.pm10), _f(r.pm25)) for r in df.itertuples()],
        )
    return len(df)
