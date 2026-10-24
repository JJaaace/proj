"""Decision coverage, sanitized output, playback invariance, and message boundaries."""

from collections import Counter
from dataclasses import asdict, replace
from datetime import timedelta
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services.events.audit import AuditTrail, delivery_decision
from services.events.triggers import AlertHistory, get_alert_events
from .demo import DemoAlert
from .integration import PROJECT_ROOT
from .presentation import Playback, export_audit
from .replay import main, run_replay
from .test_lifecycle import operation


def test_each_emitted_alert_has_one_linked_decision_and_outcome(runtime):
    """All real AlertEvent objects have exactly one matching audit emission/outcome."""
    result = run_replay(runtime, crews_available=1, log=lambda line: None)
    emitted = [entry for entry in result.audit.entries if entry.category == "alert_decision" and entry.decision == "emitted"]
    outcomes = [entry for entry in result.audit.entries if entry.category == "delivery_outcome"]
    assert len(emitted) == len(outcomes) == len(result.alerts)
    for index, (event, decision, outcome) in enumerate(zip(result.alerts, emitted, outcomes), 1):
        assert (decision.sim_time, decision.customer_id, decision.alert_type) == (
            event.sim_time.isoformat(), event.customer_id, event.alert_type,
        )
        assert decision.details["alert_sequence"] == outcome.details["alert_sequence"] == index
        assert decision.details["status"] == event.snapshot.status
        assert decision.details["previous_status"] == (event.previous_snapshot.status if event.previous_snapshot is not None else None)
        assert outcome.decision == "simulated_only"
    assert len({entry.sequence for entry in result.audit.entries}) == len(result.audit.entries)


def test_unaffected_neighbor_has_electrical_explanation(runtime):
    """Show why the same-location customer C-3 received no outage confirmation."""
    result = run_replay(runtime, crews_available=1, log=lambda line: None)
    entry = next(entry for entry in result.audit.entries if entry.customer_id == "C-3"
                 and entry.reason_code == "NOT_DOWNSTREAM_OF_FAILED_DEVICE")
    assert entry.category == "network_trace" and entry.decision == "powered"
    assert entry.details["active_devices"] == []
    assert not any(event.customer_id == "C-3" and event.alert_type == "outage_confirmed" for event in result.alerts)
    assert any(entry.customer_id == "C-3" and entry.reason_code == "LOW_RISK" for entry in result.audit.entries)


def test_repeated_replays_have_identical_events_and_audits(runtime):
    """Audit instrumentation is deterministic and does not depend on wall-clock time."""
    first = run_replay(runtime, crews_available=1, log=lambda line: None)
    second = run_replay(runtime, crews_available=1, log=lambda line: None)
    assert [asdict(event) for event in first.alerts] == [asdict(event) for event in second.alerts]
    assert first.audit.to_records() == second.audit.to_records()
    assert first.summary == second.summary


@pytest.mark.parametrize("reason,code", [
    ("throttled", "MESSAGING_THROTTLED"), ("no_consent", "MESSAGING_NO_CONSENT"),
    ("guardrail_rejected", "MESSAGING_GUARDRAIL_REJECTED"), ("send_error", "MESSAGING_SEND_ERROR"),
    (None, "MESSAGING_OUTCOME_UNAVAILABLE"), ("free text we do not understand", "MESSAGING_OUTCOME_UNAVAILABLE"),
])
def test_handler_outcomes_are_reported_without_inventing_policy(reason, code):
    """Only recognized return reasons are classified; throttle is not proof of a queue."""
    decision, actual = delivery_decision({"sent": False, "body": None, "reason": reason}, True)
    assert actual == code
    assert decision not in ("delivered", "deferred_by_messaging", "sent_dry_run")


