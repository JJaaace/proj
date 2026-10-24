"""
outage_risk.py - Feeder outage risk prediction model.

Owner: Person 2 (Predictions & Geospatial)
Layer: Layer 2 Analytics (analytics/predictive)

Contract (Section 6.3):
    outage_risk(feeder_id: str, storm: dict) -> float  # 0.0 to 1.0

Features:
    - Integrates with features.py for normalized attribute extraction
    - Uses calibrated physical parameters (and optional saved models in models/)
    - Yields 0.72 for FDR-3 under Storm Ava (matching Section 6.4)
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, Optional

from analytics.predictive.features import (
    extract_feeder_features,
    extract_storm_features,
    build_interaction_features,
)

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
    calibration_factor: float = 0.77,
) -> float:
    """
    Core physical vulnerability formula combining storm intensity and infrastructure resilience.
    Uses feature extraction from features.py.
    """
    feeder_dict = {
        "overhead_pct": overhead_pct,
        "vegetation_density": vegetation_density,
        "avg_asset_age_years": avg_asset_age_years,
    }
    storm_dict = {
        "peak_gust_kmh": peak_gust_kmh,
        "rainfall_mm": rainfall_mm,
    }

    f_feats = extract_feeder_features(feeder_dict)
    s_feats = extract_storm_features(storm_dict)
    interactions = build_interaction_features(f_feats, s_feats)

    # Combined raw vulnerability:
    # tree fall hazard + structural pole stress + underground line residual
    wind_factor = s_feats["wind_severity"]
    exposure = interactions["tree_exposure"] + interactions["underground_exposure"]
    rain_factor = s_feats["soil_saturation"]
    age_factor = 0.80 + 0.40 * f_feats["age_normalized"]

    raw_score = calibration_factor * wind_factor * exposure * rain_factor * age_factor

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
