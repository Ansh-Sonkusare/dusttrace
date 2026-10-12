"""Cause signals from real data (PRD F10, issue #34).

PM10/PM2.5: construction dust is coarse, so a spike where PM10 climbs far more than PM2.5 points to
dry excavation or demolition in working hours, and to truck track-out at night, when heavy vehicles
may enter the city. A spike carried by PM2.5 points to combustion (traffic, burning), not
construction. On real CPCB data (Jul-Oct 2026, 6,801 spike hours), 34% were coarse, peaking
21:00-01:00 IST, 22% fine and the rest mixed.

Only measured hours count: CAMS-filled hours say nothing about what is burning or digging nearby.
"""

from __future__ import annotations

import math

import pandas as pd

SPIKE = 1.5        # PM10 above 1.5x its 30-day median is a spike
COARSE, FINE = 0.8, 1.2   # PM2.5/PM10 ratio vs its 30-day median
LOOKBACK_H = 6
BASE_DAYS, BASE_MIN_HOURS = 30, 200
WORK_IST = (6, 22)        # dusty work allowed 06:00-22:00 IST; trucks run outside it
DRY_WIND = 5.0            # m/s; real K-East hours at or above it: about 10%, mostly in July
REACH_KM = 4.0
RATIO_OK = (0.05, 1.0)    # outside this the PM2.5 or PM10 channel is broken


def ist_hour(ts) -> int:
    return (pd.Timestamp(ts) + pd.Timedelta(hours=5.5)).hour


def classify(pm10, pm25, base_pm10, base_ratio, ts) -> str | None:
    vals = [pm10, pm25, base_pm10, base_ratio]
    if any(v is None or not math.isfinite(float(v)) for v in vals) or pm10 <= 0 or base_ratio <= 0:
        return None
    if pm10 < SPIKE * base_pm10 or not RATIO_OK[0] <= pm25 / pm10 <= RATIO_OK[1]:
        return None
    rel = (pm25 / pm10) / base_ratio
    if rel < COARSE:
        return "coarse_work" if WORK_IST[0] <= ist_hour(ts) < WORK_IST[1] else "coarse_night"
    if rel > FINE:
        return "fine"
    return "mixed"


def station_signatures(rd: pd.DataFrame, t0: pd.Timestamp, lookback_h: int = LOOKBACK_H) -> dict:
    """Per station with measured PM10 and PM2.5: the signature of its last `lookback_h` hours."""
    if rd.empty or "pm25" not in rd:
        return {}
    ok = rd[~rd["synthetic"].astype(bool) & ~rd.get("filled", False).astype(bool)].dropna(subset=["pm10", "pm25"])
    ok = ok[(ok["pm10"] > 0) & (ok["pm25"] > 0) & (ok["ts"] <= t0)]
    out = {}
    start = t0 - pd.Timedelta(hours=lookback_h)
    for sid, g in ok.groupby("station_id"):
        recent = g[g["ts"] > start]
        base = g[(g["ts"] <= start) & (g["ts"] > start - pd.Timedelta(days=BASE_DAYS))]
        if recent.empty or len(base) < BASE_MIN_HOURS:
            continue
        base_pm10 = float(base["pm10"].median())
        base_ratio = float((base["pm25"] / base["pm10"]).median())
        last = recent.sort_values("ts").iloc[-1]
        pm10, pm25 = float(recent["pm10"].mean()), float(recent["pm25"].mean())
        out[sid] = {"signature": classify(pm10, pm25, base_pm10, base_ratio, last["ts"]),
                    "pm10": round(pm10, 1), "ratio": round(pm25 / pm10, 3), "base_pm10": round(base_pm10, 1),
                    "base_ratio": round(base_ratio, 3), "ts": pd.Timestamp(last["ts"]).isoformat()}
    return out


def _km(lat1, lon1, lat2, lon2) -> float:
    dy = (lat1 - lat2) * 111.32
    dx = (lon1 - lon2) * 111.32 * math.cos(math.radians(lat1))
    return math.hypot(dx, dy)


def for_site(lat: float, lon: float, stations: dict, reach_km: float = REACH_KM) -> dict | None:
    """The nearest station with a signature, within reach of the site."""
    best = None
    for sid, s in stations.items():
        if not s.get("signature"):
            continue
        d = _km(lat, lon, s["lat"], s["lon"])
        if d <= reach_km and (best is None or d < best["km"]):
            best = {**s, "station_id": sid, "km": round(d, 2)}
    return best


def dry_windy_hours(wx: pd.DataFrame, t0: pd.Timestamp, horizon_h: int = 48, wind: float = DRY_WIND) -> list:
    """Forecast working hours with strong wind, no rain that hour and none in the 24 h before."""
    w = wx.sort_values("ts").set_index("ts")
    rain24 = w["precip"].fillna(0).rolling("24h").sum()
    fut = w[(w.index > t0) & (w.index <= t0 + pd.Timedelta(hours=horizon_h))]
    out = []
    for ts, r in fut.iterrows():
        if (r["wind_speed"] >= wind and (r["precip"] or 0) == 0 and rain24.get(ts, 0) == 0
                and WORK_IST[0] <= ist_hour(ts) < WORK_IST[1]):
            out.append(ts)
    return out
