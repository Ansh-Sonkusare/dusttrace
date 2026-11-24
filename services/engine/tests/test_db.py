"""Database integration tests. They need TEST_DATABASE_URL (Postgres + PostGIS) and skip without it."""

import numpy as np
import psycopg
import pytest
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
    assert set(bench["methods"]) == {"rules", "forest", "both"} and bench["n"] == 50
    assert set(bench["methods"]["forest"]["detected"]) == {"none", "flatline", "dropout", "too_clean", "drift", "rh_bias"}
    names = {r[0]: r[1] for r in conn.execute("select id, name from stations").fetchall()}
    st = bench["stations"]
    assert st and all(names[k] == v["name"] for k, v in st.items()) and sum(v["sensors"] for v in st.values()) == 50
    assert all(v["measured"] + v["next_station"] + v["interpolated"] == v["hours"] == 168 for v in st.values())
    assert bench["synthetic_ambient"] is True  # a synthetic run says so
    assert bench["nodes"] == []


def test_the_forest_compares_with_dusttrace_nodes_when_the_ward_has_them(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    hours = pd.date_range(end=pipeline.now_hour(), periods=24 * 8, freq="h", tz="UTC")
    _node_with_hours(conn, "node-marol", 19.117, 72.879, pipeline.now_hour(), {h: 70.0 for h in hours})
    assert pipeline.run(conn, settings)["metrics"]["audit"]["nodes"] == ["node-marol"]


def test_run_gives_simulated_sensors_a_calibration_date_and_names_their_station(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    out = pipeline.run(conn, settings)
    rows = conn.execute("""select n.calibrated_on, a.checks from site_sensors n
                             join sensor_audits a on a.sensor_id = n.id and a.run_id=%s""", (out["run_id"],)).fetchall()
    issued = pd.Timestamp(out["issued_at"]).date()
    assert rows and all(0 <= (issued - r[0]).days < 30 for r in rows)  # monthly, on schedule
    stations = {r[0] for r in conn.execute("select name from stations").fetchall()}
    assert all(r[1]["neighbour"]["station"] in stations and r[1]["calibration"]["ok"] for r in rows)
    assert all(r[1]["calibration"]["on"] == r[0].isoformat() for r in rows)  # the run keeps the date it used


def test_only_a_recent_scene_up_to_the_audited_week_counts_as_active(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    now = pipeline.now_hour()
    for site, d in (("A", now - pd.Timedelta(days=10)),    # recent: counts
                    ("B", now - pd.Timedelta(days=200)),   # found today, but an old scene
                    ("C", now + pd.Timedelta(days=5)),     # after the audited week
                    ("E", now)):                           # today: the id has no time, so it may be after the hour
        conn.execute("""insert into site_candidates (ward_id, scene_before, scene_after, lat, lon, area_m2, site_id)
                        values ('K-East', 'S2B_43QBV_20250101_0_L2A', %s, 19.1, 72.86, 9000, %s)""",
                     (f"S2B_43QBV_{d:%Y%m%d}_0_L2A", site))
    conn.commit()
    out = pipeline.run(conn, settings)
    checks = dict(conn.execute("select site_id, checks from sensor_audits where run_id=%s", (out["run_id"],)).fetchall())
    assert checks["A"]["work_signature"]["imagery"] == f"{now - pd.Timedelta(days=10):%Y-%m-%d}"
    assert all(checks[s]["work_signature"]["imagery"] is None for s in "BCE")


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


def test_an_officer_verdict_moves_the_dust_score_and_the_priority(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    ids = [r[0] for r in conn.execute(
        """insert into citizen_reports (site_id, ward_id, kind, lat, lon) values
           ('C', 'K-East', 'dry_excavation', 19.11, 72.87), ('C', 'K-East', 'other', null, null) returning id""").fetchall()]
    conn.commit()
    score = lambda run: one(conn, "select inputs, components from dust_scores where run_id=%s and site_id='C'", (run["run_id"],))
    priority = lambda run: float(one(conn, "select components->>'reports' from inspection_rank where run_id=%s and site_id='C'",
                                     (run["run_id"],))[0])
    before = pipeline.run(conn, settings)
    assert score(before)[0]["verified_reports"] == 0 and score(before)[1]["reports"] == 15
    conn.execute("update citizen_reports set status='verified' where id=%s", (ids[0],))
    conn.execute("update citizen_reports set status='rejected' where id=%s", (ids[1],))
    conn.commit()
    after = pipeline.run(conn, settings)
    assert score(after)[0]["verified_reports"] == 1 and score(after)[1]["reports"] == 10
    assert priority(after) == pytest.approx(priority(before) / 2)  # two reports counted, now one


def test_a_report_with_no_site_needs_a_place_and_its_photo_goes_with_it(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("insert into citizen_reports (ward_id, kind) values ('K-East', 'other')")
    conn.rollback()
    rid = one(conn, """insert into citizen_reports (ward_id, kind, lat, lon, accuracy_m)
                       values ('K-East', 'other', 19.11, 72.87, 12) returning id""")[0]
    conn.execute("insert into report_photos (report_id, jpeg, width, height) values (%s, %s, 64, 48)", (rid, b"\xff\xd8\xff\xd9"))
    conn.commit()
    assert one(conn, "select label, label_confidence, label_model from report_photos where report_id=%s", (rid,)) == (None, None, None)
    assert "C" in db.site_signals(conn, "K-East")
    conn.execute("delete from citizen_reports where id=%s", (rid,))
    assert one(conn, "select count(*) from report_photos")[0] == 0


def test_older_reports_get_their_site_s_ward(conn):
    conn.execute("insert into citizen_reports (site_id, kind) values ('C', 'other')")
    conn.commit()
    db.migrate(conn)
    assert one(conn, "select ward_id from citizen_reports where site_id='C'")[0] == "K-East"


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


def test_backtest_is_stored_and_labelled(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=90)
    out = pipeline.backtest(conn, settings, days=10)
    row = one(conn, "select data_mode, origins, metrics, stations from backtests where id=%s", (out["id"],))
    assert row[0] == "synthetic"          # no real readings in this database
    assert row[1] >= 7 and "1-24" in row[2] and row[3]



def test_backtest_uses_only_real_stations_when_there_are_some(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=90)
    db.upsert_station(conn, {"id": "openaq-9", "name": "Real", "source": "openaq", "lat": 19.11, "lon": 72.86}, "K-East")
    ts = pd.date_range(end=pipeline.now_hour(), periods=24 * 80, freq="h", tz="UTC")
    wave = 80 + 30 * np.sin(np.arange(len(ts)) / 24 * 2 * np.pi)
    db.write_readings(conn, pd.DataFrame({"station_id": "openaq-9", "ts": ts, "pm10": wave, "pm25": None}), synthetic=False)
    out = pipeline.backtest(conn, settings, days=10)
    assert out["stations"] == ["openaq-9"]
    assert out["data_mode"] == "mixed"  # real readings, synthetic weather


def test_run_records_when_real_station_data_stops(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    assert pipeline.run(conn, settings)["metrics"]["newest_real_reading"] is None
    _real_station(conn, hours_ago_newest=96)
    out = pipeline.run(conn, settings)
    newest = pd.Timestamp(out["metrics"]["newest_real_reading"])
    assert newest == pipeline.now_hour() - pd.Timedelta(hours=96)


def test_satellite_candidates_are_stored_and_reach_the_agent(conn, settings):
    cands = [{"lat": 19.1255, "lon": 72.8750, "area_m2": 9000, "site_id": "D"},
             {"lat": 19.1350, "lon": 72.8880, "area_m2": 16000, "site_id": None}]
    db.write_candidates(conn, "K-East", "S2_before", "S2_after", cands)
    db.write_candidates(conn, "K-East", "S2_before", "S2_after", cands)  # re-running replaces, not duplicates
    assert one(conn, "select count(*) from site_candidates")[0] == 2
    assert db.site_signals(conn, "K-East")["D"]["satellite"] is True
    assert db.site_signals(conn, "K-East")["A"]["satellite"] is False
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    pipeline.run(conn, settings)
    acts = _case_actions(conn, "D")
    assert ("REGISTER_UNSENSORED_SITE", "D6") in acts and ("REQUEST_SPOT_CHECK", "D1") not in acts


def _real_with_cams(conn, stale_hours, days=70):
    """A real station whose feed stopped `stale_hours` ago, with CAMS (reading 40% low) up to now."""
    db.upsert_station(conn, {"id": "openaq-7", "name": "Real seven", "source": "openaq", "lat": 19.11, "lon": 72.86}, "K-East")
    ts = pd.date_range(end=pipeline.now_hour() + pd.Timedelta(hours=48), periods=24 * days + 48, freq="h", tz="UTC")
    truth = 70 + 25 * np.sin(np.arange(len(ts)) / 24 * 2 * np.pi)
    real = pd.DataFrame({"station_id": "openaq-7", "ts": ts, "pm10": truth, "pm25": truth * 0.4})
    real = real[real["ts"] <= pipeline.now_hour() - pd.Timedelta(hours=stale_hours)]
    db.write_readings(conn, real, synthetic=False)
    db.write_cams(conn, pd.DataFrame({"station_id": "openaq-7", "ts": ts, "pm10": truth * 0.6, "pm25": truth * 0.25}))
    conn.commit()


def test_stale_station_is_filled_from_corrected_cams_not_samples(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    _real_with_cams(conn, stale_hours=96)
    out = pipeline.run(conn, settings)
    assert out["stations"] == ["openaq-7"]           # the real station, not the seed-* samples
    f = out["metrics"]["filled"]
    assert f["stations"] == 1 and 95 <= f["hours"] <= 97
    assert f["corrections"]["openaq-7"]["mae"] < 3     # CAMS was a clean 0.6x of the truth
    assert out["metrics"]["newest_real_reading"] is not None
    assert one(conn, "select count(*) from readings where station_id='openaq-7' and ts > now() - interval '90 hours'")[0] == 0


def test_long_dead_station_is_not_revived(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    _real_with_cams(conn, stale_hours=24 * 40)
    out = pipeline.run(conn, settings)
    assert "openaq-7" not in out["stations"] and out["metrics"]["filled"]["stations"] == 0


def test_real_osm_sites_join_the_run_without_false_d6(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    db.upsert_sites(conn, [{"id": "osm-way-101", "name": "Metro works", "activity": "excavation", "lat": 19.1172,
                            "lon": 72.8561, "area_m2": 9000, "source": "osm", "demo": False}], "K-East")
    conn.commit()
    out = pipeline.run(conn, settings)
    assert one(conn, "select count(*) from safe_windows where run_id=%s and site_id='osm-way-101'", (out["run_id"],))[0] == 48
    assert one(conn, "select components->>'unsensored' from inspection_rank where run_id=%s and site_id='osm-way-101'",
               (out["run_id"],))[0] in ("0", "0.0")
    acts = _case_actions(conn, "osm-way-101")
    assert ("REGISTER_UNSENSORED_SITE", "D6") not in acts and ("REQUEST_SPOT_CHECK", "D1") not in acts


def test_demo_sites_can_be_switched_off(conn, settings, monkeypatch):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    db.upsert_sites(conn, [{"id": "osm-way-101", "name": "Metro works", "activity": "excavation", "lat": 19.1172,
                            "lon": 72.8561, "area_m2": 9000, "source": "osm", "demo": False}], "K-East")
    conn.commit()
    monkeypatch.setenv("DUSTTRACE_DEMO_SITES", "0")
    out = pipeline.run(conn, settings)
    assert [r[0] for r in conn.execute("select distinct site_id from safe_windows where run_id=%s", (out["run_id"],))] == ["osm-way-101"]


def test_verify_stores_how_real_the_latest_run_is(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    out = pipeline.run(conn, settings)
    assert out["metrics"]["inputs"]["synthetic"] == 1.0  # every station hour this week is synthetic
    chk = pipeline.verify(conn, settings)
    row = one(conn, "select run_id, ok, shares->>'synthetic', jsonb_array_length(problems) from data_checks order by id desc limit 1")
    assert row[0] == out["run_id"] and row[1] is False and float(row[2]) == 1.0 and row[3] >= 2
    assert chk["weather_live"] == 0.0 and any("synthetic weather" in p for p in chk["problems"])
    assert chk["receptors_osm"] == 0 and chk["sites_real"] == 0


def test_verify_measures_the_cams_fill_on_real_stations(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    _real_with_cams(conn, stale_hours=96)
    pipeline.run(conn, settings)
    chk = pipeline.verify(conn, settings)
    st = {s["station_id"]: s for s in chk["stations"]}
    assert st["openaq-7"]["status"] == "stale" and 95 <= st["openaq-7"]["age_h"] <= 98
    h = chk["cams"]["openaq-7"]
    assert h["hours"] >= 24 * 29 and h["mae"] < 10


def test_real_housing_replaces_demo_housing_but_not_demo_schools(conn, settings, monkeypatch):
    from dusttrace import housing
    from dusttrace.sources import ohsome
    calls = []

    def fake_areas(cells, **k):
        calls.append(len(cells))
        return {c["id"]: (20_000.0 if i % 10 == 0 else 0.0) for i, c in enumerate(cells)}
    monkeypatch.setattr(ohsome, "area_by_cell", fake_areas)
    out = pipeline.load_housing_osm(conn, settings)
    assert out["receptors"] > 0 and out["census_2011"] == 823_885
    # spread over the ward's own cells, so the in-ward estimate adds back up to the census figure
    assert out["population_in_ward"] == pytest.approx(823_885, rel=0.01)
    kinds = db.read_receptors(conn, "K-East").groupby(["kind", "source"]).size().to_dict()
    assert ("housing", "seed") not in kinds and kinds[("housing", "osm")] == out["receptors"]
    assert ("school", "seed") in kinds  # no OSM schools yet, so the demo ones stay

    # a refresh with fewer homes drops cells that no longer qualify
    from dusttrace.config import load_seed
    ward = load_seed("K-East")["ward"]
    monkeypatch.setattr(ohsome, "area_by_cell", lambda cells, **k: {housing.in_ward(cells, ward)[0]["id"]: 20_000.0})
    out2 = pipeline.load_housing_osm(conn, settings)
    assert out2["receptors"] == 1
    assert one(conn, "select count(*) from receptors where kind='housing' and source='osm'")[0] == 1


def test_a_coarse_spike_at_a_real_station_reaches_the_agent(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    # A fresh real station next to Site A whose last hours show PM10 up far more than PM2.5.
    db.upsert_station(conn, {"id": "openaq-9", "name": "Chakala test", "source": "openaq", "lat": 19.1175, "lon": 72.8565}, "K-East")
    ts = pd.date_range(end=pipeline.now_hour(), periods=24 * 40, freq="h", tz="UTC")
    pm10 = np.full(len(ts), 60.0)
    pm25 = pm10 * 0.4
    pm10[-3:], pm25[-3:] = 170.0, 34.0
    db.write_readings(conn, pd.DataFrame({"station_id": "openaq-9", "ts": ts, "pm10": pm10, "pm25": pm25}), synthetic=False)
    conn.commit()
    out = pipeline.run(conn, settings)
    sig = out["metrics"]["signatures"]["openaq-9"]
    assert sig["signature"] in ("coarse_work", "coarse_night") and sig["ratio"] < 0.8 * sig["base_ratio"]
    hyp = one(conn, """select hypotheses from cases where site_id='A' and closed_at is null""")[0]
    assert hyp  # the case exists; the signature moved its causes
    assert "dry_windy_hours" in one(conn, "select metrics from runs where id=%s", (out["run_id"],))[0]


def _case_with_mist(conn, at):
    cid = conn.execute("""insert into cases (site_id, state, triggers) values ('A', 'ACTING', '{forecast_spike}')
                          returning id""").fetchone()[0]
    aid = conn.execute("""insert into case_actions (case_id, phase, action, type, route, rule, reason, status, at)
                          values (%s, 'final', 'SCHEDULE_MIST', 'preventive', 'auto', 'D2', 'test', 'done', %s)
                          returning id""", (cid, at.to_pydatetime())).fetchone()[0]
    return cid, aid


def _downwind_station(conn, now, during):
    """A real station 2 km east of Site A under a steady westerly, with 22 days of history."""
    db.upsert_station(conn, {"id": "openaq-11", "name": "East of A", "source": "openaq", "lat": 19.117, "lon": 72.875}, "K-East")
    ts = pd.date_range(end=now, periods=24 * 22, freq="h", tz="UTC")
    wx = pd.DataFrame({"ts": ts, "wind_speed": 3.0, "wind_dir": 270.0, "blh": 600.0, "temp": 30.0, "rh": 60.0, "precip": 0.0})
    db.write_weather(conn, "K-East", wx, now, synthetic=False)
    pm = pd.Series(80.0, index=ts)
    pm[(ts >= now - pd.Timedelta(hours=8)) & (ts < now - pd.Timedelta(hours=2))] = during
    db.write_readings(conn, pd.DataFrame({"station_id": "openaq-11", "ts": ts, "pm10": pm.to_numpy(), "pm25": pm.to_numpy() * 0.4}),
                      synthetic=False)
    conn.commit()


def test_a_verified_drop_closes_the_case(conn, settings):
    now = pipeline.now_hour()
    cid, aid = _case_with_mist(conn, now - pd.Timedelta(hours=8))
    _downwind_station(conn, now, during=55.0)
    out = pipeline.verify_actions(conn, "K-East", now)
    assert out["checked"] == 1 and out["drop"] == 1
    v = one(conn, "select station_id, verdict, round(change_pct) from verifications where action_id=%s", (aid,))
    assert v[0] == "openaq-11" and v[1] == "drop" and v[2] < -25
    assert one(conn, "select closed_at is not null, state from cases where id=%s", (cid,)) == (True, "DONE")
    assert pipeline.verify_actions(conn, "K-East", now)["checked"] == 0  # each action is checked once


def test_no_drop_keeps_the_case_open_and_a_dead_feed_is_insufficient(conn, settings):
    now = pipeline.now_hour()
    cid, aid = _case_with_mist(conn, now - pd.Timedelta(hours=8))
    _downwind_station(conn, now, during=84.0)
    assert pipeline.verify_actions(conn, "K-East", now)["no_drop"] == 1
    assert one(conn, "select closed_at from cases where id=%s", (cid,))[0] is None
    conn.execute("delete from verifications")
    conn.execute("delete from readings where station_id='openaq-11' and ts > %s", ((now - pd.Timedelta(hours=10)).to_pydatetime(),))
    conn.commit()
    assert pipeline.verify_actions(conn, "K-East", now)["insufficient"] == 1
    assert one(conn, "select verdict, note from verifications where action_id=%s", (aid,))[0] == "insufficient"


def test_compare_cams_stores_both_variants_on_one_window(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=90)
    rd = db.read_frame(conn, "select station_id, ts, pm10 from readings")
    rd["ts"] = pd.to_datetime(rd["ts"], utc=True)
    db.write_cams(conn, rd.assign(pm10=rd["pm10"].astype(float) * 0.6, pm25=None))
    conn.commit()
    out = pipeline.compare_cams(conn, settings, days=5)
    assert set(out["metrics"]) == {"without", "with_cams"} and out["origins"] >= 3
    kind, m = one(conn, "select kind, metrics from backtests where id=%s", (out["id"],))
    assert kind == "cams_feature" and m["with_cams"]["1-24"]["n"] == m["without"]["1-24"]["n"]


def test_runs_use_the_cams_features_when_cams_is_stored(conn, settings, monkeypatch):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    _real_with_cams(conn, stale_hours=2)  # a fresh real station with CAMS around it
    out = pipeline.run(conn, settings)
    assert one(conn, "select model from runs where id=%s", (out["run_id"],))[0].endswith("+cams")
    monkeypatch.setenv("DUSTTRACE_CAMS_FEATURES", "0")
    out = pipeline.run(conn, settings)
    assert not one(conn, "select model from runs where id=%s", (out["run_id"],))[0].endswith("+cams")


def test_an_insufficient_check_is_retried_when_the_feed_backfills(conn, settings):
    now = pipeline.now_hour()
    cid, aid = _case_with_mist(conn, now - pd.Timedelta(hours=8))
    _downwind_station(conn, now, during=55.0)
    window = conn.execute("""select ts, pm10 from readings where station_id='openaq-11' and ts >= %s and ts < %s""",
                          ((now - pd.Timedelta(hours=8)).to_pydatetime(), (now - pd.Timedelta(hours=2)).to_pydatetime())).fetchall()
    conn.execute("delete from readings where station_id='openaq-11' and ts >= %s", ((now - pd.Timedelta(hours=8)).to_pydatetime(),))
    conn.commit()
    assert pipeline.verify_actions(conn, "K-East", now)["insufficient"] == 1
    assert pipeline.verify_actions(conn, "K-East", now + pd.Timedelta(hours=1))["checked"] == 0  # not again within 6 h
    with conn.cursor() as cur:  # CPCB backfills the outage
        cur.executemany("insert into readings (station_id, ts, pm10, synthetic) values ('openaq-11', %s, %s, false)", window)
    conn.commit()
    out = pipeline.verify_actions(conn, "K-East", now + pd.Timedelta(hours=7))
    assert out["drop"] == 1
    assert one(conn, "select count(*), max(verdict) from verifications where action_id=%s", (aid,)) == (1, "drop")


def test_a_station_belongs_to_the_nearer_ward_whoever_finds_it_first(conn, settings):
    from dusttrace.config import load_seed
    db.upsert_seed(conn, load_seed("P-North"))
    malad = {"id": "openaq-77", "name": "Malad West", "source": "openaq", "lat": 19.1864, "lon": 72.8485}
    db.upsert_station(conn, malad, "K-East")   # K-East's wide search finds it first
    db.upsert_station(conn, malad, "P-North")
    assert one(conn, "select ward_id from stations where id='openaq-77'")[0] == "P-North"
    chakala = {"id": "openaq-78", "name": "Chakala", "source": "openaq", "lat": 19.1102, "lon": 72.8622}
    db.upsert_station(conn, chakala, "K-East")
    db.upsert_station(conn, chakala, "P-North")  # P-North's search reaching it doesn't take it
    assert one(conn, "select ward_id from stations where id='openaq-78'")[0] == "K-East"
    assert one(conn, "select boundary->>'type' from wards where id='P-North'")[0] == "Polygon"
    # Order doesn't matter: Powai, found first (and only) by P-North's wider search, is still K-East's.
    powai = {"id": "openaq-79", "name": "Powai", "source": "openaq", "lat": 19.1375, "lon": 72.9151}
    db.upsert_station(conn, powai, "P-North")
    assert one(conn, "select ward_id from stations where id='openaq-79'")[0] == "K-East"


def test_p_north_runs_end_to_end_with_no_demo_sites(conn, settings):
    import dataclasses
    from dusttrace.config import load_seed
    pn = dataclasses.replace(settings, ward_id="P-North")
    db.upsert_seed(conn, load_seed("P-North"))
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    pipeline.ingest(conn, pn, mode="synthetic", days=60)
    out = pipeline.run(conn, pn)
    assert out["data_mode"] == "synthetic"
    assert one(conn, "select ward_id from runs where id=%s", (out["run_id"],))[0] == "P-North"
    assert one(conn, "select count(*) from safe_windows where run_id=%s", (out["run_id"],))[0] == 0  # no sites yet
    k = pipeline.run(conn, settings)  # K-East is untouched by P-North's run
    assert one(conn, "select count(distinct site_id) from safe_windows where run_id=%s", (k["run_id"],))[0] == 6


def test_osm_sites_outside_the_ward_or_gone_from_osm_are_retired(conn, settings, monkeypatch):
    from dusttrace.sources import ohsome
    inside = {"id": "osm-way-1", "name": "Inside K/E", "activity": "excavation", "lat": 19.1172, "lon": 72.8561,
              "area_m2": 9000, "source": "osm", "demo": False}
    outside = {**inside, "id": "osm-way-2", "name": "Goregaon, P/S ward", "lat": 19.1689, "lon": 72.8427}
    monkeypatch.setattr(pipeline, "fetch_osm_sites", lambda bbox: ([inside, outside], "ohsome"))
    db.upsert_sites(conn, [outside], "K-East")  # loaded by an earlier, box-only pull
    conn.commit()
    assert pipeline.load_sites_osm(conn, settings) == 1
    rows = dict(conn.execute("select id, active from sites where source='osm'").fetchall())
    assert rows == {"osm-way-1": True, "osm-way-2": False}
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    out = pipeline.run(conn, settings)
    planned = {r[0] for r in conn.execute("select distinct site_id from safe_windows where run_id=%s", (out["run_id"],))}
    assert "osm-way-1" in planned and "osm-way-2" not in planned


def test_two_wards_housing_does_not_collide(conn, settings, monkeypatch):
    import dataclasses
    from dusttrace.config import load_seed
    from dusttrace.sources import ohsome
    db.upsert_seed(conn, load_seed("P-North"))
    monkeypatch.setattr(ohsome, "area_by_cell", lambda cells, **k: {c["id"]: 20_000.0 for c in cells})
    k = pipeline.load_housing_osm(conn, settings)
    p = pipeline.load_housing_osm(conn, dataclasses.replace(settings, ward_id="P-North"))
    counts = dict(conn.execute("""select ward_id, count(*) from receptors where kind='housing' and source='osm'
                                  group by ward_id""").fetchall())
    assert counts == {"K-East": k["receptors"], "P-North": p["receptors"]}
    # each ward's homes sit in its own box
    lat = dict(conn.execute("select ward_id, avg(lat) from receptors where kind='housing' and source='osm' group by 1").fetchall())
    assert float(lat["K-East"]) < 19.15 < float(lat["P-North"])


def test_a_node_is_provisioned_with_a_one_time_key_stored_only_as_a_hash(conn, settings):
    import hashlib
    key = db.add_node(conn, {"id": "node-marol-school", "name": "Marol school roof", "host_kind": "school",
                             "lat": 19.1172, "lon": 72.8790}, "K-East")
    conn.commit()
    row = one(conn, "select key_hash, active, ward_id from nodes where id='node-marol-school'")
    assert row[0] == hashlib.sha256(key.encode()).hexdigest() and key not in row[0]
    assert row[1] is True and row[2] == "K-East" and len(key) >= 32
    # Re-provisioning rotates the key: the old one stops matching.
    key2 = db.add_node(conn, {"id": "node-marol-school", "name": "Marol school roof", "host_kind": "school",
                              "lat": 19.1172, "lon": 72.8790}, "K-East")
    assert key2 != key and one(conn, "select key_hash from nodes where id='node-marol-school'")[0] == hashlib.sha256(key2.encode()).hexdigest()


def _node_with_hours(conn, node_id, lat, lon, now, pm10_by_hour, receptor_id=None):
    """A node whose minute readings average to the given PM10 per hour (corrected = raw at RH 0)."""
    db.add_node(conn, {"id": node_id, "name": node_id, "host_kind": "school", "lat": lat, "lon": lon,
                       "receptor_id": receptor_id}, "K-East")
    with conn.cursor() as cur:
        cur.executemany(
            """insert into node_readings (node_id, ts, pm25_raw, pm10_raw, rh, pm25_corrected, pm10_corrected)
               values (%s, %s, %s, %s, 0, %s, %s)""",
            [(node_id, (h + pd.Timedelta(minutes=m)).to_pydatetime(), v * 0.4, v, v * 0.4, v)
             for h, v in pm10_by_hour.items() for m in (0, 20, 40)])
    conn.commit()


def test_a_fix_check_uses_a_node_beside_the_site(conn, settings):
    now = pipeline.now_hour()
    cid, aid = _case_with_mist(conn, now - pd.Timedelta(hours=8))
    ts = pd.date_range(end=now, periods=24 * 22, freq="h", tz="UTC")
    wx = pd.DataFrame({"ts": ts, "wind_speed": 3.0, "wind_dir": 270.0, "blh": 600.0, "temp": 30.0, "rh": 60.0, "precip": 0.0})
    db.write_weather(conn, "K-East", wx, now, synthetic=False)
    window = (ts >= now - pd.Timedelta(hours=8)) & (ts < now - pd.Timedelta(hours=2))
    _node_with_hours(conn, "node-east-of-a", 19.117, 72.861, now,   # ~0.5 km east of Site A, downwind
                     {t: (50.0 if w else 80.0) for t, w in zip(ts, window)})
    out = pipeline.verify_actions(conn, "K-East", now)
    assert out["drop"] == 1
    v = one(conn, "select node_id, station_id, verdict from verifications where action_id=%s", (aid,))
    assert v == ("node-east-of-a", None, "drop")


def _past_exposure(conn, site, receptor, ts, issued):
    """The forecast in force at `ts` (a run issued at `issued`) had `site`'s plume over `receptor`."""
    run_id = db.create_run(conn, "K-East", issued.to_pydatetime(), "synthetic", "test", {})
    conn.execute("insert into exposures (run_id, site_id, receptor_id, ts, conc) values (%s,%s,%s,%s,30)",
                 (run_id, site, receptor, ts.to_pydatetime()))
    conn.commit()


def test_the_receptor_signal_goes_to_the_site_whose_plume_was_there_when_the_node_read_high(conn, settings):
    now = pipeline.now_hour()
    rid = one(conn, "select id from receptors where kind='school' limit 1")[0]
    hot_hour = now - pd.Timedelta(hours=2)
    _node_with_hours(conn, "node-at-school", 19.11, 72.86, now, {hot_hour: 150.0}, receptor_id=rid)
    _past_exposure(conn, "A", rid, hot_hour, issued=now - pd.Timedelta(hours=6))                       # A's plume, that hour
    _past_exposure(conn, "B", rid, now - pd.Timedelta(hours=20), issued=now - pd.Timedelta(hours=24))  # B's, a day earlier
    # Hourly runs: one issued exactly at the hot hour forecasts only the hours after it, so it isn't the
    # forecast in force at that hour.
    _past_exposure(conn, "C", rid, hot_hour + pd.Timedelta(hours=1), issued=hot_hour)
    assert db.hot_node_sites(conn, "K-East", now) == {"A"}


def test_a_hot_node_reaches_the_agent_through_the_run(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    now = pipeline.now_hour()
    rid = one(conn, "select id from receptors where kind='school' limit 1")[0]
    hot_hour = now - pd.Timedelta(hours=1)
    _node_with_hours(conn, "node-at-school", 19.11, 72.86, now, {hot_hour: 150.0}, receptor_id=rid)
    _past_exposure(conn, "D", rid, hot_hour, issued=now - pd.Timedelta(hours=5))  # D always has a case (unsensored)
    pipeline.run(conn, settings)
    assert "receptor monitor" in one(conn, "select signals from cases where site_id='D' and closed_at is null")[0]


def test_a_node_without_history_does_not_take_the_verdict_from_a_station(conn, settings):
    now = pipeline.now_hour()
    cid, aid = _case_with_mist(conn, now - pd.Timedelta(hours=8))
    _downwind_station(conn, now, during=55.0)  # real station 2 km downwind, 22 days of history
    db.add_node(conn, {"id": "node-new", "name": "New node", "host_kind": "school", "lat": 19.117, "lon": 72.861}, "K-East")
    conn.commit()                              # 0.5 km downwind, no readings yet
    assert pipeline.verify_actions(conn, "K-East", now)["drop"] == 1
    assert one(conn, "select station_id, node_id from verifications where action_id=%s", (aid,)) == ("openaq-11", None)


# Issue #56: D8, D9 and D10 on measured station data.
WORKS = {"id": "osm-way-101", "name": "Metro works", "activity": "excavation", "lat": 19.1172, "lon": 72.8561,
         "area_m2": 9000, "source": "osm", "demo": False}


def _background_stations(conn, ts):
    """Two real stations 5-6 km away at 60 µg/m³: the rest of the network a local exceedance must stand above."""
    for sid, lat, lon in (("openaq-24", 19.085, 72.84), ("openaq-25", 19.16, 72.92)):
        db.upsert_station(conn, {"id": sid, "name": sid, "source": "openaq", "lat": lat, "lon": lon}, "K-East")
        db.write_readings(conn, pd.DataFrame({"station_id": sid, "ts": ts, "pm10": 60.0, "pm25": 24.0}), synthetic=False)


def _works_upwind_of_a_station(conn, days_ago, ratio=0.2, synthetic=False):
    """A real OSM site 300 m west of a real station under a measured westerly, so its plume adds 20-40 µg/m³
    there. The station's PM10 sits at 60 (PM2.5/PM10 0.4) except one hour on each of `days_ago`, when it reads
    140 with PM2.5/PM10 `ratio`."""
    db.upsert_sites(conn, [WORKS], "K-East")
    db.upsert_station(conn, {"id": "openaq-21", "name": "East of the works", "source": "openaq",
                             "lat": 19.1172, "lon": 72.8590}, "K-East")
    now = pipeline.now_hour()
    ts = pd.date_range(end=now, periods=24 * 40, freq="h", tz="UTC")
    wx = pd.DataFrame({"ts": ts[-24 * 9:], "wind_speed": 3.0, "wind_dir": 270.0, "blh": 600.0, "temp": 30.0,
                       "rh": 60.0, "precip": 0.0})
    db.write_weather(conn, "K-East", wx, now, synthetic=False)
    pm10, pm25 = pd.Series(60.0, index=ts), pd.Series(24.0, index=ts)
    for d in days_ago:
        t = now - pd.Timedelta(days=d, hours=2)
        pm10[t], pm25[t] = 140.0, 140.0 * ratio
    db.write_readings(conn, pd.DataFrame({"station_id": "openaq-21", "ts": ts, "pm10": pm10.to_numpy(),
                                          "pm25": pm25.to_numpy()}), synthetic=synthetic)
    _background_stations(conn, ts)
    conn.commit()
    return now


def _report(conn, site="osm-way-101", ago="1 day"):
    conn.execute("insert into citizen_reports (site_id, kind, at) values (%s, 'dry_excavation', now() - %s::interval)",
                 (site, ago))
    conn.commit()


def test_d8_three_days_of_measured_exceedances_downwind_propose_a_notice_to_the_officer(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    _works_upwind_of_a_station(conn, days_ago=[1, 3, 5])
    _report(conn)  # D1: a second, independent signal
    out = pipeline.run(conn, settings)
    ev = one(conn, "select metrics->'evidence'->'osm-way-101' from runs where id=%s", (out["run_id"],))[0]
    assert ev["exceedances_7d"] == 3 and ev["non_construction"] is False and len(ev["days"]) == 3
    hours = [h for d in ev["days"].values() for h in d["hours"]]  # the station hours and winds behind each day
    assert {(h["station"], h["pm10"], h["background"], h["wind_dir"], h["wind_speed"]) for h in hours} == \
        {("East of the works", 140.0, 60.0, 270, 3.0)}
    # What the Cases page lists: the ward's open cases with their actions; a proposed one gets Approve / Decline.
    rows = conn.execute("""select c.state, a.route, a.rule, a.status, a.reason from cases c join sites s on s.id = c.site_id
                             join case_actions a on a.case_id = c.id
                            where c.closed_at is null and s.ward_id='K-East' and c.site_id='osm-way-101'
                              and a.phase='final' and a.action='ISSUE_NOTICE'""").fetchall()
    assert len(rows) == 1
    state, route, rule, status, reason = rows[0]
    assert (state, route, rule, status) == ("APPROVAL_ROUTING", "L1", "D8", "proposed")
    assert "on 3 days in 7" in reason and "East of the works 140 µg/m³ against 60 µg/m³ at the other stations" in reason
    assert "from this site's plume" in reason and "wind from 270° at 3.0 m/s" in reason
    assert "station attribution" in one(conn, "select signals from cases where site_id='osm-way-101' and closed_at is null")[0]


def test_city_wide_haze_is_not_attributed_to_a_site(conn, settings):
    now = _works_upwind_of_a_station(conn, days_ago=[1, 3, 5])
    sites = db.read_sites(conn, "K-East")
    ev, _ = pipeline.rule_evidence(conn, "K-East", sites, now, db.site_signals(conn, "K-East"))
    assert ev["osm-way-101"]["exceedances_7d"] == 3 and ev["osm-way-101"]["exceedance_days"][0]["background"] == 60.0
    # The same three hours, but the whole network was as high: regional haze, nothing local to attribute.
    hazy = [(now - pd.Timedelta(days=d, hours=2)).to_pydatetime() for d in (1, 3, 5)]
    conn.execute("update readings set pm10 = 140 where station_id in ('openaq-24', 'openaq-25') and ts = any(%s)", (hazy,))
    conn.commit()
    ev, _ = pipeline.rule_evidence(conn, "K-East", sites, now, db.site_signals(conn, "K-East"))
    assert ev["osm-way-101"]["exceedances_7d"] == 0


def test_d8_two_days_of_measured_exceedances_are_not_enough(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    _works_upwind_of_a_station(conn, days_ago=[1, 3])
    _report(conn)
    pipeline.run(conn, settings)
    assert not conn.execute("""select 1 from case_actions a join cases c on c.id = a.case_id
                                where c.site_id='osm-way-101' and a.action='ISSUE_NOTICE'""").fetchall()
    assert "repeat_exceedance" not in one(conn, "select triggers from cases where site_id='osm-way-101' and closed_at is null")[0]


def test_d8_never_counts_synthetic_or_cams_filled_hours(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    _works_upwind_of_a_station(conn, days_ago=[1, 3, 5], synthetic=True)  # the same spikes, but synthetic
    # A real station beside it whose feed stopped 4 days ago; CAMS since then corrects to about 300 µg/m³.
    db.upsert_station(conn, {"id": "openaq-22", "name": "Stale beside it", "source": "openaq",
                             "lat": 19.1172, "lon": 72.8590}, "K-East")
    now = pipeline.now_hour()
    ts = pd.date_range(end=now, periods=24 * 70, freq="h", tz="UTC")
    truth = pd.Series(np.where(ts > now - pd.Timedelta(hours=96), 300.0, 60.0 + 10 * np.sin(np.arange(len(ts)) / 24 * 2 * np.pi)), index=ts)
    real = truth[ts <= now - pd.Timedelta(hours=96)]
    db.write_readings(conn, pd.DataFrame({"station_id": "openaq-22", "ts": real.index, "pm10": real.to_numpy(),
                                          "pm25": real.to_numpy() * 0.4}), synthetic=False)
    db.write_cams(conn, pd.DataFrame({"station_id": "openaq-22", "ts": ts, "pm10": truth.to_numpy() * 0.6, "pm25": None}))
    _report(conn)
    conn.commit()
    out = pipeline.run(conn, settings)
    assert out["metrics"]["filled"]["stations"] == 1  # the stale station was filled, far above 100 ...
    triggers = one(conn, "select triggers from cases where site_id='osm-way-101' and closed_at is null")[0]
    assert "repeat_exceedance" not in triggers        # ... and neither kind of hour counted
    sites = db.read_sites(conn, "K-East")
    ev, att = pipeline.rule_evidence(conn, "K-East", sites, now, db.site_signals(conn, "K-East"))
    assert ev["osm-way-101"]["exceedances_7d"] == 0 and att["osm-way-101"] == []


def test_d10_pm25_carried_exceedances_are_referred_and_the_case_closes_once_approved(conn, settings):
    from dusttrace import agent
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    _works_upwind_of_a_station(conn, days_ago=[1, 3, 5], ratio=0.75)  # PM2.5 carried every spike: combustion
    _report(conn)
    pipeline.run(conn, settings)
    acts = _case_actions(conn, "osm-way-101")
    assert acts[("REFER_NON_CONSTRUCTION", "D10")] == "proposed"
    assert not {a for a, _ in acts} & (agent.SITE_ACTIONS | agent.ENFORCEMENT_FROM_CAUSE)
    reason = one(conn, """select a.reason from case_actions a join cases c on c.id = a.case_id where c.site_id='osm-way-101'
                           and a.action='REFER_NON_CONSTRUCTION'""")[0]
    assert "PM2.5 carried the PM10 spikes on 3 of the 3 days" in reason and "East of the works" in reason

    conn.execute("""update case_actions set status='approved', decided_by='test', decided_at=now()
                     where action='REFER_NON_CONSTRUCTION'""")
    conn.commit()
    pipeline.run(conn, settings)
    closed = one(conn, """select c.id, c.state, c.closed_at is not null from cases c where c.site_id='osm-way-101'""")
    assert closed[1:] == ("DONE", True)
    close = one(conn, "select route, rule, status from case_actions where case_id=%s and action='CLOSE_NO_ACTION'", (closed[0],))
    assert close == ("auto", "D10", "done")
    pipeline.run(conn, settings)  # still referred: no new case is opened for the site
    assert one(conn, "select count(*) from cases where site_id='osm-way-101'")[0] == 1


def test_a_verified_drop_is_recorded_as_close_no_action(conn, settings):
    now = pipeline.now_hour()
    cid, _ = _case_with_mist(conn, now - pd.Timedelta(hours=8))
    _downwind_station(conn, now, during=55.0)
    pipeline.verify_actions(conn, "K-East", now)
    row = one(conn, "select route, rule, status, reason from case_actions where case_id=%s and action='CLOSE_NO_ACTION'", (cid,))
    assert row[:3] == ("auto", "verified drop", "done") and row[3].startswith("Verified: PM10 at East of A")


def _accepted_avoid_hour(conn, site, hour, accepted=True):
    """A run issued 2 h before `hour` gave `site` an Avoid window at `hour`; its manager accepted the plan an hour before."""
    run_id = db.create_run(conn, "K-East", (hour - pd.Timedelta(hours=2)).to_pydatetime(), "live", "test", {})
    conn.execute("insert into safe_windows (run_id, site_id, ts, status, reason) values (%s,%s,%s,'avoid','test')",
                 (run_id, site, hour.to_pydatetime()))
    if accepted:
        conn.execute("insert into plan_acceptances (site_id, run_id, avoid_hours, accepted_at) values (%s,%s,1,%s)",
                     (site, run_id, (hour - pd.Timedelta(hours=1)).to_pydatetime()))


def test_d8_a_window_counts_as_ignored_only_on_measured_evidence_at_the_gate(conn, settings):
    now = pipeline.now_hour()
    day = lambda k: now.normalize() - pd.Timedelta(days=k) + pd.Timedelta(hours=5)  # 10:30 IST, k days ago
    db.add_node(conn, {"id": "node-gate-a", "name": "Gate of A", "host_kind": "site_gate", "site_id": "A",
                       "lat": 19.1172, "lon": 72.8565}, "K-East")
    db.upsert_station(conn, {"id": "openaq-23", "name": "Ambient", "source": "openaq", "lat": 19.11, "lon": 72.87}, "K-East")
    gate, ambient = {}, {}
    for k in (1, 2, 3, 4, 5):
        _accepted_avoid_hour(conn, "A", day(k), accepted=(k != 4))
        gate[day(k)], ambient[day(k)] = 200.0, 60.0
    gate[day(3)] = 100.0           # under twice the ambient: followed
    del ambient[day(5)]            # no measured ambient that hour: no evidence, so not ignored
    _accepted_avoid_hour(conn, "B", day(1))  # B has no gate node: silence is not evidence
    with conn.cursor() as cur:
        cur.executemany("""insert into node_readings (node_id, ts, pm25_raw, pm10_raw, rh, pm25_corrected, pm10_corrected)
                           values ('node-gate-a', %s, %s, %s, 0, %s, %s)""",
                        [(t.to_pydatetime(), v * 0.4, v, v * 0.4, v) for t, v in gate.items()])
        cur.executemany("insert into readings (station_id, ts, pm10, synthetic) values ('openaq-23', %s, %s, false)",
                        [(t.to_pydatetime(), v) for t, v in ambient.items()])
    conn.commit()
    # Day 1 and day 2 count; day 3 was under 2x, day 4's plan wasn't accepted, day 5 has no ambient.
    assert db.ignored_windows(conn, "K-East", now) == {"A": 2}
    assert db.ignored_windows(conn, "K-East", day(2)) == {"A": 1}  # nothing after now is visible
    ev, _ = pipeline.rule_evidence(conn, "K-East", db.read_sites(conn, "K-East"), now, db.site_signals(conn, "K-East"))
    assert ev["A"]["ignored_windows"] == 2 and ev["B"]["ignored_windows"] == 0


def test_replay_sees_nothing_after_its_as_of_hour_and_writes_nothing(conn, settings):
    now = _works_upwind_of_a_station(conn, days_ago=[1, 3, 5])
    _report(conn, ago="1 day")
    before = one(conn, "select count(*) from cases")[0]
    past = pipeline.replay_rules(conn, settings, now - pd.Timedelta(days=2))
    site = next(s for s in past["sites"] if s["site_id"] == "osm-way-101")
    assert site["exceedance_days"] == 2 and all(h["ts"] <= now - pd.Timedelta(days=2) for h in site["hours"])
    assert "citizen reports" not in site["signals"] and not any(a["action"] == "ISSUE_NOTICE" for a in site["actions"])
    today = next(s for s in pipeline.replay_rules(conn, settings, now)["sites"] if s["site_id"] == "osm-way-101")
    assert today["exceedance_days"] == 3
    assert {"action": "ISSUE_NOTICE", "route": "L1", "rule": "D8", "status": "proposed"}.items() <= \
        next(a for a in today["actions"] if a["action"] == "ISSUE_NOTICE").items()
    assert one(conn, "select count(*) from cases")[0] == before


def test_d9_stop_work_is_proposed_to_l2_with_a_confirmed_violation_d8_and_a_school_exposed(conn, settings):
    pipeline.ingest(conn, settings, mode="synthetic", days=60)
    now = _works_upwind_of_a_station(conn, days_ago=[1, 3, 5])
    rid = one(conn, "select id from receptors where kind='school' limit 1")[0]
    hot_hour = now - pd.Timedelta(hours=1)
    _node_with_hours(conn, "node-at-school", 19.11, 72.86, now, {hot_hour: 150.0}, receptor_id=rid)
    _past_exposure(conn, "osm-way-101", rid, hot_hour, issued=now - pd.Timedelta(hours=5))
    pipeline.run(conn, settings)
    first = _case_actions(conn, "osm-way-101")
    # The school's node and the station both tie the dust to the site through the wind alone: no notice yet.
    assert ("RECOMMEND_STOP_WORK", "D9") not in first and ("ISSUE_NOTICE", "D8") not in first
    conn.execute("insert into inspections (site_id, outcome, note, officer) values ('osm-way-101','violation','dry cutting','test')")
    conn.commit()
    pipeline.run(conn, settings)
    acts = _case_actions(conn, "osm-way-101")
    assert acts[("ISSUE_NOTICE", "D8")] == "proposed" and acts[("RECOMMEND_STOP_WORK", "D9")] == "proposed"
    stop = one(conn, """select a.route from case_actions a join cases c on c.id = a.case_id
                         where c.site_id='osm-way-101' and a.action='RECOMMEND_STOP_WORK' and a.phase='final'""")
    assert stop[0] == "L2"
    assert "node_at_school_or_hospital" in one(conn, "select triggers from cases where site_id='osm-way-101' and closed_at is null")[0]
