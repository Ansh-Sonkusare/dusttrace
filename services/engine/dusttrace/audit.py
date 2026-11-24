"""Sensor Audit (PRD F1): how far to trust each site's own dust sensor, 0-100.

BMC makes every active site install a PM monitor, but the developer being monitored owns, places and
maintains it. Until BMC shares that feed (it needs an MoU), the sensors here are simulated from the
real ambient series and real weather, with labelled faults injected, so the audit can be measured on
them. Every simulated reading is flagged synthetic.

A sensor reads: ambient PM at its nearest real station + near-field dust while the site works + the
site's own plume when the sensor is downwind. Work stops at night (dusty work is banned 22:00-06:00),
so night hours compare the sensor with the station without any site influence; the drift and humidity
checks use them. Simulated sensors are calibrated monthly on a fixed schedule; that date is simulated too.

Rule checks give the trust score. An Isolation Forest on each sensor's residuals against its
neighbours (the nearest station, the other site sensors, DustTrace Nodes) is measured beside them on
the same injected faults; `benchmark` reports rules alone, the forest alone and both together. The
forest stays out of the score: on real ambient readings it found no fault the rules missed, and it
flags healthy sensors that sit in their own site's plume, which are the sites with the most dust.
"""

from __future__ import annotations

import math
import zlib
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from . import effect, plume

FAULTS = ("none", "flatline", "dropout", "too_clean", "drift", "rh_bias")
IST_H = 5.5
WORK = (8, 19)  # site working hours, IST
RISE = (9, 18)  # PRD: an active site raises PM between 9 am and 6 pm
NEAR_FIELD = {"demolition": 35.0, "excavation": 25.0, "debris": 20.0, "structure": 12.0}  # ug/m3 at the gate
WINDOW_DAYS = 7
SIM_DAYS = 14

# Trust bands. D5 acts below 40.
TRUSTED, UNTRUSTED = 70, 40

# check -> points lost when it fails
PENALTY = {"flatline": 35, "dropout": 35, "neighbour": 25, "work_signature": 15,
           "humidity": 15, "placement": 40, "drift": 20, "calibration": 15}

CAL_DUE = pd.DateOffset(months=2)  # BMC: calibrate every 2 months
CAL_EVERY_DAYS = 30  # the simulated sensors' schedule
IMAGERY_DAYS = 30  # a Sentinel-2 scene says a site is active for this long after it was taken
SAME_WIND_DEG = 45.0  # wind within this of the bearing to the station carries its air to the sensor
MIN_SAME_WIND_H = 6
CALM = 1.0  # m/s; below this the wind has no direction worth trusting

# Isolation Forest: an hour is unusual when it scores below this quantile of the fault-free sensors it
# was fitted on. Picked on synthetic weather with a separate validation fleet, then frozen.
FOREST_FEATURES = ["r_station", "r_peers", "r_var", "working"]
FOREST_HOUR_Q = 0.05


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    lat: float
    lon: float


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dx = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(lat2 - lat1, dx) * plume.M_PER_DEG_LAT / 1000


