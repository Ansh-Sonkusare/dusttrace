import pandas as pd

from dusttrace import attribution

T0 = pd.Timestamp("2026-01-20 00:00", tz="UTC")
STATION = {"id": "st", "name": "Chakala station", "lat": 19.11, "lon": 72.86}


def wx_from(deg, speed=2.0, hours=24, blh=400.0):
    ts = pd.date_range(T0 + pd.Timedelta(hours=1), periods=hours, freq="h", tz="UTC")
    return pd.DataFrame({"ts": ts, "wind_speed": speed, "wind_dir": float(deg), "blh": blh})


def p_high(wx, p=0.8):
    return pd.Series(p, index=pd.DatetimeIndex(wx["ts"]))


def site(id_, dlat=0.0, dlon=0.0, **kw):
    return {"id": id_, "name": f"Site {id_}", "lat": STATION["lat"] + dlat, "lon": STATION["lon"] + dlon, **kw}


def test_back_trajectory_runs_upwind():
    pts = attribution.back_trajectory(STATION["lat"], STATION["lon"], wx_from(90).iloc[:3])
    lons = [p[1] for p in pts]
    assert lons[0] == STATION["lon"] and all(b > a for a, b in zip(lons, lons[1:]))  # wind from the east: look east


def test_site_directly_upwind_outranks_one_off_axis():
    wx = wx_from(90)  # wind from the east
    sites = [site("up", dlon=0.01), site("side", dlat=0.01), site("down", dlon=-0.01)]
    exp = attribution.upwind_exposure(sites, [STATION], wx, p_high(wx))
    assert exp["up"] > 0.5 > exp["side"] and exp["down"] == 0


def test_no_spike_risk_means_no_upwind_exposure():
    wx = wx_from(90)
    exp = attribution.upwind_exposure([site("up", dlon=0.01)], [STATION], wx, p_high(wx, 0.1))
    assert exp["up"] == 0


def test_low_trust_raises_priority():
    ranked = attribution.rank([
        {"site_id": "A", "name": "A", "upwind": 0.5, "trust": 95, "has_sensor": True},
        {"site_id": "B", "name": "B", "upwind": 0.5, "trust": 30, "has_sensor": True},
    ])
    assert [r.site_id for r in ranked] == ["B", "A"]
    assert ranked[0].rank == 1 and ranked[0].score > ranked[1].score


def test_reasons_name_the_two_largest_components():
    ranked = attribution.rank([
        {"site_id": "D", "name": "Debris yard", "upwind": 0.9, "trust": None, "has_sensor": False,
         "reports": 0, "violations": 0, "upwind_station": "Chakala station", "upwind_hours": 7},
    ])
    r = ranked[0]
    assert len(r.reasons) == 2
    assert "upwind of Chakala station" in r.reasons[0] and "no dust monitor" in r.reasons[1]
    assert set(r.components) == {"upwind", "trust", "reports", "unsensored", "violations"}


def test_ranking_is_deterministic_on_ties():
    rows = [{"site_id": x, "name": x, "upwind": 0.2, "trust": 80, "has_sensor": True} for x in "CAB"]
    assert [r.site_id for r in attribution.rank(rows)] == ["A", "B", "C"]
