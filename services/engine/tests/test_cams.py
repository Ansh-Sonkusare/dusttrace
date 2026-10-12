import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dusttrace import fill
from dusttrace.sources import cams

FIX = Path(__file__).parent / "fixtures"


def test_parse_several_points():
    payload = json.loads((FIX / "cams_two_points.json").read_text())
    df = cams.parse(payload, ["st-a", "st-b"])
    assert sorted(df["station_id"].unique()) == ["st-a", "st-b"]
    assert len(df) == 48 and str(df["ts"].dt.tz) == "UTC"
    assert {"pm10", "pm25"} <= set(df.columns)


def test_parse_a_single_point_object():
    payload = json.loads((FIX / "cams_two_points.json").read_text())[0]
    assert cams.parse(payload, ["only"])["station_id"].unique().tolist() == ["only"]


def _series(n=24 * 70, start="2026-07-01"):
    ts = pd.date_range(start, periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(3)
    c = 40 + 15 * np.sin(np.arange(n) / 24 * 2 * np.pi) + rng.normal(0, 3, n)
    return ts, c


def test_correction_recovers_a_linear_bias():
    ts, c = _series()
    obs = pd.Series(1.6 * c + 12, index=ts)
    model = pd.Series(c, index=ts)
    k = fill.fit(obs, model)
    assert k.slope == pytest.approx(1.6, abs=0.05) and k.intercept == pytest.approx(12, abs=2)
    assert k.mae < 1 and k.hours == 60 * 24  # only the last 60 days of overlap


def test_correction_with_little_overlap_scales_by_means():
    ts, c = _series(n=100)
    k = fill.fit(pd.Series(2 * c, index=ts), pd.Series(c, index=ts))
    assert k.method == "ratio" and k.slope == pytest.approx(2, rel=0.05) and k.intercept == 0


def test_correction_slope_is_kept_sane():
    ts, c = _series()
    noise = pd.Series(np.random.default_rng(1).normal(60, 30, len(ts)), index=ts)  # unrelated to the model
    k = fill.fit(noise, pd.Series(c, index=ts))
    assert 0.3 <= k.slope <= 3


def test_fill_covers_only_the_hours_after_the_last_real_reading():
    ts, c = _series()
    obs = pd.Series(1.5 * c, index=ts)
    model = pd.Series(c, index=ts)
    now = ts[-1]
    real = obs[obs.index <= now - pd.Timedelta(hours=96)]  # feed stopped 4 days ago
    k = fill.fit(real, model)
    filled = fill.gap(real, model, k, now)
    assert filled.index.min() == real.index.max() + pd.Timedelta(hours=1)
    assert filled.index.max() == now and len(filled) == 96
    assert (filled - obs.reindex(filled.index)).abs().mean() < 5