@dataclass(frozen=True)
class Ambient:
    """Measured PM10 at the stations: what each sensor is built from and checked against.
    `pm10` is hourly, indexed by UTC hour, one column per station id."""
    stations: tuple[Station, ...]
    pm10: pd.DataFrame

    def _by_distance(self, lat: float, lon: float) -> list[Station]:
        return sorted((s for s in self.stations if s.id in self.pm10), key=lambda s: _km(lat, lon, s.lat, s.lon))

    def nearest(self, lat: float, lon: float) -> Station:
        """The nearest station with PM10 in at least half the hours: one whose PM10 channel went silent
        early in the window can't stand for the air at the sensor."""
        cover = self.pm10.notna().mean()
        return next(s for s in self._by_distance(lat, lon) if cover[s.id] >= 0.5)

    def at(self, lat: float, lon: float, ts: pd.DatetimeIndex) -> tuple[Station, pd.Series]:
        """The nearest station and PM10 over `ts`: its own readings, each hour it missed from the next
        nearest station that measured it, and only hours no station measured interpolated."""
        st = self.nearest(lat, lon)
        pm = self.pm10[st.id].reindex(ts)
        for other in self._by_distance(lat, lon):
            pm = pm.fillna(self.pm10[other.id].reindex(ts))
        return st, pm.interpolate(limit_direction="both")

    def sources(self, station: Station, ts: pd.DatetimeIndex) -> dict[str, int]:
        """Over `ts`, where a sensor on `station` got its ambient: hours the station measured, hours only
        another station measured (taken from it), and hours no station measured (interpolated)."""
        own = self.pm10[station.id].reindex(ts).notna()
        anyone = self.pm10[[s.id for s in self.stations if s.id in self.pm10]].reindex(ts).notna().any(axis=1)
        return {"hours": len(ts), "measured": int(own.sum()), "next_station": int((~own & anyone).sum()),
                "interpolated": int((~anyone).sum())}


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
    calibrated_on: pd.Timestamp | None = None  # last calibration on record; None if there is no record
    imagery: str | None = None  # date of the Sentinel-2 scene that shows the site active; None if none does

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


def _phase(sensor_id: str) -> int:
    return zlib.crc32(sensor_id.encode()) % CAL_EVERY_DAYS


def simulated_calibration(sensor_id: str, as_of: pd.Timestamp) -> pd.Timestamp:
    """A simulated sensor's last calibration on or before `as_of`. The schedule is fixed per sensor, so
    the date never depends on when the audit runs, and the drift fault resets on the same days."""
    day = as_of.floor("D")
    return day - pd.Timedelta(days=(day.value // 86_400_000_000_000 + _phase(sensor_id)) % CAL_EVERY_DAYS)


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


def _window(wx: pd.DataFrame, as_of: pd.Timestamp, days: int) -> pd.DataFrame:
    start = as_of.floor("h") - pd.Timedelta(days=days)
    return wx[(wx["ts"] > start) & (wx["ts"] <= as_of)].reset_index(drop=True)


def simulate(specs: list[SensorSpec], ambient: Ambient, wx: pd.DataFrame, as_of: pd.Timestamp,
             days: int = SIM_DAYS) -> pd.DataFrame:
    """Hourly site-sensor readings for the `days` before `as_of`, each built on its nearest station."""
    w = _window(wx, as_of, days)
    ts = pd.DatetimeIndex(w["ts"])
    hrs = _epoch_hours(ts)
    working = _working(ts)
    rh = w["rh"].to_numpy(dtype=float)
    frames = []
    for s in specs:
        a = ambient.at(*s.position, ts)[1].to_numpy(dtype=float)
        local = NEAR_FIELD.get(s.activity, 15.0) * working * np.exp(0.25 * _normal(s.sensor_id, hrs, 1))
        site = local + site_increment(s, w)
        noise = np.exp(0.06 * _normal(s.sensor_id, hrs, 3))
        pm10 = true = (a + site) * noise
        pm25 = (0.45 * a + 0.15 * site) * noise  # construction dust is coarse

        day = hrs // 24
        if s.fault == "too_clean":  # upwind or behind a wall: never sees the site, under-reads
            pm10, pm25 = 0.55 * a * noise, 0.25 * a * noise
        elif s.fault == "rh_bias":  # optical sensor over-reads in humid air
            f = 1 + 0.025 * np.clip(rh - 70, 0, None)
            pm10, pm25 = pm10 * f, pm25 * f
        elif s.fault == "drift":  # loses sensitivity between its monthly calibrations
            age = (day + _phase(s.sensor_id)) % CAL_EVERY_DAYS
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
                                    "pm10": pm10, "pm25": pm25, "rh": rh, "fault": s.fault, "pm10_true": true}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["sensor_id", "site_id", "ts", "pm10", "pm25", "rh", "fault", "pm10_true"])