def test_reported_dry_run_success_is_not_live_delivery(runtime):
    """Count a handler's dry-run acceptance separately from physical delivery."""
    handler = Mock(return_value={"sent": True, "body": "Synthetic demo only", "reason": None})
    result = run_replay(replace(runtime, dependencies=replace(runtime.dependencies, handle_alert=handler)), log=lambda line: None)
    assert result.summary["successful_dry_runs"] == len(result.alerts)
    assert all(entry.decision == "sent_dry_run" for entry in result.audit.entries if entry.category == "delivery_outcome")
    assert all(call.kwargs == {"dry_run": True} for call in handler.call_args_list)


@pytest.mark.parametrize("verbose", [False, True])
def test_console_and_json_exclude_profiles_bodies_and_secrets(runtime, tmp_path, verbose):
    """Even hostile/free-form handler text never enters a console or exported audit."""
    secret = "sk-secret-demo-value"
    phone = "+16145550101"
    handler = Mock(return_value={"sent": False, "body": f"Call {phone}; {secret}",
                                "reason": f"api_key={secret} phone={phone}"})
    lines = []
    result = run_replay(replace(runtime, dependencies=replace(runtime.dependencies, handle_alert=handler)),
                        verbose=verbose, log=lines.append)
    path = tmp_path / "audit.json"
    export_audit(path, result, mode="demo", dry_run=True)
    document = json.loads(path.read_text())
    output = "\n".join(lines) + path.read_text()
    assert secret not in output and phone not in output
    assert "Demo One" not in output
    assert '"phone"' not in output and '"first_name"' not in output
    assert document["format_version"] == 1
    assert document["summary"]["alerts_emitted"] == len(result.alerts)
    assert document["entries"] == result.audit.to_records()


def test_export_and_cli_preserve_existing_files(runtime, tmp_path):
    """Neither report export nor CLI startup overwrites existing user work."""
    path = tmp_path / "existing.json"
    path.write_text("existing work")
    result = run_replay(runtime, log=lambda line: None)
    with pytest.raises(FileExistsError):
        export_audit(path, result, mode="demo", dry_run=True)
    with pytest.raises(SystemExit) as error:
        main(["--demo", "--audit-json", str(path)])
    assert error.value.code == 2 and path.read_text() == "existing work"


def test_audit_rejects_unapproved_profile_fields(now):
    """Keep arbitrary snapshots or handler message text out of private audit details."""
    with pytest.raises(ValueError, match="Unapproved"):
        AuditTrail().record(now, "delivery_outcome", "unknown", "TEST", details={"body": "secret"})


def test_medical_and_restoration_events_are_preserved_during_throttle(runtime, now):
    """Person 3 forwards every burst event and its medical flag despite throttled returns."""
    timeline = [operation(now, "device_failed", damage_type="blown_fuse"),
                operation(now + timedelta(minutes=1), "crew_assigned", crew_id="CREW-2"),
                operation(now + timedelta(minutes=2), "damage_assessed", damage_type="broken_pole"),
                operation(now + timedelta(minutes=3), "device_restored")]
    handler = Mock(return_value={"sent": False, "body": None, "reason": "throttled"})
    result = run_replay(replace(runtime, timeline=timeline, dependencies=replace(runtime.dependencies, handle_alert=handler)),
                        crews_available=1, log=lambda line: None)
    for identifier in ("C-1", "C-2"):
        events = [event for event in result.alerts if event.customer_id == identifier]
        assert set(event.alert_type for event in events) == {"pre_storm", "outage_confirmed", "crew_assigned", "etr_update", "restored"}
        assert all(event.snapshot.medical_priority == (identifier == "C-1") for event in events)
        assert next(event.sim_time for event in events if event.alert_type == "restored") == now + timedelta(minutes=3)
    assert [call.args[0] for call in handler.call_args_list] == result.alerts
    assert all(call.args[0] is event for call, event in zip(handler.call_args_list, result.alerts))
    assert result.summary["delivery_reason_counts"] == {"MESSAGING_THROTTLED": len(result.alerts)}
    assert all(entry.details["deferred_support"] == "UNVERIFIED" for entry in result.audit.entries if entry.category == "delivery_outcome")


