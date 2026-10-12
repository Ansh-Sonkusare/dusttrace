import pandas as pd

from dusttrace import agent, alerts

NOW = pd.Timestamp("2026-11-12 12:30", tz="UTC")
SPIKE = [NOW + pd.Timedelta(hours=h) for h in (13, 14)]


def case(**kw):
    base = dict(site_id="A", name="Metro Line 7A excavation", activity="excavation", has_sensor=True,
                has_relay=True, trust=90.0, now=NOW)
    ctx = agent.SiteContext(**{**base, **kw})
    return alerts.SiteState(ctx=ctx, decision=agent.decide(ctx), case_id=42, plan_accepted=False, avoid_now=False)


def kinds(rows):
    return {a.kind for a in rows}


def test_spike_with_no_mitigation_is_critical():
    out = alerts.derive([case(has_relay=False, spike_hours=SPIKE, spike_receptors=["St. Xavier's School"])])
    crit = [a for a in out if a.kind == "critical"]
    assert crit and "no misting" in crit[0].title.lower() and crit[0].case_id == 42
    assert crit[0].action  # every alert carries an action


def test_spike_with_a_relay_is_not_critical():
    assert "critical" not in kinds(alerts.derive([case(spike_hours=SPIKE, spike_receptors=["School"])]))


def test_accepted_plan_counts_as_mitigation():
    s = case(has_relay=False, spike_hours=SPIKE, spike_receptors=["School"])
    s.plan_accepted = True
    assert "critical" not in kinds(alerts.derive([s]))


def test_dusty_work_inside_an_avoid_window_is_an_action_alert():
    s = case(sensor_hot_hours=1)
    s.avoid_now = True
    out = [a for a in alerts.derive([s]) if a.kind == "action"]
    assert out and "Avoid window" in out[0].title


def test_untrusted_sensor_and_school_downwind():
    out = alerts.derive([case(trust=30.0, sensitive_avoid=[(SPIKE[0], "St. Xavier's School")])])
    assert {"sensor", "receptor"} <= kinds(out)
    rec = next(a for a in out if a.kind == "receptor")
    assert "St. Xavier's School" in rec.title and "close windows" in rec.action.lower()


def test_quiet_site_raises_nothing_and_order_is_by_severity():
    assert alerts.derive([case()]) == []
    out = alerts.derive([case(trust=30.0, sensitive_avoid=[(SPIKE[0], "School")], has_relay=False,
                              spike_hours=SPIKE, spike_receptors=["School"])])
    assert [a.kind for a in out] == sorted([a.kind for a in out], key=alerts.SEVERITY.index)