def fault_shown(sim: pd.DataFrame, as_of: pd.Timestamp, days: int = WINDOW_DAYS) -> dict[str, bool]:
    """Per simulated sensor: did its injected fault change at least 6 of the audited hours by more than
    5%? A humidity fault in dry air, say, leaves the readings as a healthy sensor's: nothing to find."""
    w = sim[sim["ts"] > as_of.floor("h") - pd.Timedelta(days=days)]
    changed = (w["pm10"].isna() & w["pm10_true"].notna()) | ((w["pm10"] / w["pm10_true"] - 1).abs() > 0.05)
    return {str(k): bool(v >= 6) for k, v in changed.groupby(w["sensor_id"]).sum().items()}


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


def _date(d) -> str:
    return pd.Timestamp(d).strftime("%-d %b %Y")


def score(spec: SensorSpec, readings: pd.DataFrame, ambient: Ambient, wx: pd.DataFrame,
          as_of: pd.Timestamp, days: int = WINDOW_DAYS) -> AuditResult:
    """Eight rule checks over the `days` before `as_of`; each failure costs PENALTY points."""
    w = _window(wx, as_of, days)
    ts = pd.DatetimeIndex(w["ts"])
    station, amb = ambient.at(*spec.position, ts)
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

    # 3. Neighbour consistency: in hours when the wind brings the nearest station's air to the sensor,
    # a sensor next to a dust source can't read far below that station. Other winds may legitimately
    # bring it cleaner air, so they don't count.
    own = ambient.pm10[station.id].reindex(ts).to_numpy(dtype=float)  # measured hours only
    toward = effect.bearing(spec.position, (station.lat, station.lon))
    off_wind = np.abs((w["wind_dir"].to_numpy(dtype=float) - toward + 180) % 360 - 180)
    same = (off_wind <= SAME_WIND_DEG) & (w["wind_speed"].to_numpy(dtype=float) >= CALM) & have & ~np.isnan(own)
    med = np.nanmedian(pm[same] / np.maximum(own[same], 1.0)) if same.sum() >= MIN_SAME_WIND_H else np.nan
    km = _km(*spec.position, station.lat, station.lon)
    checks["neighbour"] = {**_check(not (med < 0.85), med, lambda: (
        f"Reads {round((1 - med) * 100)}% below {station.name} ({km:.1f} km away) in the {int(same.sum())} hours "
        "the wind brought that station's air to it.")), "station": station.name, "hours": int(same.sum())}

    # 4. Working-hours signature: a site that imagery shows active raises PM from 9 am to 6 pm. Without
    # imagery an idle site and a blind sensor look the same, so the rise is measured but not counted.
    h = _ist_hour(ts)
    day = (h >= RISE[0]) & (h < RISE[1])
    rise = np.nanmedian(excess[day & have]) - np.nanmedian(excess[night & have]) \
        if (day & have).any() and (night & have).any() else np.nan
    checks["work_signature"] = {**_check(not (spec.imagery and rise < 5), rise, lambda: (
        f"No rise in PM10 from 9 am to 6 pm, though Sentinel-2 shows the site active (scene of {_date(spec.imagery)}).")),
        "imagery": spec.imagery}

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

    # 8. Calibration date: BMC wants every sensor calibrated every 2 months. No record is not enough data;
    # a date after the audited week can't vouch for these readings, so it fails as unknown.
    cal = spec.calibrated_on
    later = cal is not None and cal > as_of
    age = (as_of - cal).days if cal is not None and not later else np.nan
    checks["calibration"] = {**_check(cal is None or (not later and as_of <= cal + CAL_DUE), age, lambda: (
        f"The calibration date on record, {_date(cal)}, is after the audited week, so it can't vouch for these readings."
        if later else f"Last calibrated on {_date(cal)}, {age} days ago; due every 2 months.")),
        "on": None if cal is None else cal.date().isoformat()}

    lost = sum(PENALTY[k] for k, c in checks.items() if not c["ok"])
    sc = float(max(0, 100 - lost))
    reasons = [c["reason"] for k, c in sorted(checks.items(), key=lambda kv: -PENALTY[kv[0]]) if not c["ok"]]
    return AuditResult(spec.sensor_id, spec.site_id, sc, band(sc), checks, reasons)


# ---------- Isolation Forest on residuals against neighbours ----------