@pytest.mark.parametrize("speed,step,interactive", [
    ("instant", False, False), ("fast", False, False), ("normal", False, False),
    ("instant", True, True), ("instant", True, False),
])
def test_playback_controls_leave_domain_results_unchanged(runtime, speed, step, interactive):
    """Inject timing and input so presentation tests never wait or prompt the user."""
    sleeper, reader = Mock(), Mock(return_value="")
    playback = Playback(speed=speed, step=step, interactive=interactive, sleep=sleeper, read=reader)
    baseline = run_replay(runtime, crews_available=1, log=lambda line: None)
    result = run_replay(runtime, crews_available=1, playback=playback, log=lambda line: None)
    assert result.alerts == baseline.alerts
    assert result.audit.to_records() == baseline.audit.to_records()
    assert result.summary == baseline.summary
    assert reader.call_count == (playback.frames if step and interactive else 0)
    if speed == "instant":
        sleeper.assert_not_called()


def test_handler_exception_is_audited_without_losing_future_alerts(runtime):
    """A failed handler is an error outcome, not a lost source event or a leaked secret."""
    handler = Mock(side_effect=RuntimeError("api_key=sk-secret +16145550101"))
    lines = []
    result = run_replay(replace(runtime, dependencies=replace(runtime.dependencies, handle_alert=handler)), log=lines.append)
    assert result.summary["delivery_reason_counts"] == {"MESSAGING_SEND_ERROR": len(result.alerts)}
    assert result.snapshots["C-1"].status == "restored"
    assert "sk-secret" not in "\n".join(lines)


def test_incomplete_or_invalid_snapshot_never_becomes_an_event(snapshot):
    """Validate all public fields before invoking a permissive alert constructor."""
    incomplete = asdict(snapshot)
    del incomplete["phone"]
    with pytest.raises(ValueError, match="Incomplete"):
        get_alert_events(None, SimpleNamespace(**incomplete), snapshot.updated_at, AlertHistory(), alert_model=DemoAlert)
    invalid = replace(snapshot, confidence="high")
    with pytest.raises(ValueError, match="present together"):
        get_alert_events(None, invalid, snapshot.updated_at, AlertHistory(), alert_model=DemoAlert)


def test_duplicate_evaluation_is_explained(snapshot):
    """An idempotent evaluation logs suppression instead of another emitted alert."""
    history, audit = AlertHistory(), AuditTrail()
    current = replace(snapshot, status="at_risk")
    for _ in range(2):
        get_alert_events(snapshot, current, current.updated_at, history, alert_model=DemoAlert, audit=audit)
    assert Counter(entry.decision for entry in audit.entries)["emitted"] == 1
    assert all(entry.reason_code == "DUPLICATE_EVENT_SUPPRESSED" for entry in audit.entries[-5:])


def test_help_never_loads_or_runs_replay(monkeypatch):
    """Help prints the flags before any dependency loader or handler can run."""
    loader = Mock()
    monkeypatch.setattr("tests.storm_replay.replay.load_runtime", loader)
    with pytest.raises(SystemExit) as error:
        main(["--help"])
    assert error.value.code == 0
    loader.assert_not_called()


def test_noninteractive_cli_step_exports_sanitized_report(tmp_path):
    """The actual CLI completes without user input and writes usable report JSON."""
    path = tmp_path / "audit.json"
    process = subprocess.run([sys.executable, "-m", "tests.storm_replay.replay", "--demo", "--step",
                              "--audit-json", str(path)], cwd=PROJECT_ROOT, stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=20)
    assert process.returncode == 0, process.stderr
    report = json.loads(path.read_text())
    assert report["dry_run"] is True and report["mode"] == "demo"
    assert report["summary"]["alerts_by_type"] == {
        "pre_storm": 3, "outage_confirmed": 3, "crew_assigned": 3, "etr_update": 6, "restored": 3,
    }
    assert "noninteractive input" in process.stdout
    assert any(entry["category"] == "replay_step" and "position" in entry["details"] for entry in report["entries"])
