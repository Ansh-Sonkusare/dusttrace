"""The PRD F3 forecast: 72 h hourly PM10, P(24 h mean PM10 > 100) for days 1-3, festival and upwind-site inputs."""

import numpy as np
import pandas as pd
import pytest

from dusttrace import backtest, festivals, forecast
from dusttrace.sources import synthetic

END = pd.Timestamp("2026-01-10T00:00Z")


@pytest.fixture(scope="module")
def year():
    wx = synthetic.weather(END - pd.Timedelta(days=120), END + pd.Timedelta(hours=72))
    rd = synthetic.readings(wx[wx["ts"] <= END], ["s1", "s2"])
    return rd, wx


STATIONS = pd.DataFrame({"id": ["s1", "s2"], "lat": [19.10, 19.12], "lon": [72.85, 72.87]})


def _sites(lat, lon, area_m2):
    return pd.DataFrame({"lat": lat, "lon": lon, "area_m2": area_m2})


@pytest.fixture(scope="module")
def up():
    return forecast.upwind_site_area(STATIONS, _sites([19.11, 19.115], [72.85, 72.86], [40_000, 15_000]))


@pytest.fixture(scope="module")
def model(year, up):
    """Trained once on all but the last 20 days, with both new inputs."""
    rd, wx = year
    return forecast.train(rd[rd["ts"] < END - pd.Timedelta(days=20)], wx, horizon=72, festival=True, upwind=up)


def test_hourly_forecast_reaches_72_hours_and_daily_probabilities_cover_three_days(year, model):
    rd, wx = year
    fc = forecast.predict(model, rd, wx, END, horizon=72)
    for sid in ("s1", "s2", "ward"):
        hours = fc[fc["station_id"] == sid]["ts"]
        assert len(hours) == 72 and hours.max() == END + pd.Timedelta(hours=72)
    days = forecast.predict_daily(model, rd, wx, END)
    assert sorted(days["station_id"].unique()) == ["s1", "s2", "ward"]
    for sid, g in days.groupby("station_id"):
        assert g["day"].tolist() == [1, 2, 3]
        assert g["starts_at"].tolist() == [END + pd.Timedelta(hours=1 + 24 * k) for k in range(3)]
        assert g["ends_at"].tolist() == [END + pd.Timedelta(hours=24 * (k + 1)) for k in range(3)]
    assert days["p_exceed"].between(0, 1).all()


def test_hours_past_the_weather_forecast_are_not_forecast(year, model):
    rd, wx = year
    short = wx[wx["ts"] <= END + pd.Timedelta(hours=60)]
    fc = forecast.predict(model, rd, short, END, horizon=72)
    assert fc.groupby("station_id")["ts"].max().eq(END + pd.Timedelta(hours=60)).all()
    assert forecast.predict_daily(model, rd, short, END)["day"].max() == 2  # day 3 has 12 of its 24 weather hours
    almost = wx[wx["ts"] <= END + pd.Timedelta(hours=70)]
    assert forecast.predict_daily(model, rd, almost, END)["day"].tolist() == [1, 2, 3] * 3  # 22 of 24 hours is enough


def test_training_rows_past_48_hours_come_from_every_second_origin(year):
    rd, wx = year
    rows = forecast.build_rows(rd, wx, None, 72, {"s1": 0, "s2": 1}, with_target=False)
    per_h = rows.groupby("h")["t0"].nunique()
    assert per_h[49] == pytest.approx(per_h[48] / 2, abs=1) and per_h[72] == per_h[49]
    assert set(rows.loc[rows["h"] == 49, "t0"]) <= set(rows.loc[rows["h"] == 48, "t0"])
    one = forecast.build_rows(rd, wx, pd.DatetimeIndex([END]), 72, {"s1": 0}, with_target=False)
    assert sorted(one["h"]) == list(range(1, 73))  # a forecast still covers every hour


def test_daily_target_is_the_mean_of_the_24_hours_after_the_origin(year):
    rd, wx = year
    t0 = END - pd.Timedelta(days=10)
    rows = forecast.daily_rows(rd, wx, pd.DatetimeIndex([t0]), {"s1": 0, "s2": 1})
    s1 = rd[rd["station_id"] == "s1"].set_index("ts")["pm10"]
    for d in (1, 2, 3):
        block = s1[(s1.index > t0 + pd.Timedelta(hours=24 * (d - 1))) & (s1.index <= t0 + pd.Timedelta(hours=24 * d))]
        row = rows[(rows["station_id"] == "s1") & (rows["day"] == d)].iloc[0]
        assert row["y"] == pytest.approx(block.mean())
        assert row["lag_1"] == pytest.approx(s1[t0])  # the origin hour is a feature, never part of a target
    both = rd[rd["ts"].between(t0 + pd.Timedelta(hours=1), t0 + pd.Timedelta(hours=24))].groupby("ts")["pm10"].mean()
    ward = rows[(rows["station_id"] == "ward") & (rows["day"] == 1)].iloc[0]
    assert ward["y"] == pytest.approx(both.mean())  # the ward is the hourly mean of its stations


