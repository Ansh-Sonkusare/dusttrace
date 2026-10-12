"""Database integration tests. They need TEST_DATABASE_URL (Postgres + PostGIS) and skip without it."""

import numpy as np
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
    ward = [72.835, 19.09, 72.91, 19.14]
    monkeypatch.setattr(ohsome, "area_by_cell", lambda cells, **k: {housing.in_box(cells, ward)[0]["id"]: 20_000.0})
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
