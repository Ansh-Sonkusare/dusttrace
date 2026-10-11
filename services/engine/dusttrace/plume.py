"""Gaussian plume model for ground-level construction dust.

For each site and forecast hour we estimate the PM10 *increment* the site would add at ground level
if dusty work ran that hour, then (a) trace the footprint above a threshold as a polygon for the map
and (b) read the increment at each school, hospital and housing receptor.

Assumptions (documented, to be calibrated against DustTrace Nodes in the pilot):
- Ground-level area source, treated as a virtual point source set back by the site's width.
- Urban dispersion coefficients (Briggs / McElroy-Pooler) by Pasquill stability class.
- Stability from wind speed and daylight (no cloud data): unstable on calm sunny days,
  stable on calm nights.
- Hourly wind-direction meander widens the plume sideways (more on calm hours).
- When the plume fills the mixing layer, concentration becomes uniform in the vertical.
- Emission rate from AP-42 construction factors (1.2 short tons TSP / acre / month over 260 working
  hours, PM10 ~30% of TSP), scaled by activity type.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

M_PER_DEG_LAT = 111_320.0
IST_OFFSET_H = 5.5

# PM10 emission per m2 of active site, g/s, before the activity multiplier.
BASE_EMISSION_G_S_M2 = 8.6e-5
ACTIVITY_FACTOR = {"demolition": 3.0, "excavation": 2.0, "debris": 1.5, "structure": 1.0}


@dataclass(frozen=True)
class Met:
    wind_speed: float  # m/s
    wind_dir: float    # deg, FROM
    blh: float         # m
    hour_ist: float    # local hour, 0-24


def emission_g_s(area_m2: float, activity: str) -> float:
    return BASE_EMISSION_G_S_M2 * area_m2 * ACTIVITY_FACTOR.get(activity, 1.0)


def stability_class(met: Met) -> str:
    day = 7 <= met.hour_ist < 18
    u = met.wind_speed
    if day:
        return "AB" if u < 2 else ("C" if u < 5 else "D")
    return "EF" if u < 3 else "D"


def sigmas(x: np.ndarray, cls: str) -> tuple[np.ndarray, np.ndarray]:
    """Urban dispersion coefficients sigma_y, sigma_z (m) at downwind distance x (m)."""
    x = np.maximum(x, 1.0)
    if cls == "AB":
        sy = 0.32 * x * (1 + 0.0004 * x) ** -0.5
        sz = 0.24 * x * (1 + 0.001 * x) ** 0.5
    elif cls == "C":
        sy = 0.22 * x * (1 + 0.0004 * x) ** -0.5
        sz = 0.20 * x
    elif cls == "D":
        sy = 0.16 * x * (1 + 0.0004 * x) ** -0.5
        sz = 0.14 * x * (1 + 0.0003 * x) ** -0.5
    else:  # EF
        sy = 0.11 * x * (1 + 0.0004 * x) ** -0.5
        sz = 0.08 * x * (1 + 0.0015 * x) ** -0.5
    return sy, sz


def meander(met: Met) -> float:
    """Hourly wind-direction wobble (radians). Calm hours swing more, which widens the hourly plume."""
    u = met.wind_speed
    return 0.30 if u < 1.5 else (0.20 if u < 3 else 0.12)


def sigma_y_eff(x: np.ndarray, sy: np.ndarray, met: Met) -> np.ndarray:
    return np.sqrt(sy ** 2 + (meander(met) * x) ** 2)


def concentration(x: np.ndarray, y: np.ndarray, q_g_s: float, met: Met, setback_m: float) -> np.ndarray:
    """Ground-level PM10 increment (ug/m3) at downwind x and crosswind y (m). Zero upwind."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    u = max(met.wind_speed, 0.5)
    cls = stability_class(met)
    xe = np.maximum(x, 0) + setback_m
    sy, sz = sigmas(xe, cls)
    sy = sigma_y_eff(xe, sy, met)
    L = max(met.blh, 50.0)
    lateral = np.exp(-(y ** 2) / (2 * sy ** 2))
    gaussian = q_g_s / (math.pi * u * sy * sz) * lateral          # full ground reflection
    mixed = q_g_s / (math.sqrt(2 * math.pi) * u * sy * L) * lateral  # well mixed in the layer
    c = np.where(sz < 1.6 * L, gaussian, mixed)
    return np.where(x > 0, c * 1e6, 0.0)  # g/m3 -> ug/m3


def _bearing_to(met: Met) -> float:
    """Direction the plume travels toward, degrees clockwise from north."""
    return (met.wind_dir + 180.0) % 360.0


def to_plume_frame(src_lat: float, src_lon: float, lat: float, lon: float, met: Met) -> tuple[float, float]:
    """Receptor position in the plume frame: (downwind x, crosswind y) in metres."""
    north = (lat - src_lat) * M_PER_DEG_LAT
    east = (lon - src_lon) * M_PER_DEG_LAT * math.cos(math.radians(src_lat))
    b = math.radians(_bearing_to(met))
    x = east * math.sin(b) + north * math.cos(b)
    y = -east * math.cos(b) + north * math.sin(b)
    return x, y


def from_plume_frame(src_lat: float, src_lon: float, x: float, y: float, met: Met) -> tuple[float, float]:
    b = math.radians(_bearing_to(met))
    east = x * math.sin(b) - y * math.cos(b)
    north = x * math.cos(b) + y * math.sin(b)
    lat = src_lat + north / M_PER_DEG_LAT
    lon = src_lon + east / (M_PER_DEG_LAT * math.cos(math.radians(src_lat)))
    return lat, lon


@dataclass
class Footprint:
    ring: list[tuple[float, float]]  # (lon, lat) closed ring, empty if below threshold everywhere
    max_conc: float
    length_m: float


def footprint(src_lat: float, src_lon: float, q_g_s: float, met: Met, setback_m: float,
              threshold: float, max_x: float = 4000.0) -> Footprint:
    """Area where the centreline-and-sideways increment exceeds `threshold`, as a polygon ring."""
    xs = np.geomspace(50, max_x, 60)  # start 50 m out: nearer than that the site boundary dominates
    cls = stability_class(met)
    c0 = concentration(xs, np.zeros_like(xs), q_g_s, met, setback_m)
    max_c = float(c0.max()) if len(c0) else 0.0
    inside = c0 > threshold
    if not inside.any():
        return Footprint([], max_c, 0.0)
    xs_in = xs[inside]
    sy, _ = sigmas(xs_in + setback_m, cls)
    sy = sigma_y_eff(xs_in + setback_m, sy, met)
    half = sy * np.sqrt(2 * np.log(c0[inside] / threshold))
    left = [from_plume_frame(src_lat, src_lon, float(x), float(w), met) for x, w in zip(xs_in, half)]
    right = [from_plume_frame(src_lat, src_lon, float(x), float(-w), met) for x, w in zip(xs_in, half)]
    pts = [(src_lat, src_lon)] + left + right[::-1] + [(src_lat, src_lon)]
    ring = [(lon, lat) for lat, lon in pts]
    return Footprint(ring, max_c, float(xs_in.max()))


def hour_ist(ts) -> float:
    return (ts.hour + ts.minute / 60 + IST_OFFSET_H) % 24
