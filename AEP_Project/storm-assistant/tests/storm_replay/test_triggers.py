"""Exact alert names, transition semantics, and strict ETR boundaries."""

from dataclasses import asdict, replace
from datetime import timedelta

import pytest

from services.events.triggers import AlertHistory, get_alert_events
from .demo import DemoAlert


def alerts(previous, current, history=None):
    """Evaluate triggers using only the current snapshot's simulated time."""
    return get_alert_events(previous, current, current.updated_at,
                            history if history is not None else AlertHistory(), alert_model=DemoAlert)


def test_warning_once_per_customer(snapshot):
    """Even a later risk re-entry cannot repeat a customer's pre-storm alert."""
    history = AlertHistory()
    risk = replace(snapshot, status="at_risk")
    assert [event.alert_type for event in alerts(snapshot, risk, history)] == ["pre_storm"]
    assert alerts(snapshot, risk, history) == []
    later = replace(risk, updated_at=snapshot.updated_at + timedelta(minutes=1),
                    storm_arrival=snapshot.storm_arrival + timedelta(hours=1))
    assert alerts(snapshot, later, history) == []


@pytest.mark.parametrize("risk,arrival_hours", [(0.49, 1), (0.8, 13), (0.8, None)])
def test_warning_requires_risk_and_arrival(snapshot, risk, arrival_hours):
    """A manually malformed risk state cannot generate an unsupported warning."""
    current = replace(snapshot, status="at_risk", risk_score=risk,
                      storm_arrival=None if arrival_hours is None else snapshot.updated_at + timedelta(hours=arrival_hours))
    assert alerts(snapshot, current) == []


def test_initial_outage_does_not_fabricate_transition(snapshot):
    """A baseline that starts mid-outage proves no new outage transition."""
    assert alerts(None, replace(snapshot, status="outage_confirmed")) == []


def test_outage_and_restoration_once_each_occurrence(snapshot):
    """New outages can alert again, while repeated evaluation cannot."""
    history = AlertHistory()
    out = replace(snapshot, status="outage_confirmed")
    assert [event.alert_type for event in alerts(snapshot, out, history)] == ["outage_confirmed"]
    assert alerts(snapshot, out, history) == []
    same_outage = replace(out, updated_at=out.updated_at + timedelta(minutes=1))
    assert alerts(snapshot, same_outage, history) == []
    restored = replace(out, status="restored", updated_at=out.updated_at + timedelta(minutes=10))
    assert [event.alert_type for event in alerts(out, restored, history)] == ["restored"]
    assert alerts(out, restored, history) == []
    next_outage = replace(out, updated_at=out.updated_at + timedelta(minutes=20))
    assert [event.alert_type for event in alerts(restored, next_outage, history)] == ["outage_confirmed"]
    assert history.customers[snapshot.customer_id].occurrence == 2


@pytest.mark.parametrize("status", ["assigned", "on_site"])
def test_first_crew_status_once_per_outage(snapshot, status):
    """Both None->assigned and None->on_site produce exactly one crew alert."""
    history = AlertHistory()
    previous = replace(snapshot, status="outage_confirmed")
    current = replace(previous, crew_status=status)
    assert [event.alert_type for event in alerts(previous, current, history)] == ["crew_assigned"]
    assert alerts(previous, replace(current, updated_at=current.updated_at + timedelta(minutes=1)), history) == []


def test_assigned_to_on_site_does_not_repeat_crew_alert(snapshot):
    """Advancing a crew to on-site is not another assignment notification."""
    previous = replace(snapshot, status="outage_confirmed", crew_status="assigned")
    assert alerts(previous, replace(previous, crew_status="on_site")) == []


