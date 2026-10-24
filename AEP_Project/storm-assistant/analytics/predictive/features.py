"""
features.py - Feature extraction and engineering for outage risk prediction.

Owner: Person 2 (Predictions & Geospatial)
Layer: Layer 2 Analytics (analytics/predictive)

Extracts and standardizes grid and meteorological attributes into numerical features
for both real-time inference (outage_risk.py) and offline calibration/training (train.py).
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
import math


def extract_feeder_features(feeder: Dict[str, Any]) -> Dict[str, float]:
    """
    Extract and normalize physical infrastructure features for a feeder.

    Parameters:
        feeder: Feeder dictionary containing overhead_pct, vegetation_density, avg_asset_age_years

    Returns:
        Dict[str, float]: Standardized feature dict
    """
    overhead_pct = max(0.0, min(1.0, float(feeder.get("overhead_pct", 0.70))))
    vegetation_density = max(0.0, min(1.0, float(feeder.get("vegetation_density", 0.50))))
    avg_asset_age_years = max(0.0, float(feeder.get("avg_asset_age_years", 25.0)))

    # Derived infrastructure metrics
    underground_pct = 1.0 - overhead_pct
    age_normalized = min(avg_asset_age_years / 40.0, 2.0)  # 40-year utility design lifespan

    return {
        "overhead_pct": overhead_pct,
        "underground_pct": underground_pct,
        "vegetation_density": vegetation_density,
        "avg_asset_age_years": avg_asset_age_years,
        "age_normalized": age_normalized,
    }


def extract_storm_features(storm: Dict[str, Any]) -> Dict[str, float]:
    """
    Extract and normalize meteorological features from storm parameters.

    Parameters:
        storm: Storm dictionary with peak_gust_kmh, rainfall_mm, wind_radius_km, speed_kmh

    Returns:
        Dict[str, float]: Standardized storm feature dict
    """
    peak_gust_kmh = max(0.0, float(storm.get("peak_gust_kmh", 80.0)))
    rainfall_mm = max(0.0, float(storm.get("rainfall_mm", 25.0)))
    wind_radius_km = max(1.0, float(storm.get("wind_radius_km", 15.0)))
    speed_kmh = max(0.0, float(storm.get("speed_kmh", 40.0)))

    # Wind force increases quadratically with speed (dynamic pressure = 0.5 * rho * v^2)
    # Scaled against 100 km/h benchmark
    if peak_gust_kmh <= 30.0:
        wind_severity = peak_gust_kmh / 150.0
    else:
        wind_severity = (peak_gust_kmh / 100.0) ** 1.5

    # Soil saturation: heavy rainfall loosens root systems, making trees fall under wind
    soil_saturation = 1.0 + 0.20 * min(rainfall_mm / 50.0, 1.5)

    return {
        "peak_gust_kmh": peak_gust_kmh,
        "rainfall_mm": rainfall_mm,
        "wind_radius_km": wind_radius_km,
        "speed_kmh": speed_kmh,
        "wind_severity": wind_severity,
        "soil_saturation": soil_saturation,
    }


def build_interaction_features(
    feeder_feats: Dict[str, float],
    storm_feats: Dict[str, float],
) -> Dict[str, float]:
    """
    Compute compound interaction features reflecting real-world failure mechanics:
    - High wind + high tree density + overhead wire = prime branch falling hazard
    - Saturated soil + aging poles = pole tilt / structural collapse hazard
    """
    oh = feeder_feats["overhead_pct"]
    veg = feeder_feats["vegetation_density"]
    wind_sev = storm_feats["wind_severity"]
    soil_sat = storm_feats["soil_saturation"]
    age_norm = feeder_feats["age_normalized"]

    # Tree-to-overhead line contact risk
    tree_exposure = oh * (0.30 + 0.70 * veg)
    tree_fall_hazard = wind_sev * tree_exposure * soil_sat

    # Structural pole stress (wind load on aged crossarms/poles)
    pole_stress_hazard = wind_sev * oh * (0.80 + 0.40 * age_norm)

    # Underground line immunity (underground lines only fail from extreme flood or rare equipment fault)
    underground_exposure = feeder_feats["underground_pct"] * 0.04

    return {
        "tree_exposure": tree_exposure,
        "tree_fall_hazard": tree_fall_hazard,
        "pole_stress_hazard": pole_stress_hazard,
        "underground_exposure": underground_exposure,
    }


def create_feature_vector(
    feeder: Dict[str, Any],
    storm: Dict[str, Any],
) -> Dict[str, float]:
    """
    Complete combined feature dictionary for a feeder under given storm conditions.
    """
    feeder_feats = extract_feeder_features(feeder)
    storm_feats = extract_storm_features(storm)
    interactions = build_interaction_features(feeder_feats, storm_feats)

    features = {}
    features.update(feeder_feats)
    features.update(storm_feats)
    features.update(interactions)
    return features
