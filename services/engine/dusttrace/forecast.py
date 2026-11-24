"""72-hour PM10 forecast per station, plus a ward aggregate (PRD F3).

Direct multi-horizon LightGBM: each training row is (origin t0, horizon h) with features known at t0
(recent PM10 lags) and weather at the target hour t0+h (from the weather forecast in production).
We fit a median model, 10th/90th percentile models for the range, and a classifier for P(PM10 > 100).

The PRD's own quantity, P(24 h mean PM10 > 100) for days 1-3 after t0 (hours 1-24, 25-48, 49-72), comes from
a second classifier trained on daily rows: features known at t0, weather averaged over the day's 24 h, and
as target the mean PM10 those 24 h measured. The ward is one more series there: its stations' hourly mean.

Evaluation is a time-ordered holdout against two baselines from the PRD:
- persistence: PM10 at t0+h equals PM10 at t0
- for exceedance F1: "exceeds at t0+h" predicted as "exceeds at t0"
"""

from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, mean_absolute_error

from . import festivals

LAGS = [1, 2, 3, 6, 12, 24]
WX_COLS = ["wind_speed", "wind_dir_sin", "wind_dir_cos", "blh", "temp", "rh", "precip", "ventilation"]
FEATURES = (
    [f"lag_{l}" for l in LAGS]
    + ["mean_24", "max_24", "h", "hour_ist", "dow", "month", "station_code"]
    + WX_COLS
)
CAMS_FEATURES = ["cams_t", "cams_mean_24"]  # Copernicus CAMS PM10 at the station: target hour, and the 24 h before it
FESTIVAL_FEATURES = ["festival"]  # festivals.flag at the target hour; on a daily row, the day's share of festival hours
UPWIND_FEATURES = ["upwind_sites_ha"]  # mapped construction upwind of the station at the target hour (upwind_site_area)
DAYS = 3
DAILY_FEATURES = (
    [f"lag_{l}" for l in LAGS]
    + ["mean_24", "max_24", "day", "hour_ist", "dow", "month", "station_code"]
    + [f"{c}_24" for c in WX_COLS]  # weather averaged over the day's 24 h
)
DAILY_OPTIONAL = ["cams_mean_24", "festival", "upwind_sites_ha"]  # averaged over the day's 24 h when the model has them
MIN_HOURS = 18  # a 24 h mean needs 18 of its 24 hours measured
THIN_AFTER_H = 48  # training rows past this horizon come from every second origin, so 72 h costs about 1.25x 48 h
UPWIND_RADIUS_M = 3000
UPWIND_HALF_WIDTH = 30  # degrees either side of the direction the wind blows from
IST = 5.5


def _prep_weather(wx: pd.DataFrame) -> pd.DataFrame:
    w = wx.copy()
    w["ts"] = pd.to_datetime(w["ts"], utc=True)
    rad = np.radians(w["wind_dir"].astype(float))
    w["wind_dir_sin"] = np.sin(rad)
    w["wind_dir_cos"] = np.cos(rad)
    w["ventilation"] = w["wind_speed"].astype(float) * w["blh"].astype(float)
    return w.set_index("ts").sort_index()


def _station_frame(readings: pd.DataFrame, sid: str, idx: pd.DatetimeIndex) -> pd.Series:
    s = readings.loc[readings["station_id"] == sid].set_index("ts")["pm10"].sort_index()
    s = s[~s.index.duplicated()]
    return s.reindex(idx)


def upwind_site_area(stations: pd.DataFrame, sites: pd.DataFrame, radius_m: float = UPWIND_RADIUS_M,
                     half_width: float = UPWIND_HALF_WIDTH) -> dict[str, np.ndarray]:
    """Per station (id, lat, lon): for each wind direction 0-359 (where the wind blows from), the hectares of
    the given sites (lat, lon, area_m2) within `radius_m` and `half_width` degrees of that direction."""
    out = {}
    lat, lon, ha = (sites[c].astype(float).to_numpy() for c in ("lat", "lon", "area_m2"))
    for st in stations.itertuples():
        dy = (lat - float(st.lat)) * 111_320
        dx = (lon - float(st.lon)) * 111_320 * np.cos(np.radians(float(st.lat)))
        near = np.hypot(dx, dy) <= radius_m
        bearing = np.degrees(np.arctan2(dx[near], dy[near])) % 360
        off = np.abs((np.arange(360)[:, None] - bearing[None, :] + 180) % 360 - 180)
        out[st.id] = ((off <= half_width) * ha[near][None, :]).sum(axis=1) / 10_000
    return out


