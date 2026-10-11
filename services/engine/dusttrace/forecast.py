"""48-hour PM10 forecast per station, plus a ward aggregate.

Direct multi-horizon LightGBM: each training row is (origin t0, horizon h) with features known at t0
(recent PM10 lags) and weather at the target hour t0+h (from the weather forecast in production).
We fit a median model, 10th/90th percentile models for the range, and a classifier for P(PM10 > 100).

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

LAGS = [1, 2, 3, 6, 12, 24]
WX_COLS = ["wind_speed", "wind_dir_sin", "wind_dir_cos", "blh", "temp", "rh", "precip", "ventilation"]
FEATURES = (
    [f"lag_{l}" for l in LAGS]
    + ["mean_24", "max_24", "h", "hour_ist", "dow", "month", "station_code"]
    + WX_COLS
)
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


def build_rows(readings: pd.DataFrame, wx: pd.DataFrame, origins: pd.DatetimeIndex | None,
               horizon: int, station_codes: dict[str, int], with_target: bool = True,
               origin_stride: int = 3) -> pd.DataFrame:
    w = _prep_weather(wx)
    idx = pd.date_range(w.index.min(), w.index.max(), freq="h", tz="UTC")
    rows = []
    for sid, code in station_codes.items():
        pm = _station_frame(readings, sid, idx)
        lagged = {f"lag_{l}": pm.shift(l - 1) for l in LAGS}  # lag_1 == value at t0
        mean24 = pm.rolling(24, min_periods=12).mean()
        max24 = pm.rolling(24, min_periods=12).max()
        t0s = origins if origins is not None else idx[24:-1:origin_stride]
        base = pd.DataFrame({k: v.reindex(t0s).to_numpy() for k, v in lagged.items()}, index=t0s)
        base["mean_24"] = mean24.reindex(t0s).to_numpy()
        base["max_24"] = max24.reindex(t0s).to_numpy()
        for h in range(1, horizon + 1):
            tgt = t0s + pd.Timedelta(hours=h)
            df = base.copy()
            df["h"] = h
            df["t0"] = t0s
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
            if with_target:
                df["y"] = pm.reindex(tgt).to_numpy()
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


def _reg(alpha: float | None) -> lgb.LGBMRegressor:
    kw = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=40,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.9, verbose=-1)
    if alpha is None:
        return lgb.LGBMRegressor(objective="l1", **kw)
    return lgb.LGBMRegressor(objective="quantile", alpha=alpha, **kw)


def train(readings: pd.DataFrame, wx: pd.DataFrame, horizon: int = 48, threshold: float = 100.0,
          holdout_frac: float = 0.2) -> Model:
    codes = {sid: i for i, sid in enumerate(sorted(readings["station_id"].unique()))}
    data = build_rows(readings, wx, None, horizon, codes)
    if len(data) < 500:
        raise ValueError(f"Not enough history to train ({len(data)} rows)")
    cut = data["t0"].quantile(1 - holdout_frac)
    tr, te = data[data["t0"] <= cut], data[data["t0"] > cut]

    def fit_all(df):
        X, y = df[FEATURES], df["y"]
        m = _reg(None).fit(X, y)
        lo = _reg(0.1).fit(X, y)
        hi = _reg(0.9).fit(X, y)
        clf = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                                 min_child_samples=40, verbose=-1).fit(X, (y > threshold).astype(int))
        return m, lo, hi, clf

    m, lo, hi, clf = fit_all(tr)
    pred = m.predict(te[FEATURES])
    p = clf.predict_proba(te[FEATURES])[:, 1]
    y_true = te["y"].to_numpy()
    persist = te["lag_1"].to_numpy()
    ex_true = y_true > threshold
    metrics = {
        "holdout_rows": int(len(te)),
        "mae_model": round(float(mean_absolute_error(y_true, pred)), 2),
        "mae_persistence": round(float(mean_absolute_error(y_true, persist)), 2),
        "f1_exceed_model": round(float(f1_score(ex_true, p >= 0.5, zero_division=0)), 3),
        "f1_exceed_persistence": round(float(f1_score(ex_true, persist > threshold, zero_division=0)), 3),
        "coverage_10_90": round(float(np.mean((y_true >= lo.predict(te[FEATURES])) & (y_true <= hi.predict(te[FEATURES])))), 3),
        "exceed_rate": round(float(ex_true.mean()), 3),
        "train_rows": int(len(tr)),
    }
    # Refit on everything for the production forecast.
    m, lo, hi, clf = fit_all(data)
    return Model(m, lo, hi, clf, codes, threshold, metrics)


def predict(model: Model, readings: pd.DataFrame, wx: pd.DataFrame, t0: pd.Timestamp,
            horizon: int = 48) -> pd.DataFrame:
    """Station rows plus a 'ward' aggregate (mean of stations; p_exceed from the mean forecast's spread)."""
    origins = pd.DatetimeIndex([t0])
    rows = build_rows(readings, wx, origins, horizon, model.station_codes, with_target=False)
    if rows.empty:
        return pd.DataFrame(columns=["station_id", "ts", "pm10", "pm10_lo", "pm10_hi", "p_exceed"])
    X = rows[FEATURES]
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
