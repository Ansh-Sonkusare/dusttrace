"""Verify (PRD F12, issue #33): did PM10 fall after the agent acted?

For an action's window, PM10 at the nearest real station downwind of the site is compared with the
same IST hours on earlier days whose wind came from the same sector, so the comparison holds the
weather roughly fixed. A drop of at least DROP closes the case; anything else keeps it open. Too few
comparable days, or no readings in the window (the feed is down), gives "insufficient": nothing is
assumed either way.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

DROP = 0.10           # at least 10% below comparable days
SECTOR = 45.0         # degrees either side of the window's mean wind
LOOKBACK_DAYS = 21
MIN_DAYS = 3
MIN_COVERAGE = 0.5    # share of window hours with a reading
WINDOW_H = 6
REACH_KM = 4.0


def _ang(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def _mean_dir(deg: pd.Series) -> float:
    r = np.radians(deg.dropna().astype(float))
    return float(np.degrees(np.arctan2(np.sin(r).mean(), np.cos(r).mean())) % 360)


def bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    dy = b[0] - a[0]
    dx = (b[1] - a[1]) * math.cos(math.radians(a[0]))
    return math.degrees(math.atan2(dx, dy)) % 360


def km(a, b) -> float:
    dy = (a[0] - b[0]) * 111.32
    dx = (a[1] - b[1]) * 111.32 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def downwind(site: tuple[float, float], station: tuple[float, float], wind_from_deg: float) -> bool:
    """Wind blows *from* `wind_from_deg`, so dust travels toward wind_from + 180."""
    return _ang(bearing(site, station), (wind_from_deg + 180) % 360) <= SECTOR


def assess(pm10: pd.Series, wind_dir: pd.Series, window: tuple[pd.Timestamp, pd.Timestamp]) -> dict:
    start, end = window
    in_w = (pm10.index >= start) & (pm10.index < end)
    hours = int(round((end - start) / pd.Timedelta(hours=1)))
    during = pm10[in_w].dropna()
    base = {"during": None, "baseline": None, "change_pct": None, "days": 0}
    if len(during) < MIN_COVERAGE * hours:
        return {**base, "verdict": "insufficient", "note": "no readings at the station in the window"}
    wd_w = wind_dir[(wind_dir.index >= start) & (wind_dir.index < end)]
    sector = _mean_dir(wd_w) if len(wd_w.dropna()) else None
    vals = []
    for d in range(1, LOOKBACK_DAYS + 1):
        s, e = start - pd.Timedelta(days=d), end - pd.Timedelta(days=d)
        p = pm10[(pm10.index >= s) & (pm10.index < e)].dropna()
        w = wind_dir[(wind_dir.index >= s) & (wind_dir.index < e)].dropna()
        if len(p) < MIN_COVERAGE * hours or w.empty or sector is None or _ang(_mean_dir(w), sector) > SECTOR:
            continue
        vals.append(float(p.mean()))
    if len(vals) < MIN_DAYS:
        return {**base, "days": len(vals), "verdict": "insufficient",
                "note": f"only {len(vals)} earlier days with the same wind"}
    b, m = float(np.mean(vals)), float(during.mean())
    change = (m - b) / b * 100 if b > 0 else 0.0
    verdict = "drop" if m <= b * (1 - DROP) else "no_drop"
    return {"during": round(m, 1), "baseline": round(b, 1), "change_pct": round(change, 1), "days": len(vals),
            "verdict": verdict, "note": f"{len(vals)} earlier days with wind from {round(sector)}°"}


def memory(rows: list[dict]) -> dict:
    """Which fix works: average PM10 change per action, over verified (not insufficient) results."""
    out: dict[str, dict] = {}
    for r in rows:
        if r.get("verdict") not in ("drop", "no_drop") or r.get("change_pct") is None:
            continue
        m = out.setdefault(r["action"], {"n": 0, "sum": 0.0, "drops": 0})
        m["n"] += 1
        m["sum"] += float(r["change_pct"])
        m["drops"] += r["verdict"] == "drop"
    return {k: {"n": v["n"], "mean_change_pct": round(v["sum"] / v["n"], 1), "drops": v["drops"]} for k, v in out.items()}