def _upwind_hourly(table: np.ndarray, wind_dir: pd.Series) -> pd.Series:
    d = wind_dir.to_numpy(dtype=float)
    out = np.full(len(d), np.nan)
    ok = ~np.isnan(d)
    out[ok] = table[np.rint(d[ok]).astype(int) % 360]
    return pd.Series(out, index=wind_dir.index)


def _origin_features(pm: pd.Series, t0s: pd.DatetimeIndex) -> pd.DataFrame:
    base = pd.DataFrame({f"lag_{l}": pm.shift(l - 1).reindex(t0s).to_numpy() for l in LAGS}, index=t0s)  # lag_1 == t0
    base["mean_24"] = pm.rolling(24, min_periods=12).mean().reindex(t0s).to_numpy()
    base["max_24"] = pm.rolling(24, min_periods=12).max().reindex(t0s).to_numpy()
    return base


def build_rows(readings: pd.DataFrame, wx: pd.DataFrame, origins: pd.DatetimeIndex | None,
               horizon: int, station_codes: dict[str, int], with_target: bool = True,
               origin_stride: int = 3, cams: pd.DataFrame | None = None, festival: bool = False,
               upwind: dict[str, np.ndarray] | None = None) -> pd.DataFrame:
    w = _prep_weather(wx)
    idx = pd.date_range(w.index.min(), w.index.max(), freq="h", tz="UTC")
    fest = pd.Series(festivals.flag(idx), index=idx) if festival else None
    rows = []
    for sid, code in station_codes.items():
        pm = _station_frame(readings, sid, idx)
        if cams is not None:
            cm = _station_frame(cams, sid, idx)
            cm24 = cm.rolling(24, min_periods=12).mean()
        if upwind is not None:
            up = _upwind_hourly(upwind[sid], w["wind_dir"].reindex(idx))
        t0s = origins if origins is not None else idx[24:-1:origin_stride]
        base = _origin_features(pm, t0s)
        for h in range(1, horizon + 1):
            thin = origins is None and h > THIN_AFTER_H
            at = t0s[::2] if thin else t0s
            tgt = at + pd.Timedelta(hours=h)
            df = base.iloc[::2].copy() if thin else base.copy()
            df["h"] = h
            df["t0"] = at
            df["ts"] = tgt
            df["station_id"] = sid
            df["station_code"] = code
            wtar = w.reindex(tgt)
            for c in WX_COLS:
                df[c] = wtar[c].to_numpy()
            hrs = tgt.hour + tgt.minute / 60
            df["hour_ist"] = ((hrs + IST) % 24).to_numpy()
            df["dow"] = tgt.dayofweek.to_numpy()
            df["month"] = tgt.month.to_numpy()
            if cams is not None:
                df["cams_t"] = cm.reindex(tgt).to_numpy()
                df["cams_mean_24"] = cm24.reindex(tgt).to_numpy()
            if fest is not None:
                df["festival"] = fest.reindex(tgt).to_numpy()
            if upwind is not None:
                df["upwind_sites_ha"] = up.reindex(tgt).to_numpy()
            if with_target:
                df["y"] = pm.reindex(tgt).to_numpy()
            rows.append(df)
    out = pd.concat(rows, ignore_index=True)
    out = out[out["lag_1"].notna()]
    if with_target:
        out = out[out["y"].notna()]
    return out


