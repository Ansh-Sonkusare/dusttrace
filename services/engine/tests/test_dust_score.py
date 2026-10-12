from dusttrace import dust_score


def score(**kw):
    base = dict(trust=None, has_sensor=True, spike_hours=0, windows_followed=None, verified_reports=0, violations=0)
    return dust_score.compute(**{**base, **kw})


def test_a_model_site_scores_100_and_is_good():
    s = score(trust=100, windows_followed=1.0)
    assert s.score == 100 and s.band == "good"


def test_weights_follow_the_prd():
    assert dust_score.WEIGHTS == {"trust": 30, "spikes": 25, "windows": 20, "reports": 15, "inspections": 10}
    assert sum(dust_score.WEIGHTS.values()) == 100


def test_no_sensor_loses_the_trust_share():
    s = score(has_sensor=False, windows_followed=1.0)
    assert s.score == 70 and s.components["trust"] == 0


def test_unknown_windows_count_half_and_say_so():
    s = score(trust=100)
    assert s.components["windows"] == 10
    assert any("not reported" in r for r in s.notes)


def test_bad_behaviour_drives_the_score_down_and_is_bounded():
    s = score(trust=20, spike_hours=12, windows_followed=0.0, verified_reports=5, violations=4)
    assert 0 <= s.score < 40 and s.band == "poor"
    assert score(trust=0, has_sensor=False, spike_hours=99, windows_followed=0, verified_reports=99, violations=99).score == 0


def test_bands():
    assert dust_score.band(80) == "good" and dust_score.band(79.9) == "fair"
    assert dust_score.band(40) == "fair" and dust_score.band(39.9) == "poor"
