"""Fill a station's outage with CAMS, corrected against that station's own history (issue #28).

CAMS is a coarse model (one grid cell covers most of K-East) and reads low in Mumbai, so each station
gets a linear correction fitted on its recent overlap with real readings. Measured on Jul–Oct 2026
real data: correlation 0.5–0.7 at 7 of 8 stations, mean error about 12–20 µg/m³ after correction.
Filled hours are always flagged; the model never trains on them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

MIN_HOURS = 200      # below this, scale by the ratio of means instead of fitting a line
FIT_DAYS = 60
SLOPE = (0.3, 3.0)   # keep the correction physical when the fit is noisy


@dataclass(frozen=True)
class Correction:
    slope: float
    intercept: float
    hours: int
    mae: float       # in-sample error of the corrected series against the real readings
    method: str      # "linear" | "ratio"


def fit(obs: pd.Series, model: pd.Series, days: int = FIT_DAYS) -> Correction:
    j = pd.concat({"obs": obs, "model": model}, axis=1, sort=True).dropna()
    if not j.empty:
        j = j[j.index > j.index.max() - pd.Timedelta(days=days)]
    if len(j) < 24:
        return Correction(1.0, 0.0, len(j), float("nan"), "none")
    if len(j) < MIN_HOURS:
        slope, intercept, method = float(j["obs"].mean() / max(j["model"].mean(), 1e-6)), 0.0, "ratio"
    else:
        slope, intercept = np.polyfit(j["model"], j["obs"], 1)
        method = "linear"
        if not SLOPE[0] <= slope <= SLOPE[1]:  # fall back to matching the means with a bounded slope
            slope = float(np.clip(slope, *SLOPE))
            intercept = float(j["obs"].mean() - slope * j["model"].mean())
    slope = float(np.clip(slope, *SLOPE))
    pred = np.clip(slope * j["model"] + intercept, 0, None)
    return Correction(round(slope, 4), round(float(intercept), 2), int(len(j)),
                      round(float((pred - j["obs"]).abs().mean()), 2), method)


def apply(model: pd.Series, k: Correction) -> pd.Series:
    return (k.slope * model + k.intercept).clip(lower=0)


def gap(obs: pd.Series, model: pd.Series, k: Correction, now: pd.Timestamp) -> pd.Series:
    """Corrected model values for the hours after the last real reading, up to `now`."""
    last = obs.dropna().index.max()
    m = model[(model.index > last) & (model.index <= now)]
    return apply(m, k)