@pytest.mark.parametrize("minutes,expected", [(0, False), (60, False), (61, True), (-60, False), (-61, True)])
@pytest.mark.parametrize("bound", ["etr_start", "etr_end"])
def test_etr_shift_is_strictly_more_than_60(snapshot, minutes, expected, bound):
    """Test both estimate bounds, in both directions, at the exact threshold."""
    previous = replace(snapshot, status="outage_confirmed", etr_start=snapshot.updated_at + timedelta(hours=3),
                       etr_end=snapshot.updated_at + timedelta(hours=5), confidence="medium")
    current = replace(previous, **{bound: getattr(previous, bound) + timedelta(minutes=minutes)})
    assert [event.alert_type for event in alerts(previous, current)] == (["etr_update"] if expected else [])


def test_etr_appearance_and_confidence_change(snapshot):
    """First estimate and confidence-only changes both count as meaningful."""
    previous = replace(snapshot, status="outage_confirmed")
    current = replace(previous, etr_start=snapshot.updated_at, etr_end=snapshot.updated_at + timedelta(hours=2), confidence="low")
    assert [event.alert_type for event in alerts(previous, current)] == ["etr_update"]
    assert [event.alert_type for event in alerts(current, replace(current, confidence="high"))] == ["etr_update"]


def test_multiple_estimate_changes_produce_one_event(snapshot):
    """Changed bounds plus confidence yield a single ETR event."""
    previous = replace(snapshot, status="outage_confirmed", etr_start=snapshot.updated_at,
                       etr_end=snapshot.updated_at + timedelta(hours=1), confidence="low")
    current = replace(previous, etr_start=previous.etr_start + timedelta(hours=3),
                      etr_end=previous.etr_end + timedelta(hours=3), confidence="high")
    assert [event.alert_type for event in alerts(previous, current)] == ["etr_update"]


def test_loss_of_confident_estimate_alerts_while_outage_continues(snapshot):
    """A new uncertainty must reach messaging without inventing a replacement ETR."""
    previous = replace(snapshot, status="outage_confirmed", etr_start=snapshot.updated_at,
                       etr_end=snapshot.updated_at + timedelta(hours=2), confidence="medium")
    current = replace(snapshot, status="outage_confirmed")
    events = alerts(previous, current)
    assert [event.alert_type for event in events] == ["etr_update"]
    assert events[0].snapshot.etr_start is None
    assert events[0].snapshot.confidence is None


def test_same_tick_events_and_exact_contract(snapshot):
    """Keep all eligible types, exact current/prior objects, and simulated time."""
    current = replace(snapshot, status="outage_confirmed", crew_status="assigned",
                      etr_start=snapshot.updated_at, etr_end=snapshot.updated_at + timedelta(hours=2), confidence="medium")
    events = alerts(snapshot, current)
    assert [event.alert_type for event in events] == ["outage_confirmed", "crew_assigned", "etr_update"]
    for event in events:
        assert set(asdict(event)) == {"alert_type", "customer_id", "snapshot", "previous_snapshot", "sim_time"}
        assert event.snapshot is current
        assert event.previous_snapshot is snapshot
        assert event.sim_time == snapshot.updated_at
        assert set(asdict(event.snapshot)) == {
            "customer_id", "first_name", "phone", "language", "sms_opt_in",
            "medical_priority", "feeder_id", "transformer_id", "status", "risk_score",
            "storm_arrival", "cause", "etr_start", "etr_end", "confidence",
            "crew_status", "updated_at",
        }


def test_restoration_does_not_emit_etr_change(snapshot):
    """Clearing stale outage facts on restoration produces only restored."""
    previous = replace(snapshot, status="outage_confirmed", confidence="high",
                       etr_start=snapshot.updated_at, etr_end=snapshot.updated_at + timedelta(hours=2))
    assert [event.alert_type for event in alerts(previous, replace(snapshot, status="restored"))] == ["restored"]


def test_mismatched_customer_rejected(snapshot):
    """Do not compare state from two different customers."""
    with pytest.raises(ValueError, match="different customers"):
        alerts(snapshot, replace(snapshot, customer_id="C-2"))
