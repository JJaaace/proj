"""
analytics.geospatial package

Exposes:
    storm_position(storm: dict, t: datetime) -> tuple[float, float]
    storm_arrival_time(storm: dict, lat: float, lon: float) -> datetime | None
    in_high_wind_zone(storm: dict, lat: float, lon: float, t: datetime) -> bool
    haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float
"""

from analytics.geospatial.storm_overlay import (
    storm_position,
    storm_arrival_time,
    in_high_wind_zone,
    haversine_distance_km,
)

__all__ = [
    "storm_position",
    "storm_arrival_time",
    "in_high_wind_zone",
    "haversine_distance_km",
]
