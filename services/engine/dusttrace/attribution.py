"""Attribute and prioritise (PRD F4): which sites to inspect today, and why.

For each forecast hour that is likely to spike, trace the wind back from every station for a few
hours. A site close to that back-trajectory is upwind of the station when it matters. Its priority
combines that with the other signals:

    priority = w1·upwind + w2·(1 − trust) + w3·citizen reports + w4·unsensored + w5·past violations

Weights are hand-tuned to start (PRD) and can later be learned from inspection outcomes.
Every ranked site carries its two largest components as plain reasons.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

M_PER_DEG_LAT = 111_320.0
WEIGHTS = {"upwind": 0.35, "trust": 0.25, "reports": 0.15, "unsensored": 0.15, "violations": 0.10}
SPIKE_P = 0.4        # forecast hours below this exceedance probability don't count
BACK_HOURS = 3       # how far back each trajectory goes
SIGMA_M = 250.0      # trajectory half-width near the station; widens with distance
DECAY_M = 3000.0     # nearer sources matter more


@dataclass
class Ranked:
    site_id: str
    name: str
    rank: int
    score: float
    components: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    upwind_hours: int = 0


def _xy(lat0: float, lon0: float, lat: float, lon: float) -> tuple[float, float]:
    """East, north metres from (lat0, lon0)."""
    return ((lon - lon0) * M_PER_DEG_LAT * math.cos(math.radians(lat0)), (lat - lat0) * M_PER_DEG_LAT)


def back_trajectory(lat: float, lon: float, wx: pd.DataFrame) -> list[tuple[float, float]]:
    """Points (lat, lon) the air passed through, starting at the station and stepping back one hour
    at a time through `wx` (chronological; the last row is the arrival hour)."""
    pts = [(lat, lon)]
    for w in wx.iloc[::-1].itertuples():
        d = float(w.wind_speed) * 3600.0
        b = math.radians(float(w.wind_dir))  # the wind comes FROM here, so the air came from here
        north, east = d * math.cos(b), d * math.sin(b)
        lat = lat + north / M_PER_DEG_LAT
        lon = lon + east / (M_PER_DEG_LAT * math.cos(math.radians(lat)))
        pts.append((lat, lon))
    return pts


def _along_cross(pts: list[tuple[float, float]], lat: float, lon: float) -> tuple[float, float] | None:
    """Distance along the trajectory and across it to the site, or None if the site is behind the station."""
    lat0, lon0 = pts[0]
    xy = [_xy(lat0, lon0, a, b) for a, b in pts]
    sx, sy = _xy(lat0, lon0, lat, lon)
    best, done = None, 0.0
    for i in range(len(xy) - 1):
        (ax, ay), (bx, by) = xy[i], xy[i + 1]
        dx, dy = bx - ax, by - ay
        seg = math.hypot(dx, dy)
        if seg < 1:
            continue
        t = ((sx - ax) * dx + (sy - ay) * dy) / seg ** 2
        if not (i == 0 and t <= 0):  # on the first leg, t <= 0 means downwind of the station
            tc = min(t, 1.0) if i == 0 else min(max(t, 0.0), 1.0)
            cross = math.hypot(sx - (ax + tc * dx), sy - (ay + tc * dy))
            if best is None or cross < best[1]:
                best = (done + tc * seg, cross)
        done += seg
    return best


def upwind_details(sites: list[dict], stations: list[dict], wx: pd.DataFrame, p_exceed: pd.Series) -> dict:
    """Per site: exposure 0-1 (mean over the forecast hours of p × closeness to the nearest station
    back-trajectory), the station it most often sits upwind of, and how many likely-spike hours."""
    wx = wx.sort_values("ts").reset_index(drop=True)
    best: dict[str, dict] = {s["id"]: {} for s in sites}  # site -> ts -> (p × closeness, station name)
    for i, w in wx.iterrows():
        p = float(p_exceed.get(pd.Timestamp(w["ts"]), 0.0))
        if p < SPIKE_P:
            continue
        window = wx.iloc[max(0, i - BACK_HOURS + 1): i + 1]
        for st in stations:
            traj = back_trajectory(st["lat"], st["lon"], window)
            for s in sites:
                ac = _along_cross(traj, s["lat"], s["lon"])
                if ac is None:
                    continue
                along, cross = ac
                sigma = SIGMA_M + 0.15 * along
                v = p * math.exp(-cross ** 2 / (2 * sigma ** 2)) * math.exp(-along / DECAY_M)
                if v > best[s["id"]].get(w["ts"], (0.0, None))[0]:
                    best[s["id"]][w["ts"]] = (v, st.get("name", st["id"]))
    out = {}
    for s in sites:
        hours = best[s["id"]]
        strong = [name for v, name in hours.values() if v > 0.1]
        out[s["id"]] = {
            "exposure": round(sum(v for v, _ in hours.values()) / max(len(wx), 1), 4),
            "hours": len(strong),
            "station": max(set(strong), key=strong.count) if strong else None,
        }
    return out


def upwind_exposure(sites: list[dict], stations: list[dict], wx: pd.DataFrame, p_exceed: pd.Series) -> dict:
    return {k: v["exposure"] for k, v in upwind_details(sites, stations, wx, p_exceed).items()}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def rank(rows: list[dict], weights: dict = WEIGHTS) -> list[Ranked]:
    """`rows`: site_id, name, upwind (0-1), trust (0-100 or None), has_sensor, and optionally reports,
    violations, upwind_station, upwind_hours. Returns sites in inspection order."""
    out = []
    for r in rows:
        trust, has = r.get("trust"), bool(r.get("has_sensor"))
        reports, violations = int(r.get("reports") or 0), int(r.get("violations") or 0)
        comp = {
            "upwind": weights["upwind"] * float(r.get("upwind") or 0),
            "trust": weights["trust"] * (1 - float(trust) / 100) if has and trust is not None else 0.0,
            "reports": weights["reports"] * min(reports / 3, 1),
            "unsensored": weights["unsensored"] * (0.0 if has else 1.0),
            "violations": weights["violations"] * min(violations / 2, 1),
        }
        say = {
            "upwind": f"Sits upwind of {r.get('upwind_station') or 'a station'} for "
                      f"{_plural(int(r.get('upwind_hours') or 0), 'likely-spike hour')}.",
            "trust": f"Its dust monitor scores {round(float(trust or 0))}/100.",
            "reports": f"{_plural(reports, 'citizen report')} this week.",
            "unsensored": "Active site with no dust monitor.",
            "violations": f"{_plural(violations, 'confirmed violation')} in the last 30 days.",
        }
        top = [k for k, v in sorted(comp.items(), key=lambda kv: -kv[1]) if v > 0.005][:2]
        reasons = [say[k] for k in top] or ["Nothing points here in this forecast."]
        out.append(Ranked(r["site_id"], r.get("name", r["site_id"]), 0, round(100 * sum(comp.values()), 1),
                          {k: round(100 * v, 1) for k, v in comp.items()}, reasons, int(r.get("upwind_hours") or 0)))
    out.sort(key=lambda x: (-x.score, x.site_id))
    for i, x in enumerate(out, 1):
        x.rank = i
    return out
