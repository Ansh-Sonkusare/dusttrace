"""Back-test (PRD F3 evidence): replay past days with only the data up to each forecast origin visible.

The model is trained on readings before `start` only. For each origin from `start`, it forecasts the
next `horizon` hours from readings up to that origin, and the forecast is scored against what the
stations then measured, alongside persistence (the value at the origin carried forward).

One honest caveat: the weather at the target hour is the observed weather (Open-Meteo archive), so
this treats the weather forecast as perfect. Live forecasts will do somewhat worse.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from . import forecast

BUCKETS = {"1-24": (1, 24), "25-48": (25, 48)}
IST = pd.Timedelta(hours=5.5)


@dataclass
class Result:
    train_end: pd.Timestamp
    test_end: pd.Timestamp
    origins: int
    stations: list[str]
    metrics: dict
    spike_day: dict | None
    note: str = "Weather at the target hour is observed weather, i.e. a perfect weather forecast."


def metrics(rows: pd.DataFrame, threshold: float) -> dict:
    """`rows`: h, pred, lo, hi, p, actual, persist (ward level)."""
    out = {}
    for name, (a, b) in BUCKETS.items():
        r = rows[(rows["h"] >= a) & (rows["h"] <= b)]
        if r.empty:
            continue
        ex = r["actual"] > threshold
        out[name] = {
            "n": int(len(r)),
            "mae_model": round(float((r["pred"] - r["actual"]).abs().mean()), 2),
            "mae_persistence": round(float((r["persist"] - r["actual"]).abs().mean()), 2),
            "f1_exceed_model": round(float(f1_score(ex, r["p"] >= 0.5, zero_division=0)), 3),
            "f1_exceed_persistence": round(float(f1_score(ex, r["persist"] > threshold, zero_division=0)), 3),
            "coverage_10_90": round(float(((r["actual"] >= r["lo"]) & (r["actual"] <= r["hi"])).mean()), 3),
            "exceed_rate": round(float(ex.mean()), 3),
        }
    return out


def _ward_actual(readings: pd.DataFrame) -> pd.Series:
    return readings.dropna(subset=["pm10"]).groupby("ts")["pm10"].mean()


def run(readings: pd.DataFrame, wx: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
        horizon: int = 48, step_h: int = 24, threshold: float = 100.0) -> Result:
    readings = readings.copy()
    readings["ts"] = pd.to_datetime(readings["ts"], utc=True)
    model = forecast.train(readings[readings["ts"] < start], wx, horizon, threshold)
    actual = _ward_actual(readings)
    origins = pd.date_range(start, end - pd.Timedelta(hours=horizon), freq=f"{step_h}h", tz="UTC")
    rows, issued = [], {}
    for t0 in origins:
        fc = forecast.predict(model, readings[readings["ts"] <= t0], wx, t0, horizon)
        ward = fc[fc["station_id"] == "ward"].set_index("ts")
        if ward.empty or t0 not in actual.index:
            continue
        issued[t0] = ward
        for ts, w in ward.iterrows():
            if ts in actual.index:
                rows.append({"t0": t0, "ts": ts, "h": int((ts - t0) / pd.Timedelta(hours=1)), "pred": w["pm10"],
                             "lo": w["pm10_lo"], "hi": w["pm10_hi"], "p": w["p_exceed"],
                             "actual": actual[ts], "persist": actual[t0]})
    df = pd.DataFrame(rows)
    return Result(start, end, len(issued), sorted(model.station_codes), metrics(df, threshold) if len(df) else {},
                  _spike_day(actual, issued, start, end, horizon))


def _spike_day(actual: pd.Series, issued: dict, start, end, horizon) -> dict | None:
    """The worst IST day in the test window, and what the forecast issued about 48 h earlier said."""
    a = actual[(actual.index >= start) & (actual.index < end)]
    if a.empty or not issued:
        return None
    by_day = a.groupby((a.index + IST).date).mean()
    day = by_day.idxmax()
    day_start = pd.Timestamp(day).tz_localize("UTC") - IST
    candidates = [t0 for t0 in issued if t0 <= day_start - pd.Timedelta(hours=24)]
    if not candidates:
        return {"day": str(day), "actual_mean": round(float(by_day.max()), 1), "issued_at": None}
    t0 = max(candidates)
    w = issued[t0]
    hours = w[(w.index >= day_start) & (w.index < day_start + pd.Timedelta(hours=24))]
    if hours.empty:
        return {"day": str(day), "actual_mean": round(float(by_day.max()), 1), "issued_at": t0.isoformat()}
    return {
        "day": str(day),
        "actual_mean": round(float(by_day.max()), 1),
        "issued_at": t0.isoformat(),
        "lead_hours": int((day_start - t0) / pd.Timedelta(hours=1)),
        "forecast_mean": round(float(hours["pm10"].mean()), 1),
        "p_exceed_max": round(float(hours["p_exceed"].max()), 3),
        "flagged": bool(hours["p_exceed"].max() >= 0.5),
    }
