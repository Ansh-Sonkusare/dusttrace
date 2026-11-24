"""Attribute and prioritise (PRD F4): which sites to inspect today, and why.

For each forecast hour that is likely to spike, trace the wind back from every station for a few
hours. A site close to that back-trajectory is upwind of the station when it matters. Its priority
combines that with the other signals:

    priority = w1·upwind + w2·(1 − trust) + w3·citizen reports + w4·unsensored + w5·past violations

Weights are hand-tuned to start (PRD) and can later be learned from inspection outcomes.
Every ranked site carries its two largest components as plain reasons.

D8 (issue #56) attributes measured exceedances more strictly: a back-trajectory reaches several km, which in
a polluted week puts every site upwind of some exceedance, so a measured hour counts for a site only when
the site's own plume added a material share at that station.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import plume

M_PER_DEG_LAT = 111_320.0
WEIGHTS = {"upwind": 0.35, "trust": 0.25, "reports": 0.15, "unsensored": 0.15, "violations": 0.10}
SPIKE_P = 0.4        # forecast hours below this exceedance probability don't count
BACK_HOURS = 3       # how far back each trajectory goes
SIGMA_M = 250.0      # trajectory half-width near the station; widens with distance
DECAY_M = 3000.0     # nearer sources matter more
# D8: the site's own modelled plume must add at least this at the station in the measured weather; the same
# increment that puts a school, hospital or home into Caution (Settings.caution_threshold).
ADDED_MIN = 15.0
CALM_MS = 1.0        # below this the hourly wind direction is too unsteady to say which side of a station a site sat on
REACH_M = 4000.0     # a station further away can't speak for a site (as for PM signatures and fix checks)
SHARE = 0.5          # a station hour goes only to sites adding at least this share of the largest site's increment
LOCAL = 1.5          # a station this many times the median of the others that hour has a local source
IST = pd.Timedelta(hours=5.5)


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


def local_exceedances(rd: pd.DataFrame, threshold: float = 100.0, local: float = LOCAL) -> pd.DataFrame:
    """Measured hours above `threshold` at a station that also stood at least `local` times the median of the
    other stations that hour (`background`): a local source, not the haze over the whole city. In a Mumbai
    winter most station hours are above 100 µg/m³ everywhere at once. An hour with fewer than two other
    stations reporting can't tell the two apart and is left out."""
    if rd.empty:
        return rd.assign(background=pd.Series(dtype=float))
    w = rd.pivot_table(index="ts", columns="station_id", values="pm10")
    bg = {}
    for sid in w.columns:
        others = w.drop(columns=sid)
        bg[sid] = others.median(axis=1).where(others.notna().sum(axis=1) >= 2)
    bg = (pd.DataFrame(bg, index=w.index).rename_axis("ts").reset_index()
          .melt(id_vars="ts", var_name="station_id", value_name="background").dropna())
    out = rd.merge(bg, on=["ts", "station_id"])
    return out[(out["pm10"] > threshold) & (out["pm10"] >= local * out["background"])].reset_index(drop=True)


def measured_exceedances(sites: list[dict], stations: list[dict], readings: pd.DataFrame, wx: pd.DataFrame,
                         now: pd.Timestamp, days: int = 7, threshold: float = 100.0,
                         added_min: float = ADDED_MIN) -> dict[str, list[dict]]:
    """Per site, the hours in the last `days` IST days up to `now` (nothing after it) when a real station measured
    PM10 above `threshold` and the site's own plume, in that hour's measured wind and mixing height, added at
    least `added_min` µg/m³ at the station (D8, issue #56), oldest first. `sites` carry lat, lon, area_m2, activity.

    The plume is the one the Safe-Work Windows use, so it is zero upwind of the site and fades within a
    kilometre or two. A station more than REACH_M from a site never speaks for it, and an hour several sites
    could explain goes only to those adding at least SHARE of the largest increment (`shared_with` counts the
    others). Synthetic and CAMS-filled readings never count, nor do forecast, synthetic or light-wind weather
    hours; an hour without measured weather is skipped, not guessed. Pass `local_exceedances` first to keep
    city-wide haze out.
    """
    out: dict[str, list[dict]] = {s["id"]: [] for s in sites}
    start = (now + IST).normalize() - pd.Timedelta(days=days - 1) - IST
    rd = readings[(readings["ts"] >= start) & (readings["ts"] <= now)
                  & (readings["pm10"] > threshold) & ~readings["synthetic"].astype(bool)]
    if "filled" in rd:
        rd = rd[~rd["filled"].astype(bool)]
    w = wx[~wx["synthetic"].astype(bool) & ~wx["is_forecast"].astype(bool) & (wx["ts"] <= now)]
    w = w.dropna(subset=["wind_speed", "wind_dir", "blh"]).set_index("ts")
    by_id = {s["id"]: s for s in stations}
    src = [(s, plume.emission_g_s(float(s["area_m2"]), s["activity"]), math.sqrt(float(s["area_m2"]))) for s in sites]
    for r in rd.sort_values(["ts", "station_id"]).itertuples():
        st = by_id.get(r.station_id)
        if st is None or r.ts not in w.index or w.loc[r.ts, "wind_speed"] < CALM_MS:
            continue
        m = w.loc[r.ts]
        met = plume.Met(float(m["wind_speed"]), float(m["wind_dir"]), float(m["blh"]), plume.hour_ist(r.ts))
        hits = []
        for s, q, setback in src:
            if math.hypot(*_xy(st["lat"], st["lon"], s["lat"], s["lon"])) > REACH_M:
                continue
            x, y = plume.to_plume_frame(s["lat"], s["lon"], st["lat"], st["lon"], met)
            added = float(plume.concentration(np.array([x]), np.array([y]), q, met, setback)[0])
            if added >= added_min:
                hits.append((s["id"], added))
        kept = [(sid, a) for sid, a in hits if a >= SHARE * max((a for _, a in hits), default=0.0)]
        for sid, added in kept:
            out[sid].append({
                "station_id": r.station_id, "station": st.get("name", r.station_id), "ts": r.ts,
                "pm10": round(float(r.pm10), 1), "pm25": None if pd.isna(r.pm25) else round(float(r.pm25), 1),
                "background": round(float(r.background), 1) if "background" in rd else None,
                "wind_dir": round(met.wind_dir), "wind_speed": round(met.wind_speed, 1), "added": round(added, 1),
                "shared_with": len(kept) - 1})
    return out


def by_ist_day(hours: list[dict]) -> dict[str, list[dict]]:
    """Attributed hours grouped by IST date: D8 counts days, so one bad evening is one exceedance, not six."""
    days: dict[str, list[dict]] = {}
    for h in sorted(hours, key=lambda h: h["ts"]):
        days.setdefault((pd.Timestamp(h["ts"]) + IST).strftime("%Y-%m-%d"), []).append(h)
    return days


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
            "unsensored": weights["unsensored"] * (0.0 if has or not r.get("sensor_known", True) else 1.0),
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
