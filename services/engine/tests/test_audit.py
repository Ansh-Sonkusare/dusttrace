import pandas as pd
import pytest

from dusttrace import audit
from dusttrace.sources import synthetic

T0 = pd.Timestamp("2026-01-20 12:00", tz="UTC")  # winter, dry season


@pytest.fixture(scope="module")
def env():
    wx = synthetic.weather(T0 - pd.Timedelta(days=15), T0)
    rd = synthetic.readings(wx, ["s1"])
    ambient = rd.set_index("ts")["pm10"].interpolate(limit_direction="both")
    return wx, ambient


def spec(fault="none", sensor_id="A-1"):
    return audit.SensorSpec(sensor_id=sensor_id, site_id="A", site_lat=19.117, site_lon=72.856,
                            area_m2=8000, activity="excavation", fault=fault)


def run(env, fault):
    wx, ambient = env
    s = spec(fault)
    sim = audit.simulate([s], ambient, wx, T0)
    return audit.score(s, sim, ambient, wx, T0)


def failed(result):
    return {name for name, c in result.checks.items() if not c["ok"]}


def test_healthy_sensor_is_trusted(env):
    r = run(env, "none")
    assert failed(r) == set()
    assert r.score == 100 and r.band == "trusted"


def test_flatline_is_caught(env):
    r = run(env, "flatline")
    assert "flatline" in failed(r)
    assert r.band != "trusted"


def test_dropout_is_caught(env):
    r = run(env, "dropout")
    assert "dropout" in failed(r)
    assert r.band != "trusted"


def test_too_clean_sensor_is_untrusted(env):
    r = run(env, "too_clean")
    assert {"neighbour", "placement"} <= failed(r)
    assert r.band == "untrusted" and r.score < 40
    assert any("downwind" in x for x in r.reasons)


def test_drift_is_caught(env):
    assert "drift" in failed(run(env, "drift"))


def test_humidity_bias_is_caught(env):
    assert "humidity" in failed(run(env, "rh_bias"))


def test_reasons_are_plain_sentences(env):
    r = run(env, "too_clean")
    assert r.reasons and all(x[0].isupper() and x.endswith(".") for x in r.reasons)


def test_simulated_readings_are_deterministic(env):
    wx, ambient = env
    a = audit.simulate([spec()], ambient, wx, T0)
    b = audit.simulate([spec()], ambient, wx, T0 - pd.Timedelta(hours=3))
    both = a.merge(b, on=["sensor_id", "ts"])
    assert len(both) > 100 and (both["pm10_x"] - both["pm10_y"]).abs().max() < 1e-6


def test_benchmark_catches_injected_faults(env):
    wx, ambient = env
    m = audit.benchmark(ambient, wx, T0, n=50)
    assert m["n"] == 50
    assert m["precision"] >= 0.9 and m["recall"] >= 0.85


def test_checks_without_enough_data_pass_and_store_as_null(env):
    wx, ambient = env
    s = spec("none")
    r = audit.score(s, audit.simulate([s], ambient, wx, T0).iloc[0:0], ambient, wx, T0)  # no readings at all
    assert r.checks["drift"]["value"] is None and r.checks["drift"]["ok"]
    assert not r.checks["dropout"]["ok"]  # but a silent sensor is still offline
