"""Dust Response Agent: one test per dust rule D1-D10, plus the guard rails."""

import pandas as pd

from dusttrace import agent

NOW = pd.Timestamp("2026-11-12 12:30", tz="UTC")  # 18:00 IST
SPIKE = [NOW + pd.Timedelta(hours=h) for h in (13, 14, 15)]  # 07:00-09:00 IST tomorrow


def ctx(**kw):
    base = dict(site_id="A", name="Metro Line 7A excavation", activity="excavation", has_sensor=True,
                has_relay=True, trust=90.0, now=NOW)
    return agent.SiteContext(**{**base, **kw})


def actions(decision, which="final"):
    return {a.action: a for a in getattr(decision, which)}


def test_quiet_site_opens_no_case():
    assert agent.decide(ctx()) is None


def test_d1_single_signal_gets_no_enforcement():
    d = agent.decide(ctx(site_id="D", has_sensor=False, has_relay=False, trust=None))
    acts = actions(d)
    assert "REQUEST_SPOT_CHECK" in acts and acts["REQUEST_SPOT_CHECK"].rule == "D1"
    assert not {"ADD_TO_INSPECTION", "REGISTER_UNSENSORED_SITE", "ISSUE_NOTICE"} & set(acts)
    assert "D1" in d.what_changed and "an officer spot check" in acts["REQUEST_SPOT_CHECK"].reason


def test_d2_spike_issues_windows_and_schedules_mist_90_min_early():
    d = agent.decide(ctx(spike_hours=SPIKE, spike_receptors=["St. Xavier's School"]))
    acts = actions(d)
    assert acts["ISSUE_SAFE_WORK_WINDOW"].route == "auto" and acts["ISSUE_SAFE_WORK_WINDOW"].rule == "D2"
    mist = acts["SCHEDULE_MIST"]
    assert mist.route == "auto" and mist.at == SPIKE[0] - pd.Timedelta(minutes=90)


def test_d2_without_a_relay_asks_the_site_to_pre_wet():
    acts = actions(agent.decide(ctx(has_relay=False, spike_hours=SPIKE, spike_receptors=["School"])))
    assert acts["SCHEDULE_MIST"].route == "site" and acts["PRE_WET_SITE"].route == "site"


def test_d3_school_downwind_in_avoid_window_is_alerted():
    acts = actions(agent.decide(ctx(sensitive_avoid=[(SPIKE[0], "St. Xavier's School")])))
    assert acts["ALERT_RECEPTOR"].rule == "D3" and acts["ALERT_RECEPTOR"].route == "auto"
    assert "St. Xavier's School" in acts["ALERT_RECEPTOR"].reason
    assert "NOTIFY_RESIDENTS" in acts


def test_d4_hot_sensor_triggers_mist_now_then_pause():
    acts = actions(agent.decide(ctx(sensor_hot_hours=1)))
    assert acts["TRIGGER_MIST_NOW"].rule == "D4" and acts["TRIGGER_MIST_NOW"].route == "auto"
    assert "PAUSE_DUSTY_TASK" not in acts
    acts = actions(agent.decide(ctx(sensor_hot_hours=2, has_relay=False)))
    assert acts["TRIGGER_MIST_NOW"].route == "site" and acts["PAUSE_DUSTY_TASK"].route == "site"


def test_d5_untrusted_sensor_is_flagged_and_inspected():
    acts = actions(agent.decide(ctx(trust=28.0)))
    assert acts["FLAG_SENSOR_FOR_AUDIT"].route == "auto" and acts["FLAG_SENSOR_FOR_AUDIT"].rule == "D5"
    assert acts["ADD_TO_INSPECTION"].route == "L1" and acts["ADD_TO_INSPECTION"].status == "proposed"


def test_d6_unsensored_site_with_two_signals_is_registered():
    d = agent.decide(ctx(site_id="D", has_sensor=False, has_relay=False, trust=None, citizen_reports=2))
    acts = actions(d)
    assert acts["REGISTER_UNSENSORED_SITE"].route == "L1" and acts["REGISTER_UNSENSORED_SITE"].rule == "D6"
    assert acts["ADD_TO_INSPECTION"].route == "L1"


def test_d7_unanswered_request_escalates_and_nothing_is_assumed():
    overdue = [{"action": "REQUEST_SITE_PHOTO", "deadline": NOW - pd.Timedelta(hours=1)}]
    d = agent.decide(ctx(spike_hours=SPIKE, spike_receptors=["School"], pending_requests=overdue))
    acts = actions(d)
    assert acts["ADD_TO_INSPECTION"].rule == "D7"
    assert "none" in d.what_changed.lower() and "assumed" in d.what_changed.lower()
    assert d.expired == ["REQUEST_SITE_PHOTO"]


def test_d8_repeat_exceedances_issue_a_notice():
    acts = actions(agent.decide(ctx(exceedances_7d=3, citizen_reports=1)))
    assert acts["ISSUE_NOTICE"].route == "L1" and acts["ISSUE_NOTICE"].rule == "D8"
    acts = actions(agent.decide(ctx(ignored_windows=2, citizen_reports=1)))
    assert "ISSUE_NOTICE" in acts


def test_d8_on_one_signal_waits_for_evidence():
    acts = actions(agent.decide(ctx(exceedances_7d=3)))
    assert "ISSUE_NOTICE" not in acts and "REQUEST_SITE_PHOTO" in acts


def test_d9_stop_work_is_only_ever_a_proposal_to_l2():
    acts = actions(agent.decide(ctx(exceedances_7d=4, citizen_reports=1, confirmed_violation=True,
                                    sensitive_avoid=[(SPIKE[0], "Nanavati Hospital")])))
    stop = acts["RECOMMEND_STOP_WORK"]
    assert stop.route == "L2" and stop.rule == "D9" and stop.status == "proposed"
    assert "RECOMMEND_STOP_WORK" not in actions(agent.decide(ctx(exceedances_7d=4, citizen_reports=1)))


