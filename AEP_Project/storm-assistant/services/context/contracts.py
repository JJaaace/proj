"""Internal dependency injection; canonical public models remain Person 1's."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping


DAMAGE_TYPES = frozenset({
    "unknown", "tree_on_line", "blown_fuse", "broken_pole",
    "transformer_failure", "substation_damage",
})
EVENT_TYPES = frozenset({
    "device_failed", "crew_assigned", "crew_on_site",
    "damage_assessed", "device_restored",
})


def local_time(value: str | datetime) -> datetime:
    """Parse the contract's local ISO time, rejecting timezone mixing."""
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.tzinfo is not None:
        raise ValueError(f"Expected a local datetime without timezone: {value!r}")
    return result


def field(value: Any, name: str) -> Any:
    """Read a documented field from a dict, dataclass, or Pydantic model."""
    return value[name] if isinstance(value, Mapping) else getattr(value, name)


@dataclass(frozen=True)
class Dependencies:
    """Inject Section 6 functions without importing absent upstream packages."""

    snapshot_model: Callable[..., Any]
    alert_model: Callable[..., Any]
    downstream_customers: Callable[[str], list[str]]
    outage_risk: Callable[[str, dict], float]
    predict_etr: Callable[..., Any]
    storm_position: Callable[[dict, datetime], tuple[float, float]]
    storm_arrival_time: Callable[[dict, float, float], datetime | None]
    in_high_wind_zone: Callable[[dict, float, float, datetime], bool]
    handle_alert: Callable[..., dict]


@dataclass(frozen=True)
class Town:
    """Validated source-shaped synthetic records and their electrical IDs."""

    substations: list[dict]
    feeders: list[dict]
    transformers: list[dict]
    customers: list[dict]

    def __post_init__(self) -> None:
        """Reject broken references and malformed customer attributes early."""
        seen: set[str] = set()
        for records in (self.substations, self.feeders, self.transformers, self.customers):
            for record in records:
                identifier = record.get("id")
                if not isinstance(identifier, str) or not identifier or identifier in seen:
                    raise ValueError(f"Missing or duplicate grid/customer ID: {identifier!r}")
                seen.add(identifier)
        subs = {r["id"] for r in self.substations}
        feeders = {r["id"] for r in self.feeders}
        transformers = {r["id"] for r in self.transformers}
        for records, key, parents in (
            (self.feeders, "substation_id", subs),
            (self.transformers, "feeder_id", feeders),
            (self.customers, "transformer_id", transformers),
        ):
            for record in records:
                if record.get(key) not in parents:
                    raise ValueError(f"{record['id']}: invalid {key}={record.get(key)!r}")
        for customer in self.customers:
            for key in ("first_name", "phone", "language"):
                if not isinstance(customer.get(key), str) or not customer[key]:
                    raise ValueError(f"{customer['id']}: invalid {key}")
            for key in ("sms_opt_in", "medical_priority"):
                if type(customer.get(key)) is not bool:
                    raise ValueError(f"{customer['id']}: {key} must be boolean")
            for key, limit in (("lat", 90), ("lon", 180)):
                value = customer.get(key)
                if type(value) not in (int, float) or not -limit <= value <= limit:
                    raise ValueError(f"{customer['id']}: invalid {key}")

    @property
    def device_ids(self) -> set[str]:
        """Return equipment IDs, excluding customer IDs."""
        return {r["id"] for rows in (self.substations, self.feeders, self.transformers) for r in rows}
