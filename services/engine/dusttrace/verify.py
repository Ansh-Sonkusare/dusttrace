"""Data check (issue #29): how much of the latest run rests on real data, in numbers.

Run after each forecast (`dusttrace verify`). Per source it records freshness; for the run it records
the share of the last week's station hours that were measured, filled from CAMS or synthetic; and it
measures the CAMS fill on a hold-out month the correction never saw. Stored in `data_checks`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import fill

FRESH_HOURS = 6                      # same rule as pipeline.anchor
SILENT = pd.Timedelta(days=30)       # same rule as pipeline.FILL_MAX_STALE
WEEK = pd.Timedelta(days=7)
FILLED_WARN = 0.25


def station_freshness(newest: dict, now: pd.Timestamp, fresh_hours: int = FRESH_HOURS) -> list[dict]:
    """Per station: newest reading, its age in hours and fresh | stale | silent. Freshest first."""
    out = []
    for sid, ts in newest.items():
        if ts is None or pd.isna(ts):
            out.append({"station_id": sid, "newest": None, "age_h": None, "status": "silent"})
            continue
        ts = pd.Timestamp(ts)
        age = now - ts
        status = "fresh" if age <= pd.Timedelta(hours=fresh_hours) else "stale" if age <= SILENT else "silent"
        out.append({"station_id": sid, "newest": ts.isoformat(), "age_h": int(age / pd.Timedelta(hours=1)),
                    "status": status})
    return sorted(out, key=lambda r: (r["age_h"] is None, r["age_h"] or 0, r["station_id"]))


def input_shares(rd: pd.DataFrame, now: pd.Timestamp) -> dict:
    """Share of the run's station hours in the last 7 days that were measured, filled or synthetic."""
    if rd.empty:
        return {"hours": 0, "real": 0.0, "filled": 0.0, "synthetic": 0.0}
    w = rd[(rd["ts"] > now - WEEK) & (rd["ts"] <= now) & rd["pm10"].notna()]
    n = len(w)
    if n == 0:
        return {"hours": 0, "real": 0.0, "filled": 0.0, "synthetic": 0.0}
    filled = w["filled"].astype(bool)
    syn = w["synthetic"].astype(bool) & ~filled
    return {"hours": int(n), "real": round(float((~filled & ~syn).sum() / n), 4),
            "filled": round(float(filled.sum() / n), 4), "synthetic": round(float(syn.sum() / n), 4)}


def cams_holdout(obs: pd.Series, model: pd.Series, test_days: int = 30) -> dict | None:
    """Fit the CAMS correction on everything before the station's last `test_days` of readings and
    score it on those days: the error a fill would have had."""
    obs = obs.dropna()
    if obs.empty:
        return None
    cut = obs.index.max() - pd.Timedelta(days=test_days)
    k = fill.fit(obs[obs.index <= cut], model[model.index <= cut])
    if k.method == "none":
        return None
    j = pd.concat({"obs": obs[obs.index > cut], "pred": fill.apply(model, k)}, axis=1, sort=True).dropna()
    if len(j) < 24:
        return None
    err = j["pred"] - j["obs"]
    r = float(np.corrcoef(j["pred"], j["obs"])[0, 1]) if j["pred"].std() > 0 and j["obs"].std() > 0 else float("nan")
    return {"hours": int(len(j)), "mae": round(float(err.abs().mean()), 2), "bias": round(float(err.mean()), 2),
            "r": round(r, 3) if np.isfinite(r) else None, "slope": k.slope, "intercept": k.intercept,
            "from": j.index.min().isoformat(), "to": j.index.max().isoformat()}


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def problems(stations: list[dict], shares: dict, weather_live: float, receptors_osm: int, sites_real: int,
             housing_osm: int | None = None) -> list[str]:
    """Plain sentences for everything in the latest run that isn't real, live data."""
    out = []
    if not any(s["status"] == "fresh" for s in stations):
        ages = [s["age_h"] for s in stations if s["age_h"] is not None]
        out.append(f"No real station has reported in the last {FRESH_HOURS} hours"
                   + (f" (the newest reading is {min(ages)} hours old)." if ages else "."))
    if shares.get("hours") and shares["filled"] >= FILLED_WARN:
        out.append(f"{_pct(shares['filled'])} of the last week's station hours are filled from CAMS, not measured.")
    if shares.get("hours") and shares["synthetic"] > 0:
        out.append(f"{_pct(shares['synthetic'])} of the last week's station hours are synthetic.")
    if weather_live < 1:
        out.append(f"{_pct(1 - weather_live)} of the forecast hours use synthetic weather.")
    if receptors_osm == 0:
        out.append("Schools and hospitals are demo positions: no OpenStreetMap receptors are loaded.")
    if housing_osm == 0:
        out.append("Exposure to homes uses demo housing points: no census-based housing is loaded.")
    if sites_real == 0:
        out.append("No real construction site is loaded yet, so only the demo sites get Safe-Work Windows.")
    return out
