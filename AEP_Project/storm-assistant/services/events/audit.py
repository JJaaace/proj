"""Private, deterministic decision records; never change the team's public models."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import re
from typing import Any

from services.context.contracts import local_time


DETAIL_FIELDS = frozenset({
    "previous_status", "status", "risk_score", "storm_arrival", "arrival_delta_minutes",
    "active_devices", "primary_device", "crew_status", "cause", "etr_start", "etr_end",
    "confidence", "previous_etr_start", "previous_etr_end", "previous_confidence",
    "etr_start_shift_minutes", "etr_end_shift_minutes", "medical_priority", "sms_opt_in",
    "source_index", "event_type", "affected_customers", "powered_customers", "handler_sent",
    "dry_run", "body_present", "body_length", "deferred_support", "outage_occurrence",
    "alert_sequence", "exception_raised", "diagnostic", "position",
})
SNAPSHOT_AUDIT_FIELDS = (
    "status", "risk_score", "storm_arrival", "cause", "crew_status", "etr_start", "etr_end",
    "confidence", "medical_priority", "sms_opt_in",
)


def safe_text(value: str) -> str:
    """Redact phone-like numbers and common credential forms from diagnostic text."""
    value = re.sub(r"(?<!\w)\+?\d[\d ()-]{7,}\d(?!\w)", "[REDACTED]", value)
    value = re.sub(r"\b(?:sk-|sk_)[A-Za-z0-9_-]+", "[REDACTED]", value)
    return re.sub(r"(?i)\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S+", "[REDACTED]", value)


def safe_value(value: Any) -> Any:
    """Serialize only explicit audit values, excluding arbitrary object representations."""
    if isinstance(value, datetime):
        return local_time(value).isoformat()
    if isinstance(value, str):
        return safe_text(value)
    if value is None or type(value) in (bool, int, float):
        return value
    if isinstance(value, (tuple, list)):
        return [safe_value(item) for item in value]
    if isinstance(value, dict):
        return {safe_text(str(key)): safe_value(item) for key, item in value.items()}
    raise ValueError("Audit values must be explicit JSON-compatible data")


def snapshot_details(snapshot: Any) -> dict:
    """Select operational fields, omitting names, phones, language, and coordinates."""
    return {name: getattr(snapshot, name) for name in SNAPSHOT_AUDIT_FIELDS}


@dataclass(frozen=True)
class ReplayAuditEntry:
    """Internal trace record, deliberately separate from CustomerSnapshot/AlertEvent."""

    sequence: int
    sim_time: str
    category: str
    customer_id: str | None
    asset_id: str | None
    alert_type: str | None
    decision: str
    reason_code: str
    details: dict


@dataclass
class AuditTrail:
    """Keep replay-local ordered records with stable emission-to-outcome linkage."""

    entries: list[ReplayAuditEntry] = field(default_factory=list)
    alert_count: int = 0

    def record(
        self, sim_time: datetime, category: str, decision: str, reason_code: str, *,
        customer_id: str | None = None, asset_id: str | None = None,
        alert_type: str | None = None, details: dict | None = None,
    ) -> ReplayAuditEntry:
        """Whitelist fields; never accept raw message bodies, handler reasons, or profiles."""
        details = dict(details or {})
        if set(details) - DETAIL_FIELDS:
            raise ValueError("Unapproved audit detail field; customer profiles and message text are excluded")
        if category == "alert_decision" and decision == "emitted":
            self.alert_count += 1
            details["alert_sequence"] = self.alert_count
        entry = ReplayAuditEntry(
            len(self.entries) + 1, local_time(sim_time).isoformat(), category,
            safe_text(customer_id) if customer_id is not None else None,
            safe_text(asset_id) if asset_id is not None else None,
            alert_type, decision, reason_code, safe_value(details),
        )
        self.entries.append(entry)
        return entry

    def to_records(self) -> list[dict]:
        """Return JSON-ready sanitized records without touching public model serialization."""
        return [asdict(entry) for entry in self.entries]


def delivery_decision(outcome: dict, dry_run: bool) -> tuple[str, str]:
    """Interpret only recognized handler results; never infer pending delivery or consent."""
    if outcome["sent"]:
        return ("sent_dry_run", "MESSAGING_SENT_DRY_RUN") if dry_run else ("reported_sent", "MESSAGING_REPORTED_SENT")
    reason = (outcome["reason"] or "").strip().lower()
    known = {
        "throttled": ("blocked_by_messaging", "MESSAGING_THROTTLED"),
        "throttle": ("blocked_by_messaging", "MESSAGING_THROTTLED"),
        "no_consent": ("blocked", "MESSAGING_NO_CONSENT"),
        "consent_blocked": ("blocked", "MESSAGING_NO_CONSENT"),
        "opted_out": ("blocked", "MESSAGING_NO_CONSENT"),
        "guardrail_rejected": ("blocked", "MESSAGING_GUARDRAIL_REJECTED"),
        "send_error": ("error", "MESSAGING_SEND_ERROR"),
        "handler_exception": ("error", "MESSAGING_SEND_ERROR"),
        "live_recipient_not_authorized": ("blocked", "LIVE_RECIPIENT_NOT_AUTHORIZED"),
        "simulated_handler; messaging not integrated": ("simulated_only", "MESSAGING_MOCK_UNAVAILABLE"),
    }
    return known.get(reason, ("unknown", "MESSAGING_OUTCOME_UNAVAILABLE"))
