"""Safe-Work Windows: for each site and forecast hour, would dusty work put dust on people?

Rules (milestone 1, deliberately simple and explainable):
- AVOID  if a school or hospital would get more than `avoid_threshold` ug/m3 from this site,
         or any receptor would get more than `avoid_threshold` while the ward forecast says
         PM10 is likely (p >= 0.6) to exceed the standard anyway.
- CAUTION if any receptor would get more than `caution_threshold`,
         or the ward is likely to exceed the standard (p >= 0.6).
- GO     otherwise.
Each status carries a one-line reason the site manager can read.

Rain (issue #59): wet ground makes less dust. US EPA AP-42 Section 13.2.1 (Paved Roads, 01/2011), Equation 3,
corrects dust for rain by (1 - 1.2 P/N), P being the hours with at least 0.254 mm (0.01 in) of rain out of N.
Its note for hour-by-hour modelling (p. 13.2.1-6): an hour of rain makes no dust, and the extra 20% "credit"
goes to the first hours after the rain stops, one hour for each hour of rain, up to 12. So `rain_effect`
gives a rainy hour a dust factor of 0 and each credited hour after it 0.8, and `evaluate` scales the site's
emission by it. Open-Meteo's rain at an hour fell in the hour before it, so a rainy hour starts on wet ground.
AP-42 derives the rule for road dust, by analogy with unpaved roads (13.2.2); a demolition site may still raise
some dust in the rain.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import plume
from .config import Settings

RAIN_MM = 0.254      # AP-42's measurable rain: 0.01 in
WET_CREDIT = 0.8     # dust factor in the hours after rain (AP-42's 20% credit)
WET_CREDIT_MAX_H = 12

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
    person_exposure: float = 0.0     # people x increment (µg/m³) over every receptor, however faint
    person_exposure_15: float = 0.0  # the part over `exposures`, the receptors given 15 µg/m³ or more
    sensitive_hit: bool = False
    reason: str = ""


def rain_effect(wx: pd.DataFrame) -> pd.DataFrame:
    """Per hour of `wx` (ts, precip; in time order): ts, the share of a site's dust that still rises (`dust_factor`) and
    the hours since the rain stopped (`rain_since`: 0 while it rains, empty when no credit is left)."""
    rows, credit, last = [], 0, None
    for ts, mm in zip(wx["ts"], wx["precip"].astype(float).fillna(0.0)):
        if mm >= RAIN_MM:
            credit, last = min(credit + 1, WET_CREDIT_MAX_H), ts
            rows.append((ts, 0.0, 0))
        elif credit:
            credit -= 1
            rows.append((ts, WET_CREDIT, round((ts - last) / pd.Timedelta(hours=1))))
        else:
            rows.append((ts, 1.0, None))
    return pd.DataFrame(rows, columns=["ts", "dust_factor", "rain_since"])


def _rain_text(factor: float, mm: float, since) -> str:
    if factor == 0:
        return f"rain ({mm:.1f} mm) keeps the dust down"
    return f"ground still wet from rain {int(since)} h ago cuts the dust by {round((1 - factor) * 100)}%"


def evaluate(sites: pd.DataFrame, receptors: pd.DataFrame, wx_future: pd.DataFrame,
             ward_p_exceed: pd.Series, settings: Settings) -> list[SiteHour]:
    """`wx_future` has ts, wind_speed, wind_dir, blh, and optionally precip with `rain_effect`'s columns.
    `ward_p_exceed` is indexed by ts."""
    out: list[SiteHour] = []
    rec = receptors.reset_index(drop=True)
    for _, s in sites.iterrows():
        q = plume.emission_g_s(float(s["area_m2"]), s["activity"])
        setback = math.sqrt(float(s["area_m2"]))
        for _, w in wx_future.iterrows():
            ts = pd.Timestamp(w["ts"])
            met = plume.Met(float(w["wind_speed"]), float(w["wind_dir"]), float(w["blh"]), plume.hour_ist(ts))
            k = float(w["dust_factor"]) if pd.notna(w.get("dust_factor")) else 1.0
            q_h = q * k
            fp = plume.footprint(s["lat"], s["lon"], q_h, met, setback, settings.plume_threshold)
            sh = SiteHour(str(s["id"]), ts, fp.ring, fp.max_conc, fp.length_m)

            if len(rec):
                xy = [plume.to_plume_frame(s["lat"], s["lon"], r.lat, r.lon, met) for r in rec.itertuples()]
                xs = np.array([p[0] for p in xy])
                ys = np.array([p[1] for p in xy])
                conc = plume.concentration(xs, ys, q_h, met, setback)
                sh.person_exposure = float((rec["population"].to_numpy(dtype=float) * conc).sum())
                worst = None
                for r, c in zip(rec.itertuples(), conc):
                    if c >= settings.caution_threshold:
                        sh.exposures.append((r.id, float(c)))
                        sh.exposed_people += int(r.population)
                        sh.person_exposure_15 += float(r.population) * float(c)
                        if r.kind in ("school", "hospital") and c >= settings.avoid_threshold:
                            sh.sensitive_hit = True
                        if worst is None or c > worst[1]:
                            worst = (r, float(c))
            else:
                worst = None

            p_ex = float(ward_p_exceed.get(ts, 0.0)) if len(ward_p_exceed) else 0.0
            wind_txt = f"wind {met.wind_speed:.1f} m/s from {compass(met.wind_dir)}, mixing layer {met.blh:.0f} m"
            if k < 1:
                wind_txt += f"; {_rain_text(k, float(w['precip']), w['rain_since'])}"
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