def residuals(specs: list[SensorSpec], readings: pd.DataFrame, ambient: Ambient, wx: pd.DataFrame,
              as_of: pd.Timestamp, days: int = WINDOW_DAYS, nodes: pd.DataFrame | None = None) -> pd.DataFrame:
    """The forest's input: one row per sensor-hour with a reading, as residuals against its neighbours.

    r_station is the log ratio to the nearest station; r_peers to the median of the other site sensors,
    and of the ward's DustTrace Nodes (`nodes`: hourly PM10, one column per node), that hour, or to the
    station when there are none; r_var compares how much the sensor moved over 3 hours with how much
    the station did (a stuck sensor doesn't move). `working` says whether site dust is expected.
    """
    w = _window(wx, as_of, days)
    ts = pd.DatetimeIndex(w["ts"])
    wide = readings.pivot_table(index="ts", columns="sensor_id", values="pm10").reindex(ts)
    pool = wide if nodes is None else wide.join(nodes.reindex(ts))
    frames = []
    for s in specs:
        if s.sensor_id not in wide:
            continue
        amb = ambient.at(*s.position, ts)[1]
        peers = pool.drop(columns=[s.sensor_id]).median(axis=1).fillna(amb)
        lp = np.log(wide[s.sensor_id].clip(lower=1.0))
        la = np.log(amb.clip(lower=1.0))
        var = np.log((lp.rolling(3).std() + 0.02) / (la.rolling(3).std() + 0.02))
        frames.append(pd.DataFrame({
            "sensor_id": s.sensor_id, "ts": ts, "r_station": (lp - la).to_numpy(),
            "r_peers": (lp - np.log(peers.clip(lower=1.0))).to_numpy(), "r_var": var.to_numpy(),
            "working": _working(ts).astype(float)}).dropna())
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["sensor_id", "ts", *FOREST_FEATURES])