def daily_rows(readings: pd.DataFrame, wx: pd.DataFrame, origins: pd.DatetimeIndex | None,
               station_codes: dict[str, int], with_target: bool = True, origin_stride: int = 3,
               cams: pd.DataFrame | None = None, festival: bool = False,
               upwind: dict[str, np.ndarray] | None = None) -> pd.DataFrame:
    """One row per series, origin t0 and day d (1-3): features known at t0, weather (and CAMS, festival,
    upwind sites) averaged over hours 24(d-1)+1 .. 24d after t0, and as target `y` the mean PM10 measured in
    those hours (MIN_HOURS of 24 or no target). The series are the stations and 'ward', their hourly mean."""
    w = _prep_weather(wx)
    last = w.index.max() if origins is None else max(w.index.max(), origins.max() + pd.Timedelta(hours=24 * DAYS))
    idx = pd.date_range(w.index.min(), last, freq="h", tz="UTC")  # past the weather, so a day it mostly covers counts
    wx24 = w[WX_COLS].reindex(idx).rolling(24, min_periods=MIN_HOURS).mean()  # at hour e: hours e-23 .. e
    fest24 = pd.Series(festivals.flag(idx), index=idx).rolling(24).mean() if festival else None
    pm = {sid: _station_frame(readings, sid, idx) for sid in station_codes}
    pm["ward"] = pd.concat(pm.values(), axis=1).mean(axis=1)
    codes = {**station_codes, "ward": len(station_codes)}
    if cams is not None:
        cm = {sid: _station_frame(cams, sid, idx) for sid in station_codes}
        cm["ward"] = pd.concat(cm.values(), axis=1).mean(axis=1)
    if upwind is not None:
        upwind = {**upwind, "ward": np.mean([upwind[sid] for sid in station_codes], axis=0)}
    t0s = origins if origins is not None else idx[24:-1:origin_stride]
    hour_ist = ((t0s.hour + t0s.minute / 60 + IST) % 24).to_numpy()
    rows = []
    for sid, code in codes.items():
        base = _origin_features(pm[sid], t0s)
        target = pm[sid].rolling(24, min_periods=MIN_HOURS).mean()
        if cams is not None:
            cm24 = cm[sid].rolling(24, min_periods=12).mean()
        if upwind is not None:
            up24 = _upwind_hourly(upwind[sid], w["wind_dir"].reindex(idx)).rolling(24, min_periods=12).mean()
        for d in range(1, DAYS + 1):
            end = t0s + pd.Timedelta(hours=24 * d)
            mid = end + pd.Timedelta(hours=IST - 12)  # IST, halfway through the day
            df = base.copy()
            df["day"] = d
            df["t0"] = t0s
            df["starts_at"] = end - pd.Timedelta(hours=23)
            df["ends_at"] = end
            df["station_id"] = sid
            df["station_code"] = code
            df["hour_ist"] = hour_ist
            df["dow"] = mid.dayofweek.to_numpy()
            df["month"] = mid.month.to_numpy()
            for c in WX_COLS:
                df[f"{c}_24"] = wx24[c].reindex(end).to_numpy()
            if cams is not None:
                df["cams_mean_24"] = cm24.reindex(end).to_numpy()
            if fest24 is not None:
                df["festival"] = fest24.reindex(end).to_numpy()
            if upwind is not None:
                df["upwind_sites_ha"] = up24.reindex(end).to_numpy()
            if with_target:
                df["y"] = target.reindex(end).to_numpy()
            rows.append(df)
    out = pd.concat(rows, ignore_index=True)
    out = out[out["lag_1"].notna()]
    if with_target:
        out = out[out["y"].notna()]
    return out


@dataclass
class Model:
    median: lgb.LGBMRegressor
    lo: lgb.LGBMRegressor
    hi: lgb.LGBMRegressor
    exceed: lgb.LGBMClassifier
    station_codes: dict[str, int]
    threshold: float
    metrics: dict
    features: list = None  # FEATURES, plus CAMS_FEATURES, FESTIVAL_FEATURES, UPWIND_FEATURES when trained with them
    daily: lgb.LGBMClassifier = None  # P(24 h mean PM10 > threshold) for days 1-3
    daily_features: list = None
    upwind: dict = None  # the upwind_site_area tables it was trained with

    def __post_init__(self):
        if self.features is None:
            self.features = list(FEATURES)


def _reg(alpha: float | None) -> lgb.LGBMRegressor:
    kw = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=40,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.9, verbose=-1)
    if alpha is None:
        return lgb.LGBMRegressor(objective="l1", **kw)
    return lgb.LGBMRegressor(objective="quantile", alpha=alpha, **kw)


def _clf() -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=40, verbose=-1)


