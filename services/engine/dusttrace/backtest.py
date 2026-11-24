"""Back-test (PRD F3 evidence): replay past days with only the data up to each forecast origin visible.

The model is trained on readings before `start` only. For each origin from `start`, it forecasts the
next `horizon` hours from readings up to that origin, and the forecast is scored against what the
stations then measured, alongside persistence (the value at the origin carried forward).

The daily calls, P(24 h mean PM10 > 100) for days 1-3 after each origin, are scored against the 24 h means
the stations measured (18 of 24 hours or the day is skipped), for the ward and for each station, alongside
persistence: the 24 h mean measured up to the origin, carried forward.

One honest caveat: the weather at the target hour is the observed weather (Open-Meteo archive), so
this treats the weather forecast as perfect. Live forecasts will do somewhat worse.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from . import fill, forecast

BUCKETS = {"1-24": (1, 24), "25-48": (25, 48), "49-72": (49, 72)}
IST = pd.Timedelta(hours=5.5)


@dataclass
class Result:
    train_end: pd.Timestamp
    test_end: pd.Timestamp
    origins: int
    stations: list[str]
    metrics: dict
    spike_day: dict | None
    daily: dict = None
    note: str = "Weather at the target hour is observed weather, i.e. a perfect weather forecast."


def metrics(rows: pd.DataFrame, threshold: float) -> dict:
    """`rows`: h, pred, lo, hi, p, actual, persist (ward level)."""
    out = {}
    for name, (a, b) in BUCKETS.items():
        r = rows[(rows["h"] >= a) & (rows["h"] <= b)]
        if r.empty:
            continue
        ex = r["actual"] > threshold
        out[name] = {
            "n": int(len(r)),
            "mae_model": round(float((r["pred"] - r["actual"]).abs().mean()), 2),
            "mae_persistence": round(float((r["persist"] - r["actual"]).abs().mean()), 2),
            "f1_exceed_model": _f1(ex, r["p"] >= 0.5),
            "f1_exceed_persistence": _f1(ex, r["persist"] > threshold),
            "coverage_10_90": round(float(((r["actual"] >= r["lo"]) & (r["actual"] <= r["hi"])).mean()), 3),
            "exceed_rate": round(float(ex.mean()), 3),
        }
    return out


def _f1(truth, call) -> float | None:
    """F1, or None when nothing was measured above the threshold and nothing was called."""
    truth, call = np.asarray(truth, dtype=bool), np.asarray(call, dtype=bool)
    if not truth.any() and not call.any():
        return None
    return round(float(f1_score(truth, call, zero_division=0)), 3)


def daily_metrics(rows: pd.DataFrame, threshold: float) -> dict:
    """`rows`: level ('ward' or 'stations'), station_id, day, end (the day's last hour), p, actual and persist
    (24 h means). `window` counts each measured 24 h once, though days 1-3 of successive forecasts score it
    up to three times."""
    out = {}
    for level, g in rows.groupby("level"):
        out[level] = {}
        for day, r in g.groupby("day"):
            ex, call = (r["actual"] > threshold).to_numpy(), (r["p"] >= 0.5).to_numpy()
            out[level][str(day)] = {
                "n": int(len(r)),
                "exceed_days": int(ex.sum()),
                "hits": int((ex & call).sum()),
                "misses": int((ex & ~call).sum()),
                "false_alarms": int((~ex & call).sum()),
                "f1_model": _f1(ex, call),
                "f1_persistence": _f1(ex, r["persist"] > threshold),
                "brier": round(float(((r["p"] - ex) ** 2).mean()), 4),
            }
    seen = rows.drop_duplicates(["station_id", "end"])
    w, s = seen[seen["level"] == "ward"], seen[seen["level"] == "stations"]
    out["window"] = {"ward_days": int(len(w)), "ward_exceed_days": int((w["actual"] > threshold).sum()),
                     "station_days": int(len(s)), "station_exceed_days": int((s["actual"] > threshold).sum())}
    return out


def change(base_hourly: dict, base_daily: dict, hourly: dict, daily: dict) -> dict:
    """What adding an input did to the back-test, and whether it stays on: only if the hourly MAE does not
    rise and neither the hourly nor the daily exceedance F1 falls (each the mean over its horizons). The
    decision uses the unrounded means; a blank F1 (nothing to catch, nothing called) counts as perfect, so
    false alarms in a quiet window count against the input."""
    def summary(h, d):
        mean = lambda xs: float(np.mean(xs)) if xs else 0.0
        f1 = lambda v: 1.0 if v is None else v
        return (mean([h[k]["mae_model"] for k in BUCKETS if k in h]),
                mean([f1(h[k]["f1_exceed_model"]) for k in BUCKETS if k in h]),
                mean([f1(v["f1_model"]) for v in d.get("stations", {}).values()]))
    (m0, h0, d0), (m1, h1, d1) = summary(base_hourly, base_daily), summary(hourly, daily)
    tol = 1e-9  # float noise only
    return {"mae": round(m1 - m0, 4), "f1_hourly": round(h1 - h0, 4), "f1_daily": round(d1 - d0, 4),
            "on": m1 - m0 <= tol and h1 - h0 >= -tol and d1 - d0 >= -tol}


def _ward_actual(readings: pd.DataFrame) -> pd.Series:
    return readings.dropna(subset=["pm10"]).groupby("ts")["pm10"].mean()


def _means_24(series: pd.Series) -> pd.Series:
    """At each hour e, the mean of hours e-23 .. e when at least 18 were measured."""
    idx = pd.date_range(series.index.min(), series.index.max(), freq="h", tz="UTC")
    return series.reindex(idx).rolling(24, min_periods=forecast.MIN_HOURS).mean()


def run(readings: pd.DataFrame, wx: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
        horizon: int = 72, step_h: int = 24, threshold: float = 100.0, cams: pd.DataFrame | None = None,
        festival: bool = False, upwind: dict | None = None) -> Result:
    readings = readings.copy()
    readings["ts"] = pd.to_datetime(readings["ts"], utc=True)
    model = forecast.train(readings[readings["ts"] < start], wx, horizon, threshold, cams=cams, festival=festival,
                           upwind=upwind)
    actual = _ward_actual(readings)
    means = {sid: _means_24(g.set_index("ts")["pm10"].dropna()) for sid, g in readings.groupby("station_id")}
    means["ward"] = _means_24(actual)
    origins = pd.date_range(start, end - pd.Timedelta(hours=horizon), freq=f"{step_h}h", tz="UTC")
    rows, drows, issued = [], [], {}
    for t0 in origins:
        seen = readings[readings["ts"] <= t0]
        fc = forecast.predict(model, seen, wx, t0, horizon, cams=cams)
        ward = fc[fc["station_id"] == "ward"].set_index("ts")
        if ward.empty or t0 not in actual.index:
            continue
        issued[t0] = ward
        for ts, w in ward.iterrows():
            if ts in actual.index:
                rows.append({"t0": t0, "ts": ts, "h": int((ts - t0) / pd.Timedelta(hours=1)), "pred": w["pm10"],
                             "lo": w["pm10_lo"], "hi": w["pm10_hi"], "p": w["p_exceed"],
                             "actual": actual[ts], "persist": actual[t0]})
        for d in forecast.predict_daily(model, seen, wx, t0, cams=cams).itertuples():
            m = means[d.station_id]
            drows.append({"level": "ward" if d.station_id == "ward" else "stations", "station_id": d.station_id,
                          "day": d.day, "end": d.ends_at, "p": d.p_exceed,
                          "actual": m.get(d.ends_at, np.nan), "persist": m.get(t0, np.nan)})
    df = pd.DataFrame(rows)
    ddf = pd.DataFrame(drows).dropna(subset=["actual", "persist"]) if drows else pd.DataFrame()
    return Result(start, end, len(issued), sorted(model.station_codes), metrics(df, threshold) if len(df) else {},
                  _spike_day(actual, issued, start, end, horizon), daily_metrics(ddf, threshold) if len(ddf) else {})


def _spike_day(actual: pd.Series, issued: dict, start, end, horizon) -> dict | None:
    """The worst IST day in the test window, and what the forecast issued about 48 h earlier said."""
    a = actual[(actual.index >= start) & (actual.index < end)]
    if a.empty or not issued:
        return None
    by_day = a.groupby((a.index + IST).date).mean()
    day = by_day.idxmax()
    day_start = pd.Timestamp(day).tz_localize("UTC") - IST
    candidates = [t0 for t0 in issued if t0 <= day_start - pd.Timedelta(hours=24)]
    if not candidates:
        return {"day": str(day), "actual_mean": round(float(by_day.max()), 1), "issued_at": None}
    t0 = max(candidates)
    w = issued[t0]
    hours = w[(w.index >= day_start) & (w.index < day_start + pd.Timedelta(hours=24))]
    if hours.empty:
        return {"day": str(day), "actual_mean": round(float(by_day.max()), 1), "issued_at": t0.isoformat()}
    return {
        "day": str(day),
        "actual_mean": round(float(by_day.max()), 1),
        "issued_at": t0.isoformat(),
        "lead_hours": int((day_start - t0) / pd.Timedelta(hours=1)),
        "forecast_mean": round(float(hours["pm10"].mean()), 1),
        "p_exceed_max": round(float(hours["p_exceed"].max()), 3),
        "flagged": bool(hours["p_exceed"].max() >= 0.5),
    }


def outage_replay(readings: pd.DataFrame, cams_df: pd.DataFrame, wx: pd.DataFrame, start: pd.Timestamp,
                  end: pd.Timestamp, outage_h: int = 96, horizon: int = 48, step_h: int = 24,
                  threshold: float = 100.0) -> dict:
    """Verify the CAMS fill (issue #28) on real history.

    At each origin, hide the last `outage_h` hours of every station, fill them with CAMS corrected on
    the data before the outage, forecast, and score against what the stations then measured. Compared
    with: the forecast from the real data (no outage), corrected CAMS used directly, and the last real
    value carried forward.
    """
    readings = readings.copy()
    readings["ts"] = pd.to_datetime(readings["ts"], utc=True)
    cams_df = cams_df.copy()
    cams_df["ts"] = pd.to_datetime(cams_df["ts"], utc=True)
    model = forecast.train(readings[readings["ts"] < start], wx, horizon, threshold)
    actual = _ward_actual(readings)
    rows = {k: [] for k in ("real", "filled", "cams_direct", "last_value")}
    origins = pd.date_range(start, end - pd.Timedelta(hours=horizon), freq=f"{step_h}h", tz="UTC")
    used = 0
    for t0 in origins:
        cut = t0 - pd.Timedelta(hours=outage_h)
        seen = readings[readings["ts"] <= cut]
        fills, direct = [], []
        for sid, obs in seen.groupby("station_id"):
            cm = cams_df[cams_df["station_id"] == sid].set_index("ts")["pm10"]
            k = fill.fit(obs.set_index("ts")["pm10"], cm)
            if k.method == "none":
                continue
            g = fill.gap(obs.set_index("ts")["pm10"], cm, k, t0)
            fills.append(pd.DataFrame({"station_id": sid, "ts": g.index, "pm10": g.to_numpy()}))
            fut = fill.apply(cm[(cm.index > t0) & (cm.index <= t0 + pd.Timedelta(hours=horizon))], k)
            direct.append(fut.rename(sid))
        if not fills or t0 not in actual.index:
            continue
        used += 1
        filled = pd.concat([seen[["station_id", "ts", "pm10"]]] + fills, ignore_index=True)
        f_real = forecast.predict(model, readings[readings["ts"] <= t0], wx, t0, horizon)
        f_fill = forecast.predict(model, filled, wx, t0, horizon)
        cams_ward = pd.concat(direct, axis=1, sort=True).mean(axis=1)
        last_seen = _ward_actual(seen)
        last_value = float(last_seen.iloc[-1]) if len(last_seen) else np.nan
        for name, fc in (("real", f_real), ("filled", f_fill)):
            w = fc[fc["station_id"] == "ward"].set_index("ts")
            for ts, r in w.iterrows():
                if ts in actual.index:
                    rows[name].append({"h": int((ts - t0) / pd.Timedelta(hours=1)), "pred": r["pm10"], "lo": r["pm10_lo"],
                                       "hi": r["pm10_hi"], "p": r["p_exceed"], "actual": actual[ts], "persist": actual[t0]})
        for ts, v in cams_ward.items():
            if ts in actual.index:
                h = int((ts - t0) / pd.Timedelta(hours=1))
                rows["cams_direct"].append({"h": h, "pred": v, "lo": v, "hi": v, "p": float(v > threshold),
                                            "actual": actual[ts], "persist": actual[t0]})
                rows["last_value"].append({"h": h, "pred": last_value, "lo": last_value, "hi": last_value,
                                           "p": float(last_value > threshold), "actual": actual[ts], "persist": actual[t0]})
    out = {k: metrics(pd.DataFrame(v), threshold) if v else {} for k, v in rows.items()}
    return {"metrics": out, "origins": used, "outage_hours": outage_h, "stations": sorted(model.station_codes),
            "train_end": start, "test_end": end}
