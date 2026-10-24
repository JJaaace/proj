"""Explicit OFFLINE test doubles, never canonical schemas or SMS delivery."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from services.context.contracts import Dependencies, Town, local_time


@dataclass(frozen=True)
class DemoSnapshot:
    """Section 6-shaped stand-in until Shaun's canonical model is available."""

    customer_id: str
    first_name: str
    phone: str
    language: str
    sms_opt_in: bool
    medical_priority: bool
    feeder_id: str
    transformer_id: str
    status: str
    risk_score: float
    storm_arrival: datetime | None
    cause: str | None
    etr_start: datetime | None
    etr_end: datetime | None
    confidence: str | None
    crew_status: str | None
    updated_at: datetime


@dataclass(frozen=True)
class DemoAlert:
    """Section 6 alert stand-in used only by offline adapters and tests."""

    alert_type: str
    customer_id: str
    snapshot: DemoSnapshot
    previous_snapshot: DemoSnapshot | None
    sim_time: datetime


@dataclass(frozen=True)
class DemoETR:
    """Typed fixture estimate; not a real prediction model."""

    etr_start: datetime
    etr_end: datetime
    confidence: str


def demo_inputs() -> tuple[Town, dict, list[dict]]:
    """Provide a source-shaped synthetic town without replacing Shaun's files."""
    town = Town(
        substations=[dict(id="SUB-1", name="Fictional Demo", lat=40.0, lon=-83.0)],
        feeders=[dict(id=identifier, substation_id="SUB-1", overhead_pct=0.8,
                      vegetation_density=0.6, avg_asset_age_years=32)
                 for identifier in ("FDR-1", "FDR-2")],
        transformers=[dict(id=identifier, feeder_id=feeder, lat=40.0, lon=-83.0)
                      for identifier, feeder in (("TX-17", "FDR-1"), ("TX-18", "FDR-2"))],
        customers=[dict(
            id=identifier, first_name=name, phone=phone, lat=40.0, lon=-83.0,
            transformer_id=transformer, medical_priority=medical,
            sms_opt_in=consent, language="en",
        ) for identifier, name, phone, transformer, medical, consent in (
            ("C-1", "Demo One", "+16145550101", "TX-17", True, True),
            ("C-2", "Demo Two", "+16145550102", "TX-17", False, True),
            ("C-3", "Demo Neighbor", "+16145550103", "TX-18", False, True),
            ("C-4", "Demo Opted Out", "+16145550104", "TX-17", False, False),
        )],
    )
    storm = dict(name="Fictional Storm Ava", start_time="2026-10-24T18:00:00",
                 start_lat=40.0, start_lon=-83.5, heading_degrees=90,
                 speed_kmh=40, wind_radius_km=15, peak_gust_kmh=110, rainfall_mm=60)
    timeline = [
        dict(time="2026-10-24T18:40:00", type="device_failed", device_id="TX-17", damage_type="unknown"),
        dict(time="2026-10-24T18:50:00", type="crew_assigned", device_id="TX-17", crew_id="CREW-2"),
        dict(time="2026-10-24T19:00:00", type="crew_on_site", device_id="TX-17", crew_id="CREW-2"),
        dict(time="2026-10-24T19:10:00", type="damage_assessed", device_id="TX-17", damage_type="tree_on_line"),
        dict(time="2026-10-24T19:30:00", type="damage_assessed", device_id="TX-17", damage_type="broken_pole"),
        dict(time="2026-10-24T20:30:00", type="device_restored", device_id="TX-17"),
    ]
    return town, storm, timeline


def demo_dependencies(town: Town) -> Dependencies:
    """Construct a real adjacency graph and clearly labeled analytic stand-ins."""
    children: dict[str, list[str]] = {}
    customer_ids = {row["id"] for row in town.customers}
    for rows, parent in ((town.feeders, "substation_id"),
                         (town.transformers, "feeder_id"), (town.customers, "transformer_id")):
        for row in rows:
            children.setdefault(row[parent], []).append(row["id"])

    def downstream_customers(device_id: str) -> list[str]:
        """Traverse electrical edges in the offline directed graph."""
        if device_id not in town.device_ids:
            raise ValueError(f"Unknown demo device: {device_id}")
        pending, result = [device_id], []
        while pending:
            node = pending.pop()
            if node in customer_ids:
                result.append(node)
            pending.extend(children.get(node, []))
        return sorted(result)

    def outage_risk(feeder_id: str, storm: dict) -> float:
        """Return deterministic fixture risk, not an actual predictive model."""
        return 0.8 if feeder_id == "FDR-1" else 0.2

    def predict_etr(damage_type: str, crews_available: int, now: datetime) -> DemoETR:
        """Return illustrative ranges anchored to the operational revision."""
        hours, confidence = {
            "unknown": (6, "low"), "blown_fuse": (1, "high"),
            "tree_on_line": (2, "medium"), "broken_pole": (5, "low"),
            "transformer_failure": (3, "medium"), "substation_damage": (8, "low"),
        }[damage_type]
        return DemoETR(now + timedelta(hours=hours), now + timedelta(hours=hours + 2), confidence)

    def storm_position(storm: dict, t: datetime) -> tuple[float, float]:
        """Move an illustrative point east without claiming a geospatial model."""
        hours = (t - local_time(storm["start_time"])).total_seconds() / 3600
        return storm["start_lat"], storm["start_lon"] + hours * 0.4

    def storm_arrival_time(storm: dict, lat: float, lon: float) -> datetime | None:
        """Return the demo town's fixed fixture arrival time."""
        return local_time(storm["start_time"]) + timedelta(minutes=45)

    def in_high_wind_zone(storm: dict, lat: float, lon: float, t: datetime) -> bool:
        """Use an explicit fixture wind interval for lifecycle tests."""
        arrival = storm_arrival_time(storm, lat, lon)
        return arrival <= t <= arrival + timedelta(hours=1)

    def handle_alert(event: DemoAlert, dry_run: bool = True) -> dict:
        """Record simulated handoff only; never compose or send a text."""
        if not dry_run:
            raise ValueError("The offline demo adapter cannot send live SMS")
        return {"sent": False, "body": None, "reason": "simulated_handler; messaging not integrated"}

    return Dependencies(DemoSnapshot, DemoAlert, downstream_customers, outage_risk,
                        predict_etr, storm_position, storm_arrival_time,
                        in_high_wind_zone, handle_alert)