def _fleet(prefix: str, centre: tuple[float, float], n: int, faults: tuple[str, ...], as_of: pd.Timestamp,
           step: int, imagery: str | None = None) -> list[SensorSpec]:
    acts = list(NEAR_FIELD)
    return [SensorSpec(sensor_id=f"{prefix}-{i:03d}", site_id=prefix,
                       site_lat=centre[0] - 0.006 + 0.002 * ((i * step) % 7), site_lon=centre[1] - 0.004 + 0.002 * (i % 5),
                       area_m2=3000 + 700 * (i % 9), activity=acts[i % len(acts)], fault=faults[i % len(faults)],
                       bearing_deg=(step * 37 * i) % 360, imagery=imagery if (i // len(faults)) % 2 == 0 else None,
                       calibrated_on=simulated_calibration(f"{prefix}-{i:03d}", as_of)) for i in range(n)]


def reference(ambient: Ambient, wx: pd.DataFrame, as_of: pd.Timestamp, centre: tuple[float, float],
              n: int = 50, nodes: pd.DataFrame | None = None) -> pd.DataFrame:
    """Residuals of `n` simulated sensors with no fault, on the same ambient and weather: the forest's
    picture of normal. Their own ids and placements, so the forest never sees the sensors it scores."""
    specs = _fleet("ref", centre, n, ("none",), as_of, step=3)
    return residuals(specs, simulate(specs, ambient, wx, as_of), ambient, wx, as_of, nodes=nodes)


def outlier_share(ref: pd.DataFrame, feats: pd.DataFrame) -> tuple[dict[str, float], float]:
    """Per sensor in `feats`, the share of its hours the forest finds unusual, and the bar above which a
    sensor is flagged. The forest is fitted on half the reference sensors; the bar is the highest share
    among the other half, so no fault-free sensor it hasn't seen would be flagged. No fault labels used."""
    ids = sorted(ref["sensor_id"].unique())
    fit, held = ref[ref["sensor_id"].isin(ids[::2])], ref[ref["sensor_id"].isin(ids[1::2])]
    x = fit[FOREST_FEATURES].to_numpy(dtype=float)
    forest = IsolationForest(n_estimators=200, random_state=0).fit(x)
    cut = np.quantile(forest.score_samples(x), FOREST_HOUR_Q)

    def share(f: pd.DataFrame) -> dict[str, float]:
        if f.empty:
            return {}
        out = pd.Series(forest.score_samples(f[FOREST_FEATURES].to_numpy(dtype=float)) < cut)
        return {str(k): round(float(v), 4) for k, v in out.groupby(f["sensor_id"].to_numpy()).mean().items()}

    return share(feats), max(share(held).values())


def _rates(specs: list[SensorSpec], flagged: dict[str, bool]) -> dict:
    tp = sum(flagged[s.sensor_id] and s.fault != "none" for s in specs)
    fp = sum(flagged[s.sensor_id] and s.fault == "none" for s in specs)
    fn = sum(not flagged[s.sensor_id] and s.fault != "none" for s in specs)
    by_fault: dict[str, list[bool]] = {}
    for s in specs:
        by_fault.setdefault(s.fault, []).append(flagged[s.sensor_id])
    return {"precision": round(tp / (tp + fp), 3) if tp + fp else 1.0,
            "recall": round(tp / (tp + fn), 3) if tp + fn else 1.0,
            "detected": {f: round(sum(v) / len(v), 2) for f, v in by_fault.items()}}


def benchmark(ambient: Ambient, wx: pd.DataFrame, as_of: pd.Timestamp, centre: tuple[float, float], n: int = 50,
              nodes: pd.DataFrame | None = None) -> dict:
    """Simulate `n` sensors around `centre` with faults injected in rotation and measure how well the
    rules, the forest, and either of them find the faults. Every simulated site works; half of them, a
    whole fault rotation at a time, count as active in imagery, so the working-hours check is scored
    both ways."""
    specs = _fleet("bench", centre, n, FAULTS, as_of, step=1, imagery=str(as_of.date()))
    sim = simulate(specs, ambient, wx, as_of)
    rules = {s.sensor_id: any(not c["ok"] for c in score(s, sim, ambient, wx, as_of).checks.values()) for s in specs}
    share, bar = outlier_share(reference(ambient, wx, as_of, centre, nodes=nodes),
                               residuals(specs, sim, ambient, wx, as_of, nodes=nodes))
    forest = {s.sensor_id: share.get(s.sensor_id, 0.0) > bar for s in specs}
    methods = {"rules": _rates(specs, rules), "forest": _rates(specs, forest),
               "both": _rates(specs, {k: rules[k] or forest[k] for k in rules})}
    sensors = pd.Series([s.fault for s in specs]).value_counts().to_dict()
    shown = fault_shown(sim, as_of)
    week = pd.date_range(end=as_of.floor("h"), periods=24 * WINDOW_DAYS, freq="h")
    used = Counter(ambient.nearest(*s.position) for s in specs)
    stations = {st.id: {"name": st.name, "sensors": k, **ambient.sources(st, week)} for st, k in used.items()}
    return {"n": n, **methods["rules"], "methods": methods, "sensors": {f: int(sensors.get(f, 0)) for f in FAULTS},
            "shown": {f: sum(shown[s.sensor_id] for s in specs if s.fault == f) for f in FAULTS if f != "none"},
            "imagery_active": sum(s.imagery is not None for s in specs), "stations": dict(sorted(stations.items())),
            "forest_bar": bar}


def hot_hours(readings: pd.DataFrame, specs: list[SensorSpec], ambient: Ambient, as_of: pd.Timestamp) -> dict[str, int]:
    """Per sensor: the latest working hours in a row, up to `as_of`, reading above twice its station (D4)."""
    out = {}
    pos = {s.sensor_id: s.position for s in specs}
    for sid, g in readings[readings["ts"] <= as_of].sort_values("ts").groupby("sensor_id"):
        ts = pd.DatetimeIndex(g["ts"])
        amb = ambient.at(*pos[sid], ts)[1].to_numpy(dtype=float)
        hot = (g["pm10"].to_numpy(dtype=float) > 2 * amb) & _working(ts)
        n = 0
        for h in hot[::-1]:
            if not h:
                break
            n += 1
        out[str(sid)] = n
    return out
