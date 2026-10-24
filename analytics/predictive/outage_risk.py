"""
outage_risk.py - Feeder outage risk prediction model.

Owner: Person 2 (Predictions and Maps)
Layer: Layer 2 Analytics (analytics/predictive)

Contract (Section 6.3):
    outage_risk(feeder_id: str, storm: dict) -> float  # 0.0 to 1.0
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

# Default fallback feeder catalog for when data/sample/feeders.json has not been created yet
# Values calibrated to match Section 6.1 and Section 6.4 of the specification.
DEFAULT_FEEDERS: Dict[str, Dict[str, Any]] = {
    "FDR-1": {
        "id": "FDR-1",
        "substation_id": "SUB-1",
        "overhead_pct": 0.30,
        "vegetation_density": 0.25,
        "avg_asset_age_years": 14,
    },
    "FDR-2": {
        "id": "FDR-2",
        "substation_id": "SUB-1",
        "overhead_pct": 0.60,
        "vegetation_density": 0.45,
        "avg_asset_age_years": 24,
    },
    "FDR-3": {
        "id": "FDR-3",
        "substation_id": "SUB-1",
        "overhead_pct": 0.80,
        "vegetation_density": 0.60,
        "avg_asset_age_years": 32,
    },
    "FDR-4": {
        "id": "FDR-4",
        "substation_id": "SUB-2",
        "overhead_pct": 0.95,
        "vegetation_density": 0.85,
        "avg_asset_age_years": 45,
    },
}

_FEEDERS_CACHE: Optional[Dict[str, Dict[str, Any]]] = None


def find_sample_file(filename: str = "feeders.json") -> Optional[Path]:
    """Search common project paths for sample data files."""
    candidates = [
        Path(f"data/sample/{filename}"),
        Path(f"data/examples/{filename}"),
        Path(f"AEP_Project/storm-assistant/data/sample/{filename}"),
        Path(f"AEP_Project/storm-assistant/data/examples/{filename}"),
        Path(__file__).resolve().parent.parent.parent / "data" / "sample" / filename,
        Path(__file__).resolve().parent.parent.parent / "AEP_Project" / "storm-assistant" / "data" / "sample" / filename,
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def load_feeders() -> Dict[str, Dict[str, Any]]:
    """Load feeders from data/sample/feeders.json or return calibrated fallback."""
    global _FEEDERS_CACHE
    if _FEEDERS_CACHE is not None:
        return _FEEDERS_CACHE

    p = find_sample_file("feeders.json")
    if p and p.is_file():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    _FEEDERS_CACHE = {item["id"]: item for item in data if "id" in item}
                    return _FEEDERS_CACHE
                elif isinstance(data, dict):
                    _FEEDERS_CACHE = data
                    return _FEEDERS_CACHE
        except Exception:
            pass

    _FEEDERS_CACHE = dict(DEFAULT_FEEDERS)
    return _FEEDERS_CACHE


def calculate_risk(
    overhead_pct: float,
    vegetation_density: float,
    avg_asset_age_years: float,
    peak_gust_kmh: float,
    rainfall_mm: float,
) -> float:
    """
    Core physical vulnerability formula combining storm intensity and infrastructure resilience.
    
    Factors:
    - Wind intensity: non-linear force starting around 50 km/h, accelerating past 90 km/h.
    - Overhead exposure: underground lines (overhead_pct=0) are shielded from wind/branches.
    - Vegetation interaction: tree canopy overhang * overhead line exposure is primary cause of faults.
    - Soil saturation: rainfall softens ground, loosening roots and accelerating tree topples.
    - Asset age: aging poles/crossarms have higher structural failure probability under gust load.
    
    Calibrated so FDR-3 with Storm Ava (110 km/h, 60 mm rain) yields 0.72 risk (matching spec).
    """
    # 1. Wind Gust Factor (calibrated for km/h)
    # Under 40 km/h is benign breeze; 70-110+ km/h causes tree limb snapping and conductor contact
    gust = max(0.0, float(peak_gust_kmh))
    if gust <= 30.0:
        wind_factor = gust / 150.0  # minimal
    else:
        wind_factor = ((gust / 100.0) ** 1.5)

    # 2. Exposure & Vegetation interaction (overhead line vulnerability)
    oh = max(0.0, min(1.0, float(overhead_pct)))
    veg = max(0.0, min(1.0, float(vegetation_density)))
    # Overhead lines in dense tree corridors are at acute risk
    # Underground lines (1 - oh) have small base failure rate
    tree_exposure = oh * (0.30 + 0.70 * veg)
    underground_exposure = (1.0 - oh) * 0.04

    # 3. Rainfall / Soil saturation factor
    rain = max(0.0, float(rainfall_mm))
    rain_factor = 1.0 + 0.20 * min(rain / 50.0, 1.5)

    # 4. Asset Age factor (normalized against 40-year utility design life)
    age = max(0.0, float(avg_asset_age_years))
    age_factor = 0.80 + 0.40 * min(age / 40.0, 1.5)

    # Combined raw vulnerability
    # Calibrated coefficient 0.77 yields 0.72 for FDR-3 with Storm Ava (matching Section 6.4)
    raw_score = 0.77 * wind_factor * (tree_exposure + underground_exposure) * rain_factor * age_factor

    # Floor at 0.0 and cap at 0.99
    risk = max(0.0, min(0.99, raw_score))
    return round(risk, 2)


def outage_risk(feeder_id: str, storm: dict) -> float:
    """
    Estimate outage risk score (0.0 to 1.0) for a given feeder under forecast storm conditions.

    Parameters:
        feeder_id: Feeder identifier (e.g. 'FDR-3')
        storm: Dictionary with storm characteristics including 'peak_gust_kmh' and 'rainfall_mm'

    Returns:
        float: Probability score between 0.0 and 1.0.
    """
    feeders = load_feeders()
    feeder = feeders.get(feeder_id)

    if not feeder:
        # Fallback to realistic median feeder if unknown ID
        feeder = {
            "id": feeder_id,
            "overhead_pct": 0.70,
            "vegetation_density": 0.50,
            "avg_asset_age_years": 25.0,
        }

    overhead_pct = float(feeder.get("overhead_pct", 0.70))
    vegetation_density = float(feeder.get("vegetation_density", 0.50))
    avg_asset_age_years = float(feeder.get("avg_asset_age_years", 25.0))

    peak_gust_kmh = float(storm.get("peak_gust_kmh", 80.0))
    rainfall_mm = float(storm.get("rainfall_mm", 25.0))

    return calculate_risk(
        overhead_pct=overhead_pct,
        vegetation_density=vegetation_density,
        avg_asset_age_years=avg_asset_age_years,
        peak_gust_kmh=peak_gust_kmh,
        rainfall_mm=rainfall_mm,
    )
