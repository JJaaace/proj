"""Shared contracts for customer snapshots and customer-facing alerts."""

from dataclasses import dataclass
from typing import Literal

CustomerStatus = Literal["normal", "at_risk", "outage_confirmed", "restored"]
DamageType = Literal[
    "unknown",
    "tree_on_line",
    "blown_fuse",
    "broken_pole",
    "transformer_failure",
    "substation_damage",
]
Confidence = Literal["low", "medium", "high"]
CrewStatus = Literal["assigned", "on_site"]
AlertType = Literal[
    "pre_storm",
    "outage_confirmed",
    "crew_assigned",
    "etr_update",
    "restored",
]


@dataclass(frozen=True)
class CustomerSnapshot:
    """A point-in-time customer status and restoration estimate."""

    customer_id: str
    first_name: str
    phone: str
    language: str
    sms_opt_in: bool
    medical_priority: bool
    feeder_id: str | None
    transformer_id: str | None
    status: CustomerStatus
    risk_score: float | None
    storm_arrival: str | None
    cause: DamageType | None
    etr_start: str | None
    etr_end: str | None
    confidence: Confidence | None
    crew_status: CrewStatus | None
    updated_at: str | None


@dataclass(frozen=True)
class AlertEvent:
    """An alert payload containing current and optional prior customer state."""

    alert_type: AlertType
    customer_id: str
    snapshot: CustomerSnapshot
    previous_snapshot: CustomerSnapshot | None
    sim_time: str
