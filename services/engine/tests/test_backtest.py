import numpy as np
import pandas as pd
import pytest

from dusttrace import backtest, forecast
from dusttrace.sources import synthetic

START = pd.Timestamp("2026-01-01 00:00", tz="UTC")


@pytest.fixture(scope="module")
def data():
    wx = synthetic.weather(START - pd.Timedelta(days=150), START + pd.Timedelta(days=12))
    rd = synthetic.readings(wx, ["s1", "s2"])
    return rd, wx


def test_forecast_at_an_origin_ignores_later_readings(data):
    rd, wx = data
    past = rd[rd["ts"] < START]
    model = forecast.train(past, wx, horizon=24)
    origin = START + pd.Timedelta(days=3)
    clean = rd[rd["ts"] <= origin]
    poisoned = rd.copy()
    poisoned.loc[poisoned["ts"] > origin, "pm10"] = 9999.0  # what happened later must not matter
    a = forecast.predict(model, clean, wx, origin, 24)
    b = forecast.predict(model, poisoned, wx, origin, 24)
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))


def test_backtest_trains_only_on_the_past_and_reports_by_horizon(data):
    rd, wx = data
    res = backtest.run(rd, wx, START, START + pd.Timedelta(days=8), horizon=48, step_h=24)
    assert res.train_end == START and res.origins == 7  # daily, Jan 1 to Jan 7: the last leaves 48 h to score
    assert set(res.metrics) == {"1-24", "25-48"}
    for m in res.metrics.values():
        assert m["n"] > 0 and m["mae_model"] >= 0 and 0 <= m["coverage_10_90"] <= 1
    assert res.spike_day is not None and "p_exceed_max" in res.spike_day


def test_metrics_on_a_toy_series():
    rows = pd.DataFrame({
        "h": [1, 2, 30, 31],
        "pred": [100.0, 110.0, 50.0, 60.0], "lo": [90.0, 100.0, 40.0, 70.0], "hi": [120.0, 130.0, 60.0, 80.0],
        "p": [0.9, 0.2, 0.1, 0.1], "actual": [105.0, 120.0, 55.0, 50.0], "persist": [95.0, 95.0, 45.0, 45.0],
    })
    m = backtest.metrics(rows, threshold=100.0)
    assert m["1-24"]["mae_model"] == 7.5 and m["1-24"]["mae_persistence"] == 17.5
    assert m["1-24"]["f1_exceed_model"] == pytest.approx(2 / 3, abs=1e-3)   # caught 1 of 2 exceedances, no false alarm
    assert m["1-24"]["f1_exceed_persistence"] == 0
    assert m["25-48"]["coverage_10_90"] == 0.5
    assert m["25-48"]["n"] == 2


def test_outage_replay_scores_the_fill_against_real_data(data):
    rd, wx = data
    rd = rd.dropna(subset=["pm10"])
    model_pm = rd.groupby("ts")["pm10"].mean() * 0.6  # a model that reads 40% low
    cams_df = pd.concat([pd.DataFrame({"station_id": s, "ts": model_pm.index, "pm10": model_pm.to_numpy()})
                         for s in rd["station_id"].unique()])
    res = backtest.outage_replay(rd, cams_df, wx, START, START + pd.Timedelta(days=6), outage_h=96)
    assert set(res["metrics"]) == {"real", "filled", "cams_direct", "last_value"}
    for m in res["metrics"].values():
        assert set(m) == {"1-24", "25-48"} and m["1-24"]["n"] > 0
    assert res["outage_hours"] == 96 and res["origins"] == 5
