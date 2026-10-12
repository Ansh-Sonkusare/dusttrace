import numpy as np
import pandas as pd
import pytest

from dusttrace import signature

T0 = pd.Timestamp("2026-10-05 10:00", tz="UTC")  # 15:30 IST


def test_classify_coarse_fine_and_no_spike():
    base = dict(base_pm10=60.0, base_ratio=0.4)
    day = pd.Timestamp("2026-10-05 08:00", tz="UTC")    # 13:30 IST, working hours
    night = pd.Timestamp("2026-10-05 18:00", tz="UTC")  # 23:30 IST, truck hours
    assert signature.classify(150, 30, ts=day, **base) == "coarse_work"     # ratio 0.2 vs 0.4
    assert signature.classify(150, 30, ts=night, **base) == "coarse_night"
    assert signature.classify(150, 90, ts=day, **base) == "fine"            # ratio 0.6 vs 0.4
    assert signature.classify(150, 60, ts=day, **base) == "mixed"
    assert signature.classify(70, 10, ts=day, **base) is None               # not a spike
    assert signature.classify(150, float("nan"), ts=day, **base) is None


def _station(sid="s1", hours=24 * 40, spike=None):
    ts = pd.date_range(end=T0, periods=hours, freq="h", tz="UTC")
    rng = np.random.default_rng(1)
    pm10 = 60 + rng.normal(0, 5, len(ts))
    pm25 = 0.4 * pm10
    df = pd.DataFrame({"station_id": sid, "ts": ts, "pm10": pm10, "pm25": pm25, "synthetic": False, "filled": False})
    if spike == "coarse":
        df.loc[df.index[-3:], "pm10"] = 160.0
        df.loc[df.index[-3:], "pm25"] = 35.0
    return df


def test_station_signatures_use_recent_real_hours_against_a_30_day_baseline():
    rd = pd.concat([_station("s1", spike="coarse"), _station("s2")])
    sig = signature.station_signatures(rd, T0)
    assert sig["s1"]["signature"] == "coarse_work" and sig["s1"]["base_ratio"] == pytest.approx(0.4, abs=0.01)
    assert sig["s2"]["signature"] is None


def test_stale_or_filled_hours_give_no_signature():
    stale = _station("s1", spike="coarse")
    stale["ts"] = stale["ts"] - pd.Timedelta(hours=30)  # feed stopped a day ago
    filled = _station("s2", spike="coarse")
    filled.loc[filled.index[-6:], "filled"] = True
    sig = signature.station_signatures(pd.concat([stale, filled]), T0)
    assert sig.get("s1", {}).get("signature") is None and sig.get("s2", {}).get("signature") is None


def test_nearest_station_within_reach():
    stations = {"near": {"lat": 19.110, "lon": 72.870, "signature": "coarse_work"},
                "far": {"lat": 19.200, "lon": 72.950, "signature": "fine"}}
    assert signature.for_site(19.112, 72.872, stations)["station_id"] == "near"
    assert signature.for_site(19.30, 73.10, stations) is None


def test_dry_windy_working_hours():
    ts = pd.date_range(T0 - pd.Timedelta(hours=24), periods=72, freq="h", tz="UTC")
    wx = pd.DataFrame({"ts": ts, "wind_speed": 3.0, "precip": 0.0})
    windy = (ts >= T0 + pd.Timedelta(hours=1)) & (ts <= T0 + pd.Timedelta(hours=8))
    wx.loc[windy, "wind_speed"] = 6.0
    hrs = signature.dry_windy_hours(wx, T0)
    # 11:00-18:00 UTC = 16:30-23:30 IST; only those before 22:00 IST are working hours
    assert [h.hour for h in hrs] == [11, 12, 13, 14, 15, 16]
    wet = wx.copy()
    wet.loc[(ts > T0 - pd.Timedelta(hours=10)) & (ts <= T0 - pd.Timedelta(hours=9)), "precip"] = 2.0
    assert signature.dry_windy_hours(wet, T0) == []  # it rained in the last 24 h: ground is wet


def test_implausible_pairs_are_ignored():
    day = pd.Timestamp("2026-10-05 08:00", tz="UTC")
    # Seen in real CPCB data on Sep 1: PM10 180 with PM2.5 near zero is a broken PM2.5 channel, not dust.
    assert signature.classify(180, 1.8, base_pm10=60, base_ratio=0.22, ts=day) is None
    assert signature.classify(150, 160, base_pm10=60, base_ratio=0.4, ts=day) is None  # PM2.5 can't exceed PM10
