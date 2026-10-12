"""Database integration tests. They need TEST_DATABASE_URL (Postgres + PostGIS) and skip without it."""

import pandas as pd

from dusttrace import db, pipeline


def one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()


def test_migrations_are_safe_to_rerun(conn):
    assert db.migrate(conn) == db.migrate(conn)
    assert one(conn, "select count(*) from sites")[0] == 6


def test_synthetic_pipeline_end_to_end(conn, settings):
    report = pipeline.ingest(conn, settings, mode="synthetic", days=60)
    assert not report["weather"]["live"] and not report["readings"]["live"]

    out = pipeline.run(conn, settings)
    assert out["data_mode"] == "synthetic"
    assert one(conn, "select id from latest_run")[0] == out["run_id"]

    h = settings.horizon_hours
    assert one(conn, "select count(*) from forecasts where run_id=%s and station_id='ward'", (out["run_id"],))[0] == h
    assert one(conn, "select count(distinct station_id) from forecasts where run_id=%s", (out["run_id"],))[0] == 4
    assert one(conn, "select count(*) from safe_windows where run_id=%s", (out["run_id"],))[0] == 6 * h
    assert one(conn, "select count(*) from plumes where run_id=%s", (out["run_id"],))[0] == 6 * h
    statuses = {r[0] for r in conn.execute("select distinct status from safe_windows").fetchall()}
    assert statuses <= {"go", "caution", "avoid"}


def _reading(station, ts, pm10):
    return pd.DataFrame({"station_id": [station], "ts": [ts], "pm10": [pm10], "pm25": [None]})


def test_synthetic_never_overwrites_real(conn):
    ts = pd.Timestamp("2026-01-01 00:00", tz="UTC")
    db.write_readings(conn, _reading("seed-powai", ts, 100.0), synthetic=False)
    db.write_readings(conn, _reading("seed-powai", ts, 5.0), synthetic=True)
    assert one(conn, "select pm10, synthetic from readings where ts=%s", (ts,)) == (100.0, False)
    db.write_readings(conn, _reading("seed-powai", ts, 120.0), synthetic=False)
    assert one(conn, "select pm10 from readings where ts=%s", (ts,))[0] == 120.0

    w = pd.DataFrame({"ts": [ts], "wind_speed": [3.0], "wind_dir": [90.0], "blh": [500.0],
                      "temp": [25.0], "rh": [60.0], "precip": [0.0]})
    db.write_weather(conn, "K-East", w, ts, synthetic=False)
    db.write_weather(conn, "K-East", w.assign(wind_speed=9.9), ts, synthetic=True)
    assert one(conn, "select wind_speed, synthetic from weather_hourly where ts=%s", (ts,)) == (3.0, False)


def _real_station(conn, hours_ago_newest):
    db.upsert_station(conn, {"id": "openaq-1", "name": "Real station", "source": "openaq",
                             "lat": 19.11, "lon": 72.86}, "K-East")
    end = pipeline.now_hour() - pd.Timedelta(hours=hours_ago_newest)
    ts = pd.date_range(end=end, periods=24 * 30, freq="h", tz="UTC")
    df = pd.DataFrame({"station_id": "openaq-1", "ts": ts, "pm10": 90.0, "pm25": 40.0})
    db.write_readings(conn, df, synthetic=False)


