"""Synthetic weather and PM history for offline development and demos.

Used only when live sources are unreachable. Every row it produces is flagged `synthetic`.
The physics is deliberately simple but keeps the relationships the forecast must learn:
PM10 rises when the mixing layer is shallow and the wind is calm, falls with rain and sea breeze,
peaks in winter and collapses in the monsoon.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

IST_OFFSET_H = 5.5


def _ist_hour(ts: pd.DatetimeIndex) -> np.ndarray:
    return ((ts.hour + ts.minute / 60 + IST_OFFSET_H) % 24).to_numpy()


def weather(start: pd.Timestamp, end: pd.Timestamp, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ts = pd.date_range(start.floor("h"), end.floor("h"), freq="h", tz="UTC")
    n = len(ts)
    h = _ist_hour(ts)
    month = ts.month.to_numpy()
    monsoon = np.isin(month, [6, 7, 8, 9])
    day = np.sin(np.pi * np.clip((h - 7) / 11, 0, 1))  # 0 at night, 1 mid-afternoon

    # Synoptic wobble shared by wind and mixing height, so some days are stagnant.
    synoptic = np.convolve(rng.normal(0, 1, n + 72), np.ones(72) / 72, mode="same")[36:36 + n] * 3

    wind = 1.6 + 2.8 * day + 0.6 * synoptic + rng.normal(0, 0.4, n) + 2.5 * monsoon
    wind = np.clip(wind, 0.3, 12)
    # Land breeze from the east at night, sea breeze from the west-northwest by afternoon.
    wdir = np.where(day > 0.35, 285, 75) + rng.normal(0, 25, n) + 40 * monsoon
    wdir = np.mod(wdir, 360)
    blh = 260 + 1150 * day + 180 * synoptic + rng.normal(0, 60, n) + 400 * monsoon
    blh = np.clip(blh, 80, 2500)
    temp = 24 + 7 * day + rng.normal(0, 0.8, n)
    rh = np.clip(78 - 25 * day + 15 * monsoon + rng.normal(0, 5, n), 20, 100)
    rain_prob = np.where(monsoon, 0.35, 0.01)
    precip = np.where(rng.random(n) < rain_prob, rng.gamma(1.5, 2.0, n), 0.0)

    return pd.DataFrame({
        "ts": ts, "wind_speed": wind, "wind_dir": wdir, "blh": blh,
        "temp": temp, "rh": rh, "precip": precip,
    })


def readings(wx: pd.DataFrame, station_ids: list[str], seed: int = 11) -> pd.DataFrame:
    """PM10/PM2.5 per station driven by the given weather frame."""
    rng = np.random.default_rng(seed)
    ts = pd.DatetimeIndex(wx["ts"])
    h = _ist_hour(ts)
    month = ts.month.to_numpy()
    season = np.select(
        [np.isin(month, [11, 12, 1, 2]), np.isin(month, [3, 4, 5, 10]), np.isin(month, [6, 7, 8, 9])],
        [1.0, 0.7, 0.35], 0.6,
    )
    traffic = 1 + 0.25 * np.exp(-((h - 9.5) ** 2) / 3) + 0.3 * np.exp(-((h - 20.5) ** 2) / 4)
    work = np.where((h >= 8) & (h <= 19), 1.15, 0.9)  # construction hours
    vent = (wx["wind_speed"].to_numpy() * wx["blh"].to_numpy()).clip(50, None)
    stagnation = (700 / vent) ** 0.45
    washout = np.exp(-0.25 * wx["precip"].to_numpy())

    frames = []
    for i, sid in enumerate(station_ids):
        local = 1 + 0.12 * (i - len(station_ids) / 2)
        base = 95 * season * traffic * work * stagnation * washout * local
        # AR(1) noise so recent values carry information, as real sensors do.
        e = np.zeros(len(ts))
        shocks = rng.normal(0, 0.12, len(ts))
        for t in range(1, len(ts)):
            e[t] = 0.85 * e[t - 1] + shocks[t]
        pm10 = np.clip(base * np.exp(e), 8, 900)
        pm25 = pm10 * np.clip(rng.normal(0.45, 0.06, len(ts)), 0.25, 0.7)
        # A few gaps, like a real feed.
        gaps = rng.random(len(ts)) < 0.02
        pm10[gaps] = np.nan
        pm25[gaps] = np.nan
        frames.append(pd.DataFrame({"station_id": sid, "ts": ts, "pm10": pm10, "pm25": pm25}))
    return pd.concat(frames, ignore_index=True)
