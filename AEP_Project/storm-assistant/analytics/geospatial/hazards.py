"""
hazards.py - Geospatial environmental and road hazard assessment.

Owner: Person 2 (Predictions & Geospatial)
Layer: Layer 2 Analytics (analytics/geospatial)

Evaluates flood conditions, road accessibility for utility restoration crews,
and active downed wire hazard zones.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
import math


def assess_flood_hazard(rainfall_mm: float, elevation_m: Optional[float] = None) -> Dict[str, Any]:
    """
    Assess flash flooding and standing water risk based on cumulative rainfall
    and local topography.
    """
    rain = max(0.0, float(rainfall_mm))

    if rain >= 75.0:
        level = "severe"
        access_impeded = True
        desc = "Severe flash flooding likely in low-lying roads and stream crossings"
    elif rain >= 45.0:
        level = "moderate"
        access_impeded = False
        desc = "Localized water pooling; standard line trucks can pass with caution"
    elif rain >= 20.0:
        level = "minor"
        access_impeded = False
        desc = "Wet pavement and saturated road shoulders"
    else:
        level = "none"
        access_impeded = False
        desc = "Normal road surface conditions"

    return {
        "level": level,
        "access_impeded": access_impeded,
        "description": desc,
    }


def assess_hazards(
    lat: float,
    lon: float,
    storm: Dict[str, Any],
    vegetation_density: float = 0.50,
) -> Dict[str, Any]:
    """
    Produce comprehensive local hazard report for a premise or crew dispatch coordinate.

    Parameters:
        lat: Target latitude
        lon: Target longitude
        storm: Storm dictionary with rainfall_mm and peak_gust_kmh
        vegetation_density: Density of tree canopy along roads

    Returns:
        Dict[str, Any]: Hazard report with flood, downed wire, and crew accessibility status
    """
    rainfall = float(storm.get("rainfall_mm", 0.0))
    gust = float(storm.get("peak_gust_kmh", 0.0))

    flood_info = assess_flood_hazard(rainfall)

    # Downed line and debris blockage probability
    debris_index = (gust / 100.0) * vegetation_density
    if debris_index >= 0.70:
        downed_line_risk = "high"
        road_closure_probable = True
    elif debris_index >= 0.40:
        downed_line_risk = "medium"
        road_closure_probable = False
    else:
        downed_line_risk = "low"
        road_closure_probable = False

    crew_accessible = not (flood_info["access_impeded"] or (debris_index >= 0.85))

    return {
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "flood_risk": flood_info["level"],
        "flood_description": flood_info["description"],
        "downed_line_risk": downed_line_risk,
        "road_closure_probable": road_closure_probable,
        "crew_accessible": crew_accessible,
    }