def test_a_24_hour_mean_needs_18_measured_hours(year):
    rd, wx = year
    t0 = END - pd.Timedelta(days=10)
    gap = rd["ts"].between(t0 + pd.Timedelta(hours=1), t0 + pd.Timedelta(hours=7)) & (rd["station_id"] == "s1")
    rows = forecast.daily_rows(rd[~gap], wx, pd.DatetimeIndex([t0]), {"s1": 0, "s2": 1})
    assert set(rows[rows["station_id"] == "s1"]["day"]) == {2, 3}  # 17 of 24 hours on day 1: no target


def test_nothing_after_the_origin_reaches_a_feature_or_a_forecast(year, model, up):
    rd, wx = year
    t0 = END - pd.Timedelta(days=8)
    clean = rd[rd["ts"] <= t0]
    poisoned = rd.copy()
    poisoned.loc[poisoned["ts"] > t0, "pm10"] = 9999.0
    pd.testing.assert_frame_equal(forecast.predict(model, clean, wx, t0, 72).reset_index(drop=True),
                                  forecast.predict(model, poisoned, wx, t0, 72).reset_index(drop=True))
    pd.testing.assert_frame_equal(forecast.predict_daily(model, clean, wx, t0).reset_index(drop=True),
                                  forecast.predict_daily(model, poisoned, wx, t0).reset_index(drop=True))
    at_t0 = dict(origins=pd.DatetimeIndex([t0]), station_codes={"s1": 0, "s2": 1}, festival=True, upwind=up)
    a = forecast.daily_rows(clean, wx, with_target=False, **at_t0)
    b = forecast.daily_rows(poisoned, wx, with_target=False, **at_t0)
    assert len(a) == 9
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))
    assert (forecast.daily_rows(poisoned, wx, **at_t0)["y"] > 9000).all()  # only the targets saw the later readings


def test_festival_calendar_flags_real_festival_days_in_ist():
    ts = pd.DatetimeIndex([
        "2025-10-21T14:30Z",  # Laxmi Pujan 2025, 20:00 IST
        "2025-10-23T19:00Z",  # 00:30 IST on 24 Oct, the day after Bhaubeej
        "2025-12-31T18:30Z",  # midnight IST, New Year 2026
        "2026-09-25T12:00Z",  # Anant Chaturdashi 2026 (Ganesh Visarjan)
        "2026-11-08T14:00Z",  # Laxmi Pujan 2026
        "2026-11-20T14:00Z",
        "2027-03-22T06:00Z",  # Holi 2027
    ], tz="UTC")
    assert festivals.flag(ts).tolist() == [1, 0, 1, 1, 1, 0, 1]
    names = {f.name for f in festivals.CALENDAR}
    assert {"Diwali", "Ganeshotsav", "Holi", "New Year"} <= names
    for year in (2025, 2026, 2027):
        assert any(f.name == "Diwali" and f.first.year == year for f in festivals.CALENDAR)


def test_upwind_site_area_counts_the_sites_the_wind_blows_from():
    st = pd.DataFrame({"id": ["s"], "lat": [19.10], "lon": [72.85]})
    sites = _sites([19.109, 19.10, 19.145], [72.85, 72.8595, 72.85], [20_000, 10_000, 50_000])  # 1 km N, 1 km E, 5 km N
    t = forecast.upwind_site_area(st, sites)["s"]
    assert len(t) == 360
    assert t[0] == pytest.approx(2.0) and t[20] == pytest.approx(2.0)  # hectares; wind from the north
    assert t[90] == pytest.approx(1.0)  # wind from the east
    assert t[45] == 0 and t[180] == 0  # nothing in those sectors, and the far site is out of range


def test_new_inputs_are_optional_and_the_model_remembers_them(year, model):
    rd, wx = year
    plain = forecast.train(rd, wx, horizon=6)
    assert {"festival", "upwind_sites_ha"} <= set(model.features)
    assert {"festival", "upwind_sites_ha"} <= set(model.daily_features)
    assert not {"festival", "upwind_sites_ha"} & set(plain.features + plain.daily_features)
    assert len(forecast.predict(plain, rd, wx, END, horizon=6)) == 3 * 6


def test_backtest_scores_49_to_72_hours_and_the_daily_calls(year):
    rd, wx = year
    start = END - pd.Timedelta(days=6)
    res = backtest.run(rd, wx, start, END, horizon=72, step_h=24)
    assert res.origins == 4 and set(res.metrics) == {"1-24", "25-48", "49-72"}
    assert res.metrics["49-72"]["n"] > 0 and res.metrics["49-72"]["mae_persistence"] > 0
    assert set(res.daily) == {"ward", "stations", "window"}
    assert res.daily["window"]["ward_days"] == 4 + 2  # days 1-3 of four daily forecasts span six days
    for level, n in (("ward", 4), ("stations", 8)):
        assert set(res.daily[level]) == {"1", "2", "3"}
        for m in res.daily[level].values():
            assert m["n"] == n and 0 <= m["exceed_days"] <= n and 0 <= m["brier"] <= 1
            assert m["hits"] + m["misses"] == m["exceed_days"]