def test_stale_real_station_leaves_the_run_on_synthetic_samples(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    _real_station(conn, hours_ago_newest=96)
    out = pipeline.run(conn, settings)
    assert "openaq-1" not in out["stations"]
    assert out["issued_at"] == pipeline.now_hour().isoformat()


def test_fresh_real_station_replaces_the_samples(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    _real_station(conn, hours_ago_newest=1)
    out = pipeline.run(conn, settings)
    assert out["stations"] == ["openaq-1"]
    assert out["data_mode"] == "mixed"  # real readings, synthetic weather


def test_osm_schools_and_hospitals_replace_the_demo_ones(conn):
    kinds = lambda: sorted({(r["kind"], r["source"]) for r in db.read_receptors(conn, "K-East").to_dict("records")})
    assert ("school", "seed") in kinds()
    db.upsert_receptors(conn, [{"id": "osm-node-1", "name": "Real School", "kind": "school", "lat": 19.11,
                                "lon": 72.86, "population": 800, "source": "osm"}], "K-East")
    conn.commit()
    assert kinds() == [("housing", "seed"), ("school", "osm")]


def test_run_audits_every_site_sensor(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    out = pipeline.run(conn, settings)
    rows = conn.execute("""select a.site_id, a.score, a.band, a.reasons, s.injected_fault
                             from sensor_audits a join site_sensors s on s.id = a.sensor_id
                            where a.run_id=%s order by a.site_id""", (out["run_id"],)).fetchall()
    assert [r[0] for r in rows] == ["A", "B", "C", "E", "F"]  # D, the unregistered debris yard, has no sensor
    by_site = {r[0]: r for r in rows}
    assert by_site["C"][4] == "too_clean" and by_site["C"][2] == "untrusted" and by_site["C"][3]
    assert by_site["A"][4] == "none" and by_site["A"][2] == "trusted"
    assert one(conn, "select bool_and(synthetic), count(*) > 0 from site_readings") == (True, True)
    bench = out["metrics"]["audit"]
    assert bench["precision"] >= 0.9 and bench["recall"] >= 0.85


def test_run_ranks_every_site_for_inspection(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    out = pipeline.run(conn, settings)
    rows = conn.execute("""select site_id, rank, score, components, reasons from inspection_rank
                            where run_id=%s order by rank""", (out["run_id"],)).fetchall()
    assert [r[1] for r in rows] == [1, 2, 3, 4, 5, 6]
    assert sorted(r[0] for r in rows) == list("ABCDEF")
    assert all(r[4] for r in rows)  # every site says why
    scores = [r[2] for r in rows]
    assert scores == sorted(scores, reverse=True)
    by_site = {r[0]: r for r in rows}
    assert by_site["D"][3]["unsensored"] > 0 and by_site["A"][3]["unsensored"] == 0
    assert by_site["C"][3]["trust"] > by_site["A"][3]["trust"]  # C's monitor is untrusted


def _case_actions(conn, site):
    return {(r[0], r[1]): r[2] for r in conn.execute(
        """select a.action, a.rule, a.status from case_actions a join cases c on c.id = a.case_id
            where c.site_id=%s and c.closed_at is null and a.phase='final'""", (site,)).fetchall()}


def test_run_opens_one_case_per_site_and_keeps_officer_decisions(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    pipeline.run(conn, settings)
    c = _case_actions(conn, "C")  # untrusted monitor: D5
    assert c[("FLAG_SENSOR_FOR_AUDIT", "D5")] == "done" and c[("ADD_TO_INSPECTION", "D5")] == "proposed"
    d = _case_actions(conn, "D")  # no monitor, one signal: D1 spot check, no enforcement
    assert d[("REQUEST_SPOT_CHECK", "D1")] == "requested" and ("ADD_TO_INSPECTION", "D6") not in d

    conn.execute("""update case_actions set status='approved', decided_by='test', decided_at=now()
                     where action='ADD_TO_INSPECTION' and case_id=(select id from cases where site_id='C')""")
    conn.commit()
    pipeline.run(conn, settings)
    assert one(conn, "select count(*) from cases where closed_at is null and site_id='C'")[0] == 1
    assert _case_actions(conn, "C")[("ADD_TO_INSPECTION", "D5")] == "approved"


def test_unanswered_request_escalates_under_d7(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    pipeline.run(conn, settings)
    conn.execute("""update case_actions set deadline = now() - interval '1 hour'
                     where action='REQUEST_SPOT_CHECK' and case_id=(select id from cases where site_id='D')""")
    conn.commit()
    pipeline.run(conn, settings)
    d = _case_actions(conn, "D")
    assert d[("REQUEST_SPOT_CHECK", "D1")] == "expired" and d[("ADD_TO_INSPECTION", "D7")] == "proposed"
    note = one(conn, "select what_changed from cases where site_id='D' and closed_at is null")[0]
    assert "none was assumed" in note


def test_confirmed_violations_raise_priority_and_reach_the_agent(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    first = pipeline.run(conn, settings)
    before = one(conn, "select components->>'violations' from inspection_rank where run_id=%s and site_id='A'",
                 (first["run_id"],))[0]
    assert float(before) == 0
    conn.execute("insert into inspections (site_id, outcome, note, officer) values ('A','violation','dry cutting','test')")
    conn.execute("insert into inspections (site_id, outcome, officer) values ('B','compliant','test')")
    conn.commit()
    a = db.site_signals(conn, "K-East")["A"]
    assert (a["reports"], a["violations"], a["confirmed_violation"]) == (0, 1, True)
    assert db.site_signals(conn, "K-East")["B"]["violations"] == 0
    second = pipeline.run(conn, settings)
    after = one(conn, "select components->>'violations', reasons from inspection_rank where run_id=%s and site_id='A'",
                (second["run_id"],))
    assert float(after[0]) > 0
    # A's case now counts the officer's finding as evidence
    sig = one(conn, "select signals from cases where site_id='A' and closed_at is null")
    assert sig is None or "officer inspection" in sig[0]


def test_run_scores_every_site_and_counts_citizen_reports(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    conn.execute("insert into citizen_reports (site_id, kind) values ('C','dry_excavation'), ('C','uncovered_truck')")
    conn.execute("insert into citizen_reports (site_id, kind, status) values ('C','other','verified'), ('B','other','rejected')")
    conn.commit()
    sig = db.site_signals(conn, "K-East")
    assert sig["C"]["reports"] == 3 and sig["C"]["verified_reports"] == 1 and sig["B"]["reports"] == 0
    out = pipeline.run(conn, settings)
    rows = {r[0]: r for r in conn.execute(
        "select site_id, score, band, components from dust_scores where run_id=%s", (out["run_id"],)).fetchall()}
    assert sorted(rows) == list("ABCDEF")
    assert rows["A"][1] > rows["C"][1]  # trusted monitor, no reports
    assert rows["D"][3]["trust"] == 0   # no monitor
    rank_c = one(conn, "select components->>'reports' from inspection_rank where run_id=%s and site_id='C'", (out["run_id"],))
    assert float(rank_c[0]) > 0


def test_accepted_plans_count_as_windows_followed(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    out = pipeline.run(conn, settings)
    conn.execute("insert into safe_windows (run_id, site_id, ts, status, reason) "
                 "select %s, 'A', now() + interval '30 days', 'avoid', 'test' "
                 "where not exists (select 1 from safe_windows where run_id=%s and site_id='A' and status='avoid')",
                 (out["run_id"], out["run_id"]))
    conn.commit()
    assert db.windows_followed(conn, "K-East")["A"] == 0.0
    conn.execute("insert into plan_acceptances (site_id, run_id, avoid_hours) values ('A', %s, 3)", (out["run_id"],))
    conn.commit()
    assert db.windows_followed(conn, "K-East")["A"] == 1.0
    second = pipeline.run(conn, settings)
    comp = one(conn, "select components->>'windows' from dust_scores where run_id=%s and site_id='A'", (second["run_id"],))
    assert float(comp[0]) == 20.0


def test_run_logs_ward_alerts_with_actions(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    out = pipeline.run(conn, settings)
    rows = conn.execute("select kind, site_id, case_id, title, action from alerts where run_id=%s", (out["run_id"],)).fetchall()
    sensor = [r for r in rows if r[0] == "sensor"]
    assert [r[1] for r in sensor] == ["C"] and sensor[0][2] is not None and sensor[0][4]
    assert all(r[4] for r in rows)
