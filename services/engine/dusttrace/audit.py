"""Sensor Audit (PRD F1): how far to trust each site's own dust sensor, 0-100.

BMC makes every active site install a PM monitor, but the developer being monitored owns, places and
maintains it. Until BMC shares that feed (it needs an MoU), the sensors here are simulated from the
real ambient series and real weather, with labelled faults injected, so the audit can be measured on
them. Every simulated reading is flagged synthetic.

A sensor reads: ambient PM + near-field dust while the site works + the site's own plume when the
sensor is downwind. Work stops at night (dusty work is banned 22:00-06:00), so night hours compare
the sensor with the stations without any site influence; the drift and humidity checks use them.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import plume

FAULTS = ("none", "flatline", "dropout", "too_clean", "drift", "rh_bias")
IST_H = 5.5
WORK = (8, 19)  # site working hours, IST
NEAR_FIELD = {"demolition": 35.0, "excavation": 25.0, "debris": 20.0, "structure": 12.0}  # ug/m3 at the gate
WINDOW_DAYS = 7
SIM_DAYS = 14

# Trust bands. D5 acts below 40.
TRUSTED, UNTRUSTED = 70, 40

# check -> points lost when it fails
PENALTY = {"flatline": 35, "dropout": 35, "neighbour": 25, "work_signature": 15,
           "humidity": 15, "placement": 40, "drift": 20}


@dataclass(frozen=True)
class SensorSpec:
    sensor_id: str
    site_id: str
    site_lat: float
    site_lon: float
    area_m2: float
    activity: str
    fault: str = "none"  # injected fault, ground truth for the simulator
    bearing_deg: float = 90.0  # where the sensor sits, seen from the site centre

    @property
    def position(self) -> tuple[float, float]:
        d = math.sqrt(self.area_m2) / 2 + 15  # at the boundary, by the gate
        b = math.radians(self.bearing_deg)
        lat = self.site_lat + d * math.cos(b) / plume.M_PER_DEG_LAT
        lon = self.site_lon + d * math.sin(b) / (plume.M_PER_DEG_LAT * math.cos(math.radians(self.site_lat)))
        return lat, lon


@dataclass
class AuditResult:
    sensor_id: str
    site_id: str
    score: float
    band: str
    checks: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def band(score: float) -> str:
    return "trusted" if score >= TRUSTED else ("untrusted" if score < UNTRUSTED else "check")


# ---------- deterministic noise: the same sensor and hour always get the same value ----------

def _uniform(sensor_id: str, hours: np.ndarray, salt: int) -> np.ndarray:
    x = (hours.astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15)) ^ np.uint64(zlib.crc32(sensor_id.encode()) * 1_000_003 + salt)
    x ^= x >> np.uint64(33)
    x *= np.uint64(0xFF51AFD7ED558CCD)
    x ^= x >> np.uint64(33)
    x *= np.uint64(0xC4CEB9FE1A85EC53)
    x ^= x >> np.uint64(33)
    return ((x >> np.uint64(11)).astype(np.float64) + 0.5) / float(1 << 53)


def _normal(sensor_id: str, hours: np.ndarray, salt: int) -> np.ndarray:
    u1, u2 = _uniform(sensor_id, hours, salt), _uniform(sensor_id, hours, salt + 1)
    return np.sqrt(-2 * np.log(u1)) * np.cos(2 * np.pi * u2)


def _epoch_hours(ts: pd.DatetimeIndex) -> np.ndarray:
    return (ts.as_unit("s").asi8 // 3600).astype(np.int64)


def _ist_hour(ts: pd.DatetimeIndex) -> np.ndarray:
    return ((ts.hour + ts.minute / 60 + IST_H) % 24).to_numpy()


def _working(ts: pd.DatetimeIndex) -> np.ndarray:
    h = _ist_hour(ts)
    return (h >= WORK[0]) & (h < WORK[1])


def _night(ts: pd.DatetimeIndex) -> np.ndarray:
    h = _ist_hour(ts)
    return (h >= 22) | (h < 6)


# ---------- simulator ----------

def site_increment(spec: SensorSpec, wx: pd.DataFrame) -> np.ndarray:
    """Modelled PM10 from the site at the sensor, per weather hour, if the site works that hour."""
    lat, lon = spec.position
    q = plume.emission_g_s(spec.area_m2, spec.activity)
    setback = math.sqrt(spec.area_m2)
    out = np.zeros(len(wx))
    ts = pd.DatetimeIndex(wx["ts"])
    working = _working(ts)
    for i, w in enumerate(wx.itertuples()):
        if not working[i]:
            continue
        met = plume.Met(float(w.wind_speed), float(w.wind_dir), float(w.blh), plume.hour_ist(ts[i]))
        x, y = plume.to_plume_frame(spec.site_lat, spec.site_lon, lat, lon, met)
        out[i] = float(plume.concentration(np.array([x]), np.array([y]), q, met, setback)[0])
    return out


def _window(ambient: pd.Series, wx: pd.DataFrame, as_of: pd.Timestamp, days: int) -> tuple[pd.Series, pd.DataFrame]:
    start = as_of.floor("h") - pd.Timedelta(days=days)
    w = wx[(wx["ts"] > start) & (wx["ts"] <= as_of)].reset_index(drop=True)
    amb = ambient.reindex(pd.DatetimeIndex(w["ts"])).interpolate(limit_direction="both")
    return amb, w


def simulate(specs: list[SensorSpec], ambient: pd.Series, wx: pd.DataFrame, as_of: pd.Timestamp,
             days: int = SIM_DAYS) -> pd.DataFrame:
    """Hourly site-sensor readings for the `days` before `as_of`. `ambient` is PM10 indexed by ts."""
    amb, w = _window(ambient, wx, as_of, days)
    ts = pd.DatetimeIndex(w["ts"])
    hrs = _epoch_hours(ts)
    working = _working(ts)
    rh = w["rh"].to_numpy(dtype=float)
    a = amb.to_numpy(dtype=float)
    frames = []
    for s in specs:
        local = NEAR_FIELD.get(s.activity, 15.0) * working * np.exp(0.25 * _normal(s.sensor_id, hrs, 1))
        site = local + site_increment(s, w)
        noise = np.exp(0.06 * _normal(s.sensor_id, hrs, 3))
        pm10 = (a + site) * noise
        pm25 = (0.45 * a + 0.15 * site) * noise  # construction dust is coarse

        day = hrs // 24
        if s.fault == "too_clean":  # upwind or behind a wall: never sees the site, under-reads
            pm10, pm25 = 0.55 * a * noise, 0.25 * a * noise
        elif s.fault == "rh_bias":  # optical sensor over-reads in humid air
            f = 1 + 0.025 * np.clip(rh - 70, 0, None)
            pm10, pm25 = pm10 * f, pm25 * f
        elif s.fault == "drift":  # loses sensitivity between 30-day calibrations
            age = (day + zlib.crc32(s.sensor_id.encode()) % 30) % 30
            f = np.clip(1 - 0.025 * age, 0.25, 1)
            pm10, pm25 = pm10 * f, pm25 * f
        elif s.fault == "flatline":  # stuck from 10:00 IST on about half the days
            stuck_day = _uniform(s.sensor_id, day, 7) < 0.6
            h = _ist_hour(ts)
            stuck = stuck_day & (h >= 10) & (h < WORK[1])
            pm10, pm25 = pm10.copy(), pm25.copy()
            for d in np.unique(day[stuck]):
                idx = np.where((day == d) & stuck)[0]
                pm10[idx], pm25[idx] = pm10[idx[0] - 1], pm25[idx[0] - 1]
        elif s.fault == "dropout":  # switched off while the site works, on most days
            off = (_uniform(s.sensor_id, day, 9) < 0.7) & working
            pm10, pm25 = np.where(off, np.nan, pm10), np.where(off, np.nan, pm25)

        frames.append(pd.DataFrame({"sensor_id": s.sensor_id, "site_id": s.site_id, "ts": ts,
                                    "pm10": pm10, "pm25": pm25, "rh": rh, "fault": s.fault}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["sensor_id", "site_id", "ts", "pm10", "pm25", "rh", "fault"])


# ---------- audit ----------

def _longest_run(mask: np.ndarray) -> int:
    best = cur = 0
    for m in mask:
        cur = cur + 1 if m else 0
        best = max(best, cur)
    return best


def _check(ok: bool, value, reason) -> dict:
    """One check's result. A value that couldn't be computed (not enough data) is None and passes.
    `reason` is a callable, so the sentence is only built when the check fails."""
    v = None if value is None or not np.isfinite(value) else round(float(value), 4)
    return {"ok": bool(ok), "value": v, "reason": None if ok else reason()}


def score(spec: SensorSpec, readings: pd.DataFrame, ambient: pd.Series, wx: pd.DataFrame,
          as_of: pd.Timestamp, days: int = WINDOW_DAYS) -> AuditResult:
    """Six checks over the `days` before `as_of`; each failure costs PENALTY points."""
    amb, w = _window(ambient, wx, as_of, days)
    ts = pd.DatetimeIndex(w["ts"])
    r = readings[readings["sensor_id"] == spec.sensor_id].set_index("ts")["pm10"].reindex(ts)
    pm = r.to_numpy(dtype=float)
    a = amb.to_numpy(dtype=float)
    rh = w["rh"].to_numpy(dtype=float)
    working, night = _working(ts), _night(ts)
    have = ~np.isnan(pm)
    checks = {}

    # 1-2. Dropout and flatline: 3+ hours in a row while the site works. Nights break a run.
    off = np.isnan(pm) & working
    checks["dropout"] = _check(_longest_run(off) < 3, _longest_run(off),
                               lambda: f"Offline for {int(off.sum())} of {int(working.sum())} working hours in the last {days} days.")
    flat = np.zeros(len(pm), dtype=bool)
    flat[1:] = have[1:] & have[:-1] & (np.abs(np.diff(pm)) < 0.01)
    flat &= working
    checks["flatline"] = _check(_longest_run(flat) + 1 < 3, _longest_run(flat) + 1,
                                lambda: f"Stuck at one value for {int(flat.sum())} working hours in the last {days} days.")

    ratio = pm / np.maximum(a, 1.0)
    excess = pm - a

    # 3. Neighbour consistency: a sensor next to a dust source shouldn't read below the stations.
    med = np.nanmedian(ratio) if have.any() else np.nan
    checks["neighbour"] = _check(not (med < 0.85), med,
                                 lambda: f"Reads {round((1 - med) * 100)}% below the ward stations.")

    # 4. Working-hours signature: an active site raises PM while it works.
    rise = np.nanmedian(excess[working & have]) - np.nanmedian(excess[night & have]) \
        if (working & have).any() and (night & have).any() else np.nan
    checks["work_signature"] = _check(not (rise < 5), rise, lambda: "No rise in PM10 during working hours.")

    # 5. Placement: when the model puts the sensor downwind of its own site, it must read above ambient.
    inc = site_increment(spec, w)
    down = (inc > 20) & have
    placed = np.nanmedian(excess[down]) if down.sum() >= 3 else np.nan
    checks["placement"] = _check(not (placed < 0), placed,
                                 lambda: "Cleaner than the stations even when downwind of its own site.")

    # 6. Humidity bias: at night (no site dust) the ratio to the stations shouldn't climb with RH.
    n = night & have
    slope = np.nan
    if n.sum() >= 24 and np.ptp(rh[n]) >= 15:
        slope = np.polyfit(rh[n], np.log(np.maximum(ratio[n], 1e-3)), 1)[0]
    checks["humidity"] = _check(not (slope > 0.006), slope,
                                lambda: f"Over-reads in humid hours (+{round(slope * 1000)}% per 10% RH).")

    # 7. Calibration drift: the night ratio to the stations shouldn't trend.
    nights = pd.Series(ratio[n], index=ts[n] + pd.Timedelta(hours=IST_H - 12)).groupby(lambda t: t.date()).median()
    drift = np.nan
    if len(nights) >= 4:
        drift = np.polyfit(np.arange(len(nights)), nights.to_numpy(), 1)[0]
    checks["drift"] = _check(not (abs(drift) > 0.012), drift,
                             lambda: f"Drifting {abs(round(drift * 100, 1))}% a day against the stations; calibration may be overdue.")

    lost = sum(PENALTY[k] for k, c in checks.items() if not c["ok"])
    sc = float(max(0, 100 - lost))
    reasons = [c["reason"] for k, c in sorted(checks.items(), key=lambda kv: -PENALTY[kv[0]]) if not c["ok"]]
    return AuditResult(spec.sensor_id, spec.site_id, sc, band(sc), checks, reasons)


def benchmark(ambient: pd.Series, wx: pd.DataFrame, as_of: pd.Timestamp, n: int = 50) -> dict:
    """Simulate `n` sensors with faults injected in rotation and measure how well the audit finds them."""
    acts = list(NEAR_FIELD)
    specs = [SensorSpec(sensor_id=f"bench-{i:03d}", site_id="bench", site_lat=19.115 + 0.002 * (i % 7),
                        site_lon=72.86 + 0.002 * (i % 5), area_m2=3000 + 700 * (i % 9),
                        activity=acts[i % len(acts)], fault=FAULTS[i % len(FAULTS)],
                        bearing_deg=(37 * i) % 360) for i in range(n)]
    sim = simulate(specs, ambient, wx, as_of)
    tp = fp = fn = tn = 0
    by_fault: dict[str, list[bool]] = {}
    for s in specs:
        res = score(s, sim, ambient, wx, as_of)
        flagged = any(not c["ok"] for c in res.checks.values())
        faulty = s.fault != "none"
        tp += flagged and faulty
        fp += flagged and not faulty
        fn += (not flagged) and faulty
        tn += (not flagged) and not faulty
        by_fault.setdefault(s.fault, []).append(flagged)
    return {
        "n": n,
        "precision": round(tp / (tp + fp), 3) if tp + fp else 1.0,
        "recall": round(tp / (tp + fn), 3) if tp + fn else 1.0,
        "detected": {f: round(sum(v) / len(v), 2) for f, v in by_fault.items()},
    }


def hot_hours(readings: pd.DataFrame, ambient: pd.Series, as_of: pd.Timestamp) -> dict[str, int]:
    """Per sensor: the latest working hours in a row, up to `as_of`, reading above twice the ambient (D4)."""
    out = {}
    for sid, g in readings[readings["ts"] <= as_of].sort_values("ts").groupby("sensor_id"):
        ts = pd.DatetimeIndex(g["ts"])
        amb = ambient.reindex(ts).interpolate(limit_direction="both").to_numpy(dtype=float)
        hot = (g["pm10"].to_numpy(dtype=float) > 2 * amb) & _working(ts)
        n = 0
        for h in hot[::-1]:
            if not h:
                break
            n += 1
        out[str(sid)] = n
    return out
