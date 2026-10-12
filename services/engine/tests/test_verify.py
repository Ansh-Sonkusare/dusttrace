import numpy as np
import pandas as pd
import pytest

from dusttrace import verify

NOW = pd.Timestamp("2026-10-12 04:00", tz="UTC")


def test_station_freshness_sorts_fresh_stale_and_silent():
    out = verify.station_freshness({
        "a": NOW - pd.Timedelta(hours=2),
        "b": NOW - pd.Timedelta(hours=110),
        "c": NOW - pd.Timedelta(days=45),
        "d": None,
    }, NOW)
    by = {r["station_id"]: r for r in out}
    assert by["a"]["status"] == "fresh" and by["a"]["age_h"] == 2
    assert by["b"]["status"] == "stale" and by["b"]["age_h"] == 110
    assert by["c"]["status"] == "silent" and by["d"]["status"] == "silent" and by["d"]["age_h"] is None
    assert [r["station_id"] for r in out] == ["a", "b", "c", "d"]  # freshest first


def test_input_shares_split_the_last_week_into_real_filled_synthetic():
    ts = pd.date_range(NOW - pd.Timedelta(hours=239), NOW, freq="h")
    rd = pd.DataFrame({"station_id": "s", "ts": ts, "pm10": 50.0, "synthetic": False, "filled": False})
    rd.loc[rd.index[-24:], "filled"] = True                 # last day filled
    rd.loc[rd.index[-48:-24], "synthetic"] = True           # day before synthetic
    s = verify.input_shares(rd, NOW)
    assert s["hours"] == 168  # only the last 7 days count
    assert s["real"] == pytest.approx(120 / 168, abs=1e-3)
    assert s["filled"] == pytest.approx(24 / 168, abs=1e-3) and s["synthetic"] == pytest.approx(24 / 168, abs=1e-3)


def test_input_shares_of_nothing_is_empty():
    assert verify.input_shares(pd.DataFrame(columns=["station_id", "ts", "pm10", "synthetic", "filled"]), NOW) == \
        {"hours": 0, "real": 0.0, "filled": 0.0, "synthetic": 0.0}


def test_cams_holdout_is_measured_on_days_the_correction_never_saw():
    ts = pd.date_range("2026-07-01", periods=24 * 90, freq="h", tz="UTC")
    c = 40 + 15 * np.sin(np.arange(len(ts)) / 24 * 2 * np.pi)
    obs = pd.Series(1.5 * c + 10, index=ts)
    obs.iloc[-24 * 30:] += 6  # the station drifts in the last month: the hold-out must see it
    h = verify.cams_holdout(obs, pd.Series(c, index=ts), test_days=30)
    assert h["hours"] == 24 * 30
    assert h["bias"] == pytest.approx(-6, abs=0.5) and h["mae"] == pytest.approx(6, abs=0.5)
    assert h["r"] > 0.99


def test_cams_holdout_needs_enough_history():
    ts = pd.date_range("2026-07-01", periods=24 * 20, freq="h", tz="UTC")
    assert verify.cams_holdout(pd.Series(1.0, index=ts), pd.Series(1.0, index=ts), test_days=30) is None


def test_problems_name_what_is_not_real():
    p = verify.problems(
        stations=[{"station_id": "a", "status": "stale", "age_h": 110}],
        shares={"hours": 168, "real": 0.3, "filled": 0.7, "synthetic": 0.0},
        weather_live=1.0, receptors_osm=233, sites_real=0)
    assert any("No real station" in x for x in p)
    assert any("70% of the last week" in x and "filled" in x for x in p)
    assert any("construction site" in x for x in p)
    assert not any("weather" in x.lower() for x in p)
    ok = verify.problems(stations=[{"station_id": "a", "status": "fresh", "age_h": 1}],
                         shares={"hours": 168, "real": 1.0, "filled": 0.0, "synthetic": 0.0},
                         weather_live=1.0, receptors_osm=233, sites_real=12)
    assert ok == []
