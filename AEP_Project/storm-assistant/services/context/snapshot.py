"""Build complete canonical customer snapshots from injected team functions."""

from datetime import datetime
from typing import Any

from .contracts import Dependencies, Town, field, local_time
from .lifecycle import Failure, OperationalState, customer_status


class SnapshotBuilder:
    """Join electrical mappings, predictions, and authoritative incident facts."""

    def __init__(
        self, town: Town, dependencies: Dependencies, *, crews_available: int | None = None,
    ) -> None:
        """Require an explicit synthetic crew assumption before predicting ETRs."""
        if crews_available is not None and (
            type(crews_available) is not int or crews_available < 0
        ):
            raise ValueError("crews_available must be a nonnegative integer or None")
        self.town = town
        self.dependencies = dependencies
        self.crews_available = crews_available
        self.transformers = {row["id"]: row for row in town.transformers}
        self.primary_failures: dict[str, str] = {}

    def _estimate(self, failure: Failure) -> tuple[datetime | None, datetime | None, str | None]:
        """Anchor estimates to operational revisions; unknown damage has no ETR."""
        if self.crews_available is None or failure.damage_type == "unknown":
            return None, None, None
        key = (failure.revision, self.crews_available)
        if failure.estimate_key != key:
            estimate = self.dependencies.predict_etr(
                failure.damage_type, self.crews_available,
                failure.revised_at or failure.started_at,
            )
            start = local_time(field(estimate, "etr_start"))
            end = local_time(field(estimate, "etr_end"))
            confidence = field(estimate, "confidence")
            if start > end or confidence not in ("low", "medium", "high"):
                raise ValueError(f"Invalid ETR for {failure.device_id}")
            failure.estimate = (start, end, confidence)
            failure.estimate_key = key
        return failure.estimate

    def build_all_snapshots(
        self, storm: dict, state: OperationalState, previous_snapshots: dict[str, Any],
    ) -> dict[str, Any]:
        """Build every customer's canonical model at the current simulated time."""
        if state.sim_time is None:
            raise ValueError("Advance operational state before building snapshots")
        now = state.sim_time
        deps = self.dependencies
        risks = {}
        for feeder in self.town.feeders:
            risk = deps.outage_risk(feeder["id"], storm)
            if type(risk) not in (int, float) or not 0 <= risk <= 1:
                raise ValueError(f"Invalid risk score for {feeder['id']}: {risk!r}")
            risks[feeder["id"]] = float(risk)
        affected = state.affected_customers(
            deps.downstream_customers, {row["id"] for row in self.town.customers},
        )
        snapshots = {}
        self.primary_failures = {}
        for customer in self.town.customers:
            identifier = customer["id"]
            transformer_id = customer["transformer_id"]
            feeder_id = self.transformers[transformer_id]["feeder_id"]
            risk = risks[feeder_id]
            arrival = deps.storm_arrival_time(storm, customer["lat"], customer["lon"])
            if arrival is not None:
                arrival = local_time(arrival)
            in_zone = deps.in_high_wind_zone(storm, customer["lat"], customer["lon"], now)
            previous = previous_snapshots.get(identifier)
            failures = sorted(affected.get(identifier, []), key=lambda f: (f.started_at, f.device_id))
            status = customer_status(
                previous.status if previous is not None else None,
                affected=bool(failures), risk_score=risk, storm_arrival=arrival,
                sim_time=now, in_wind_zone=in_zone,
            )
            cause = crew_status = etr_start = etr_end = confidence = None
            if failures:
                # Track the oldest incident, breaking ties by device ID. Multiple
                # independent failures cannot support one definitive cause/ETR.
                self.primary_failures[identifier] = failures[0].device_id
                cause = "unknown"
                if len(failures) == 1:
                    failure = failures[0]
                    cause, crew_status = failure.damage_type, failure.crew_status
                    etr_start, etr_end, confidence = self._estimate(failure)
            snapshots[identifier] = deps.snapshot_model(
                customer_id=identifier, first_name=customer["first_name"], phone=customer["phone"],
                language=customer["language"], sms_opt_in=customer["sms_opt_in"],
                medical_priority=customer["medical_priority"], feeder_id=feeder_id,
                transformer_id=transformer_id, status=status, risk_score=risk,
                storm_arrival=arrival, cause=cause, etr_start=etr_start, etr_end=etr_end,
                confidence=confidence, crew_status=crew_status, updated_at=now,
            )
        return snapshots