def test_daily_metrics_on_a_toy_series():
    rows = pd.DataFrame({
        "level": ["ward"] * 4, "station_id": ["ward"] * 4, "day": [1, 1, 1, 1],
        "end": pd.date_range("2026-11-02", periods=4, freq="D", tz="UTC"),
        "p": [0.9, 0.2, 0.7, 0.1], "actual": [130.0, 110.0, 80.0, 60.0], "persist": [120.0, 90.0, 70.0, 50.0],
    })
    m = backtest.daily_metrics(rows, 100.0)["ward"]["1"]
    assert (m["n"], m["exceed_days"], m["hits"], m["misses"], m["false_alarms"]) == (4, 2, 1, 1, 1)
    assert m["f1_model"] == pytest.approx(0.5) and m["f1_persistence"] == pytest.approx(2 / 3, abs=1e-3)
    assert m["brier"] == pytest.approx((0.01 + 0.64 + 0.49 + 0.01) / 4, abs=1e-3)


def test_each_measured_day_counts_once_and_a_quiet_window_has_no_f1():
    e1, e2 = pd.Timestamp("2026-11-02T00:00Z"), pd.Timestamp("2026-11-03T00:00Z")
    rows = pd.DataFrame({  # two forecasts score the 24 h ending e2: the first as day 2, the second as day 1
        "level": ["ward", "ward", "ward", "stations", "stations"], "station_id": ["ward", "ward", "ward", "s1", "s1"],
        "day": [1, 2, 1, 1, 2], "end": [e1, e2, e2, e1, e2],
        "p": [0.8, 0.3, 0.2, 0.3, 0.1], "actual": [130.0, 60.0, 60.0, 40.0, 45.0], "persist": [90.0, 80.0, 130.0, 50.0, 50.0],
    })
    m = backtest.daily_metrics(rows, 100.0)
    assert m["window"] == {"ward_days": 2, "ward_exceed_days": 1, "station_days": 2, "station_exceed_days": 0}
    assert m["stations"]["1"]["f1_model"] is None and m["stations"]["1"]["f1_persistence"] is None  # nothing to catch
    assert m["ward"]["1"]["f1_persistence"] == 0  # a false alarm against one exceedance is a real 0
    quiet = pd.DataFrame({"h": [1, 2], "pred": [50.0, 60.0], "lo": [40.0, 50.0], "hi": [60.0, 70.0], "p": [0.1, 0.2],
                          "actual": [55.0, 58.0], "persist": [52.0, 52.0]})
    assert backtest.metrics(quiet, 100.0)["1-24"]["f1_exceed_model"] is None


def test_an_input_stays_on_only_if_it_does_not_make_the_backtest_worse():
    hourly = {k: {"mae_model": 10.0, "f1_exceed_model": 0.5} for k in ("1-24", "25-48", "49-72")}
    daily = {"stations": {d: {"f1_model": 0.6} for d in ("1", "2", "3")}}
    better = {k: {"mae_model": 9.5, "f1_exceed_model": 0.5} for k in hourly}
    worse_f1 = {"stations": {d: {"f1_model": 0.55} for d in ("1", "2", "3")}}
    c = backtest.change(hourly, daily, better, daily)
    assert c == {"mae": -0.5, "f1_hourly": 0.0, "f1_daily": 0.0, "on": True}
    assert backtest.change(hourly, daily, better, worse_f1)["on"] is False
    assert backtest.change(hourly, daily, hourly, daily)["on"] is True  # no change is not worse


def test_a_change_too_small_to_show_still_decides():
    # Real K-East, Sep-Oct window: festival cut the error but lost 0.0003 of hourly F1, which rounds to 0.000.
    daily = {"stations": {d: {"f1_model": 0.9} for d in ("1", "2", "3")}}
    base = {k: {"mae_model": 20.0, "f1_exceed_model": f} for k, f in (("1-24", 0.915), ("25-48", 0.912), ("49-72", 0.912))}
    fest = {k: {"mae_model": 19.7, "f1_exceed_model": f} for k, f in (("1-24", 0.915), ("25-48", 0.911), ("49-72", 0.912))}
    c = backtest.change(base, daily, fest, daily)
    assert c["on"] is False and c["f1_hourly"] == pytest.approx(-0.0003, abs=1e-4)


def test_a_quiet_window_compares_false_alarms_against_nothing_to_catch():
    hourly = {k: {"mae_model": 10.0, "f1_exceed_model": None} for k in ("1-24", "25-48", "49-72")}
    quiet = {"stations": {d: {"f1_model": None} for d in ("1", "2", "3")}}
    alarms = {"stations": {"1": {"f1_model": 0.0}, "2": {"f1_model": None}, "3": {"f1_model": None}}}
    assert backtest.change(hourly, quiet, hourly, quiet)["on"] is True
    assert backtest.change(hourly, quiet, hourly, alarms)["on"] is False