def test_d10_non_construction_cause_is_referred_with_no_site_action():
    d = agent.decide(ctx(spike_hours=SPIKE, spike_receptors=["School"], non_construction=True))
    acts = actions(d)
    assert acts["REFER_NON_CONSTRUCTION"].rule == "D10"
    assert d.hypotheses[0][0] == "non_construction"
    assert not {"SCHEDULE_MIST", "PAUSE_DUSTY_TASK", "ISSUE_NOTICE"} & set(acts)


def test_every_action_comes_from_the_catalog_and_cites_a_rule():
    d = agent.decide(ctx(trust=30.0, spike_hours=SPIKE, spike_receptors=["School"], sensor_hot_hours=2,
                         sensitive_avoid=[(SPIKE[0], "School")], exceedances_7d=3, citizen_reports=1))
    for a in d.initial + d.final:
        assert (a.type, a.route_options) == agent.CATALOG[a.action][:2]
        assert a.route in a.route_options and a.rule and a.reason
    assert "UPDATE_DUST_SCORE" in actions(d)


def test_hypotheses_are_probabilities():
    d = agent.decide(ctx(trust=30.0, spike_hours=SPIKE, spike_receptors=["School"]))
    assert abs(sum(p for _, p in d.hypotheses) - 1) < 0.005  # rounded to 3 dp
    assert d.hypotheses == sorted(d.hypotheses, key=lambda h: -h[1])


def test_d6_satellite_change_is_a_second_signal_for_an_unsensored_site():
    d = agent.decide(ctx(site_id="D", has_sensor=False, has_relay=False, trust=None, satellite_active=True))
    acts = actions(d)
    assert "satellite change" in d.signals
    assert acts["REGISTER_UNSENSORED_SITE"].rule == "D6" and "REQUEST_SPOT_CHECK" not in acts


def test_a_site_whose_feed_is_not_connected_is_not_treated_as_unmonitored():
    d = agent.decide(ctx(site_id="osm-way-1", has_sensor=False, sensor_known=False, has_relay=False, trust=None))
    assert d is None  # nothing triggers: unknown is not "no monitor"
    d = agent.decide(ctx(site_id="osm-way-1", has_sensor=False, sensor_known=False, has_relay=False, trust=None,
                         sensitive_avoid=[(SPIKE[0], "School")]))
    assert "unsensored_site" not in d.triggers and "site registry" not in d.signals


# F10 playbook (issue #34): cause from the PM10/PM2.5 signature, and the fix sent to the site.
RECEPTORS = ["Homes for about 900 people (estimated)"]


def top(d):
    return d.hypotheses[0][0]


def test_coarse_dust_in_working_hours_points_to_digging_or_demolition():
    d = agent.decide(ctx(activity="structure", spike_hours=SPIKE, spike_receptors=RECEPTORS, pm_signature="coarse_work"))
    base = agent.decide(ctx(activity="structure", spike_hours=SPIKE, spike_receptors=RECEPTORS))
    h, b = dict(d.hypotheses), dict(base.hypotheses)
    assert h["dry_excavation"] > b["dry_excavation"] and h["demolition"] > b["demolition"]
    assert "coarse" in d.what_changed.lower() or any("coarse" in a.reason.lower() for a in d.final)


def test_coarse_dust_at_night_points_to_truck_trackout_and_orders_a_wheel_wash():
    d = agent.decide(ctx(activity="excavation", spike_hours=SPIKE, spike_receptors=RECEPTORS, pm_signature="coarse_night"))
    assert top(d) == "truck_trackout"
    a = actions(d)["ORDER_WHEEL_WASH"]
    assert a.route == "site" and a.rule == "F10" and a.status == "sent" and "night" in a.reason


def test_fine_dust_leans_to_a_non_construction_source_without_dropping_site_actions():
    d = agent.decide(ctx(spike_hours=SPIKE, spike_receptors=RECEPTORS, pm_signature="fine"))
    base = agent.decide(ctx(spike_hours=SPIKE, spike_receptors=RECEPTORS))
    assert dict(d.hypotheses)["non_construction"] > dict(base.hypotheses)["non_construction"]
    assert "REFER_NON_CONSTRUCTION" not in actions(d)  # D10 still needs evidence beyond one station
    assert "ISSUE_SAFE_WORK_WINDOW" in actions(d)


def test_uncovered_debris_gets_a_cover_order_with_a_two_hour_deadline():
    d = agent.decide(ctx(activity="debris", has_sensor=True, sensor_hot_hours=1))
    assert top(d) == "uncovered_debris"
    a = actions(d)["ORDER_COVER_DEBRIS"]
    assert a.rule == "F10" and a.route == "site" and a.deadline == NOW + pd.Timedelta(hours=2)


def test_dry_windy_day_ahead_means_pre_wet_even_without_a_spike():
    windy = [NOW + pd.Timedelta(hours=h) for h in (14, 15)]
    d = agent.decide(ctx(activity="excavation", dry_windy_hours=windy))
    assert d is not None and "dry_windy" in d.triggers
    a = actions(d)["PRE_WET_SITE"]
    assert a.rule == "F10" and "wind" in a.reason.lower()
    assert agent.decide(ctx(activity="structure", dry_windy_hours=windy)) is None  # finishing work raises little dust


def test_playbook_actions_are_dropped_for_a_non_construction_source():
    d = agent.decide(ctx(activity="debris", sensor_hot_hours=1, non_construction=True))
    assert not {"ORDER_COVER_DEBRIS", "ORDER_WHEEL_WASH", "PRE_WET_SITE"} & set(actions(d))
