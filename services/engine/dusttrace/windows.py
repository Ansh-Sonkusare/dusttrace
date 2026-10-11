"""Safe-Work Windows: for each site and forecast hour, would dusty work put dust on people?

Rules (milestone 1, deliberately simple and explainable):
- AVOID  if a school or hospital would get more than `avoid_threshold` ug/m3 from this site,
         or any receptor would get more than `avoid_threshold` while the ward forecast says
         PM10 is likely (p >= 0.6) to exceed the standard anyway.
- CAUTION if any receptor would get more than `caution_threshold`,
         or the ward is likely to exceed the standard (p >= 0.6).
- GO     otherwise.
Each status carries a one-line reason the site manager can read.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import plume
from .config import Settings

COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def compass(deg: float) -> str:
    return COMPASS[int((deg % 360) / 22.5 + 0.5) % 16]


@dataclass
class SiteHour:
    site_id: str
    ts: pd.Timestamp
    ring: list
    max_conc: float
    length_m: float
    exposures: list[tuple[str, float]] = field(default_factory=list)  # (receptor_id, conc)
    status: str = "go"
    exposed_people: int = 0
    sensitive_hit: bool = False
    reason: str = ""


def evaluate(sites: pd.DataFrame, receptors: pd.DataFrame, wx_future: pd.DataFrame,
             ward_p_exceed: pd.Series, settings: Settings) -> list[SiteHour]:
    """`wx_future` has ts, wind_speed, wind_dir, blh. `ward_p_exceed` is indexed by ts."""
    out: list[SiteHour] = []
    rec = receptors.reset_index(drop=True)
    for _, s in sites.iterrows():
        q = plume.emission_g_s(float(s["area_m2"]), s["activity"])
        setback = math.sqrt(float(s["area_m2"]))
        for _, w in wx_future.iterrows():
            ts = pd.Timestamp(w["ts"])
            met = plume.Met(float(w["wind_speed"]), float(w["wind_dir"]), float(w["blh"]), plume.hour_ist(ts))
            fp = plume.footprint(s["lat"], s["lon"], q, met, setback, settings.plume_threshold)
            sh = SiteHour(str(s["id"]), ts, fp.ring, fp.max_conc, fp.length_m)

            if len(rec):
                xy = [plume.to_plume_frame(s["lat"], s["lon"], r.lat, r.lon, met) for r in rec.itertuples()]
                xs = np.array([p[0] for p in xy])
                ys = np.array([p[1] for p in xy])
                conc = plume.concentration(xs, ys, q, met, setback)
                worst = None
                for r, c in zip(rec.itertuples(), conc):
                    if c >= settings.caution_threshold:
                        sh.exposures.append((r.id, float(c)))
                        sh.exposed_people += int(r.population)
                        if r.kind in ("school", "hospital") and c >= settings.avoid_threshold:
                            sh.sensitive_hit = True
                        if worst is None or c > worst[1]:
                            worst = (r, float(c))
            else:
                worst = None

            p_ex = float(ward_p_exceed.get(ts, 0.0)) if len(ward_p_exceed) else 0.0
            wind_txt = f"wind {met.wind_speed:.1f} m/s from {compass(met.wind_dir)}, mixing layer {met.blh:.0f} m"
            if sh.sensitive_hit or (worst and worst[1] >= settings.avoid_threshold and p_ex >= 0.6):
                sh.status = "avoid"
                r, c = worst
                sh.reason = f"Plume reaches {r.name} (~{c:.0f} µg/m³ added); {wind_txt}"
            elif worst is not None or p_ex >= 0.6:
                sh.status = "caution"
                if worst is not None:
                    r, c = worst
                    sh.reason = f"Light dust reaches {r.name} (~{c:.0f} µg/m³ added); {wind_txt}"
                else:
                    sh.reason = f"Ward PM10 likely above 100 (p={p_ex:.2f}); {wind_txt}"
            else:
                sh.status = "go"
                sh.reason = f"Plume clears sensitive places; {wind_txt}"
            out.append(sh)
    return out