def train(readings: pd.DataFrame, wx: pd.DataFrame, horizon: int = 72, threshold: float = 100.0,
          holdout_frac: float = 0.2, cams: pd.DataFrame | None = None, festival: bool = False,
          upwind: dict[str, np.ndarray] | None = None) -> Model:
    codes = {sid: i for i, sid in enumerate(sorted(readings["station_id"].unique()))}
    data = build_rows(readings, wx, None, horizon, codes, cams=cams, festival=festival, upwind=upwind)
    feats = (list(FEATURES) + (CAMS_FEATURES if cams is not None else []) + (FESTIVAL_FEATURES if festival else [])
             + (UPWIND_FEATURES if upwind is not None else []))
    if len(data) < 500:
        raise ValueError(f"Not enough history to train ({len(data)} rows)")
    cut = data["t0"].quantile(1 - holdout_frac)
    tr, te = data[data["t0"] <= cut], data[data["t0"] > cut]

    def fit_all(df):
        X, y = df[feats], df["y"]
        m = _reg(None).fit(X, y)
        lo = _reg(0.1).fit(X, y)
        hi = _reg(0.9).fit(X, y)
        clf = _clf().fit(X, (y > threshold).astype(int))
        return m, lo, hi, clf

    m, lo, hi, clf = fit_all(tr)
    pred = m.predict(te[feats])
    p = clf.predict_proba(te[feats])[:, 1]
    y_true = te["y"].to_numpy()
    persist = te["lag_1"].to_numpy()
    ex_true = y_true > threshold
    metrics = {
        "holdout_rows": int(len(te)),
        "mae_model": round(float(mean_absolute_error(y_true, pred)), 2),
        "mae_persistence": round(float(mean_absolute_error(y_true, persist)), 2),
        "f1_exceed_model": round(float(f1_score(ex_true, p >= 0.5, zero_division=0)), 3),
        "f1_exceed_persistence": round(float(f1_score(ex_true, persist > threshold, zero_division=0)), 3),
        "coverage_10_90": round(float(np.mean((y_true >= lo.predict(te[feats])) & (y_true <= hi.predict(te[feats])))), 3),
        "exceed_rate": round(float(ex_true.mean()), 3),
        "train_rows": int(len(tr)),
    }
    # Refit on everything for the production forecast.
    m, lo, hi, clf = fit_all(data)
    days = daily_rows(readings, wx, None, codes, cams=cams, festival=festival, upwind=upwind)
    dfeats = DAILY_FEATURES + [c for c in DAILY_OPTIONAL if c in feats]
    daily = _clf().fit(days[dfeats], (days["y"] > threshold).astype(int))
    metrics["daily_rows"] = int(len(days))
    metrics["daily_exceed_rate"] = round(float((days["y"] > threshold).mean()), 3)
    return Model(m, lo, hi, clf, codes, threshold, metrics, feats, daily, dfeats, upwind)


def predict(model: Model, readings: pd.DataFrame, wx: pd.DataFrame, t0: pd.Timestamp,
            horizon: int = 72, cams: pd.DataFrame | None = None) -> pd.DataFrame:
    """Station rows plus a 'ward' aggregate (mean of stations; p_exceed from the mean forecast's spread)."""
    origins = pd.DatetimeIndex([t0])
    use_cams = cams if set(CAMS_FEATURES) <= set(model.features) else None
    rows = build_rows(readings, wx, origins, horizon, model.station_codes, with_target=False, cams=use_cams,
                      festival="festival" in model.features,
                      upwind=model.upwind if "upwind_sites_ha" in model.features else None)
    rows = rows[rows[WX_COLS].notna().any(axis=1)].copy()  # no weather forecast for the hour: no PM10 forecast either
    if rows.empty:
        return pd.DataFrame(columns=["station_id", "ts", "pm10", "pm10_lo", "pm10_hi", "p_exceed"])
    X = rows[model.features]
    rows["pm10"] = np.clip(model.median.predict(X), 0, None)
    lo = model.lo.predict(X)
    hi = model.hi.predict(X)
    rows["pm10_lo"] = np.clip(np.minimum(lo, rows["pm10"]), 0, None)
    rows["pm10_hi"] = np.maximum(hi, rows["pm10"])
    rows["p_exceed"] = model.exceed.predict_proba(X)[:, 1]
    st = rows[["station_id", "ts", "pm10", "pm10_lo", "pm10_hi", "p_exceed"]]
    ward = st.groupby("ts", as_index=False).agg(
        pm10=("pm10", "mean"), pm10_lo=("pm10_lo", "mean"), pm10_hi=("pm10_hi", "mean"),
        p_exceed=("p_exceed", "mean"))
    ward["station_id"] = "ward"
    return pd.concat([st, ward[st.columns]], ignore_index=True)


def predict_daily(model: Model, readings: pd.DataFrame, wx: pd.DataFrame, t0: pd.Timestamp,
                  cams: pd.DataFrame | None = None) -> pd.DataFrame:
    """P(24 h mean PM10 > threshold) for days 1-3 after t0, per station and for the ward:
    station_id, day, starts_at and ends_at (first and last forecast hour of the day), p_exceed."""
    rows = daily_rows(readings, wx, pd.DatetimeIndex([t0]), model.station_codes, with_target=False,
                      cams=cams if "cams_mean_24" in model.daily_features else None,
                      festival="festival" in model.daily_features,
                      upwind=model.upwind if "upwind_sites_ha" in model.daily_features else None)
    rows = rows[rows[[f"{c}_24" for c in WX_COLS]].notna().any(axis=1)].copy()  # needs 18 h of weather forecast
    rows["p_exceed"] = model.daily.predict_proba(rows[model.daily_features])[:, 1]
    return rows[["station_id", "day", "starts_at", "ends_at", "p_exceed"]].reset_index(drop=True)
