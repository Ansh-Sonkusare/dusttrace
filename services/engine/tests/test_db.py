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
