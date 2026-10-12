import numpy as np
import pandas as pd
import pytest

from dusttrace import effect

START = pd.Timestamp("2026-10-20 02:30", tz="UTC")  # 08:00 IST
WINDOW = (START, START + pd.Timedelta(hours=6))


def series(days=22, during=None, wind=225.0, window_wind=None):
    ts = pd.date_range(START - pd.Timedelta(days=days), START + pd.Timedelta(hours=12), freq="h", tz="UTC")
    rng = np.random.default_rng(4)
    pm = pd.Series(80 + rng.normal(0, 4, len(ts)), index=ts)
    wd = pd.Series(wind, index=ts)
    in_w = (ts >= WINDOW[0]) & (ts < WINDOW[1])
    if during is not None:
        pm[in_w] = during
    if window_wind is not None:
        wd[in_w] = window_wind
    return pm, wd


def test_a_drop_against_comparable_days_is_verified():
    pm, wd = series(during=60.0)
    r = effect.assess(pm, wd, WINDOW)
    assert r["verdict"] == "drop" and r["days"] >= 3
    assert r["baseline"] == pytest.approx(80, abs=2) and r["during"] == pytest.approx(60)
    assert r["change_pct"] == pytest.approx(-25, abs=3)


def test_no_drop_keeps_the_case_open():
    pm, wd = series(during=82.0)
    assert effect.assess(pm, wd, WINDOW)["verdict"] == "no_drop"


def test_too_few_comparable_days_or_missing_readings_is_insufficient():
    pm, wd = series(days=2, during=60.0)
    assert effect.assess(pm, wd, WINDOW)["verdict"] == "insufficient"
    pm, wd = series(during=60.0, wind=45.0, window_wind=225.0)  # no earlier day had the same wind
    assert effect.assess(pm, wd, WINDOW)["verdict"] == "insufficient"
    pm, wd = series(during=60.0)
    pm[(pm.index >= WINDOW[0]) & (pm.index < WINDOW[1])] = np.nan  # the feed was down
    r = effect.assess(pm, wd, WINDOW)
    assert r["verdict"] == "insufficient" and "no readings" in r["note"]


def test_station_must_be_downwind_of_the_site():
    site = (19.117, 72.856)
    east = (19.117, 72.876)  # ~2 km east
    assert effect.downwind(site, east, wind_from_deg=270)      # westerly wind carries dust east
    assert not effect.downwind(site, east, wind_from_deg=90)   # easterly wind carries it away


def test_memory_averages_the_change_per_action():
    rows = [{"action": "ORDER_WHEEL_WASH", "verdict": "drop", "change_pct": -20.0},
            {"action": "ORDER_WHEEL_WASH", "verdict": "no_drop", "change_pct": 4.0},
            {"action": "SCHEDULE_MIST", "verdict": "drop", "change_pct": -12.0},
            {"action": "SCHEDULE_MIST", "verdict": "insufficient", "change_pct": None}]
    m = effect.memory(rows)
    assert m["ORDER_WHEEL_WASH"] == {"n": 2, "mean_change_pct": -8.0, "drops": 1}
    assert m["SCHEDULE_MIST"] == {"n": 1, "mean_change_pct": -12.0, "drops": 1}
