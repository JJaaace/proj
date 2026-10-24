"""
etr.py - Estimated Time of Restoration (ETR) prediction model.

Owner: Person 2 (Predictions and Maps)
Layer: Layer 2 Analytics (analytics/predictive)

Contract (Section 6.3):
    predict_etr(damage_type: str, crews_available: int, now: datetime) -> ETR
    where ETR is:
        {
            "etr_start": datetime,
            "etr_end": datetime,
            "confidence": "low" | "medium" | "high"
        }

Rules:
    - unknown damage always returns confidence = "low" and a wide range.
    - broken_pole and substation_damage take much longer than blown_fuse.
    - Never return a single exact time; always a realistic window.
"""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import TypedDict, Literal, Dict, Any, Union


ConfidenceLevel = Literal["low", "medium", "high"]


class ETR(dict):
    """
    ETR result mapping. Inherits from dict for exact schema compliance (dict subscripting)
    while also exposing convenient dot-notation attributes.
    """
    def __init__(self, etr_start: datetime, etr_end: datetime, confidence: ConfidenceLevel):
        super().__init__(etr_start=etr_start, etr_end=etr_end, confidence=confidence)

    @property
    def etr_start(self) -> datetime:
        return self["etr_start"]

    @property
    def etr_end(self) -> datetime:
        return self["etr_end"]

    @property
    def confidence(self) -> ConfidenceLevel:
        return self["confidence"]


# Base duration ranges (min_hours, max_hours, baseline_confidence) when 1 crew is actively working
DAMAGE_PROFILES: Dict[str, Dict[str, Any]] = {
    "blown_fuse": {
        "min_hours": 0.75,     # 45 mins
        "max_hours": 1.50,     # 90 mins
        "confidence": "high",
        "description": "Replace/re-fuse cutout and patrol tap",
    },
    "tree_on_line": {
        "min_hours": 1.50,     # 1 hr 30 mins
        "max_hours": 3.00,     # 3 hrs
        "confidence": "high",
        "description": "Clear tree branches, splice downed conductors",
    },
    "transformer_failure": {
        "min_hours": 2.50,     # 2 hrs 30 mins
        "max_hours": 4.50,     # 4 hrs 30 mins
        "confidence": "medium",
        "description": "Rig, hoist and connect replacement transformer",
    },
    "broken_pole": {
        "min_hours": 4.50,     # 4 hrs 30 mins
        "max_hours": 8.00,     # 8 hrs
        "confidence": "medium",
        "description": "Dig hole, plant replacement utility pole, transfer lines",
    },
    "substation_damage": {
        "min_hours": 6.00,     # 6 hrs
        "max_hours": 12.00,    # 12 hrs
        "confidence": "low",
        "description": "Substation breaker/busbar switching, engineering inspection",
    },
    "unknown": {
        "min_hours": 2.00,     # 2 hrs
        "max_hours": 6.00,     # 6 hrs (wide range)
        "confidence": "low",   # Mandated rule: unknown ALWAYS returns "low"
        "description": "Crews patrolling circuit to identify fault location and cause",
    },
}


def _parse_datetime(dt: Union[datetime, str]) -> datetime:
    """Robustly parse ISO string or validate datetime object."""
    if isinstance(dt, datetime):
        return dt
    if isinstance(dt, str):
        # Support ISO 8601 strings (e.g. 2026-10-24T20:05:00)
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    raise TypeError(f"Expected datetime or ISO string, got {type(dt)}")


def predict_etr(damage_type: str, crews_available: int, now: Union[datetime, str]) -> ETR:
    """
    Predict Estimated Time of Restoration range and confidence.

    Parameters:
        damage_type: One of 'unknown', 'tree_on_line', 'blown_fuse', 'broken_pole',
                     'transformer_failure', 'substation_damage'
        crews_available: Number of utility restoration crews currently assigned/available
        now: Current simulation timestamp (datetime or ISO 8601 string)

    Returns:
        ETR: Mapping with 'etr_start', 'etr_end', and 'confidence'
    """
    current_time = _parse_datetime(now)
    profile = DAMAGE_PROFILES.get(damage_type.lower(), DAMAGE_PROFILES["unknown"])

    min_h = profile["min_hours"]
    max_h = profile["max_hours"]
    confidence: ConfidenceLevel = profile["confidence"]

    # If damage is unknown, MUST ALWAYS be low confidence and wide window
    if damage_type.lower() == "unknown":
        confidence = "low"

    # Adjust for crew availability
    if crews_available <= 0:
        # No crew on site yet: dispatch latency adds 45-90 minutes, confidence degrades
        dispatch_delay_hours = 1.0
        min_h += dispatch_delay_hours
        max_h += dispatch_delay_hours + 0.5
        if confidence == "high":
            confidence = "medium"
        elif confidence == "medium":
            confidence = "low"
    elif crews_available >= 2:
        # Multiple crews expedite work (e.g., pole setting + line restringing in parallel)
        min_h = max(0.5, min_h * 0.80)
        max_h = max(min_h + 0.5, max_h * 0.85)

    # Ensure min range spread is at least 30 minutes for honesty
    if (max_h - min_h) < 0.5:
        max_h = min_h + 0.5

    start_delta = timedelta(minutes=round(min_h * 60))
    end_delta = timedelta(minutes=round(max_h * 60))

    etr_start = current_time + start_delta
    etr_end = current_time + end_delta

    return ETR(etr_start=etr_start, etr_end=etr_end, confidence=confidence)
