"""
storm_overlay.py - Geospatial storm trajectory and arrival time calculator.

Owner: Person 2 (Predictions and Maps)
Layer: Layer 2 Analytics (analytics/geospatial)

Contracts (Section 6.3):
    storm_position(storm: dict, t: datetime) -> tuple[float, float]
    storm_arrival_time(storm: dict, lat: float, lon: float) -> datetime | None
    in_high_wind_zone(storm: dict, lat: float, lon: float, t: datetime) -> bool

Model:
    Storm center point moves along a straight path at a fixed speed with a wind radius.
    Computes when the high-wind boundary reaches each customer (or None if track misses).
"""

from __future__ import annotations
import math
from datetime import datetime, timedelta
from typing import Tuple, Optional, Union

# Earth mean radius in kilometers
EARTH_RADIUS_KM = 6371.0


def _parse_datetime(dt: Union[datetime, str]) -> datetime:
    """Parse ISO timestamp or validate datetime object."""
    if isinstance(dt, datetime):
        return dt
    if isinstance(dt, str):
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    raise TypeError(f"Expected datetime or ISO string, got {type(dt)}")


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in kilometers."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_KM * c


def storm_position(storm: dict, t: Union[datetime, str]) -> Tuple[float, float]:
    """
    Compute storm center coordinate (lat, lon) at simulated time t.

    Parameters:
        storm: Dict containing 'start_lat', 'start_lon', 'start_time',
               'heading_degrees', 'speed_kmh'
        t: Target timestamp (datetime or ISO string)

    Returns:
        (lat, lon): Tuple of floats (center coordinates)
    """
    target_time = _parse_datetime(t)
    start_time = _parse_datetime(storm.get("start_time", target_time))

    start_lat = float(storm.get("start_lat", 39.90))
    start_lon = float(storm.get("start_lon", -83.15))
    heading_deg = float(storm.get("heading_degrees", 60.0))
    speed_kmh = float(storm.get("speed_kmh", 40.0))

    # Elapsed hours from start
    delta_hours = (target_time - start_time).total_seconds() / 3600.0
    dist_km = speed_kmh * delta_hours

    if abs(dist_km) < 1e-6:
        return (round(start_lat, 6), round(start_lon, 6))

    # Spherical geodesy destination point formula
    angular_dist = dist_km / EARTH_RADIUS_KM
    bearing_rad = math.radians(heading_deg)

    lat1 = math.radians(start_lat)
    lon1 = math.radians(start_lon)

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_dist)
        + math.cos(lat1) * math.sin(angular_dist) * math.cos(bearing_rad)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_dist) * math.cos(lat1),
        math.cos(angular_dist) - math.sin(lat1) * math.sin(lat2),
    )

    dest_lat = math.degrees(lat2)
    dest_lon = (math.degrees(lon2) + 540.0) % 360.0 - 180.0

    return (round(dest_lat, 6), round(dest_lon, 6))


def in_high_wind_zone(storm: dict, lat: float, lon: float, t: Union[datetime, str]) -> bool:
    """
    Determine if the given coordinate is currently within the storm's wind radius at time t.

    Parameters:
        storm: Storm metadata dict with wind_radius_km
        lat: Target latitude
        lon: Target longitude
        t: Target timestamp (datetime or ISO string)

    Returns:
        bool: True if inside the wind radius, False otherwise
    """
    center_lat, center_lon = storm_position(storm, t)
    wind_radius = float(storm.get("wind_radius_km", 15.0))
    dist = haversine_distance_km(center_lat, center_lon, lat, lon)
    return dist <= wind_radius


def storm_arrival_time(
    storm: dict,
    lat: float,
    lon: float,
) -> Optional[datetime]:
    """
    Calculate the timestamp when the storm's high-wind boundary first reaches (lat, lon).
    Returns None if the storm track never intersects the target within wind_radius_km,
    or if the storm has already completed passing before start_time.

    Parameters:
        storm: Storm dictionary with trajectory and start parameters
        lat: Customer/premise latitude
        lon: Customer/premise longitude

    Returns:
        datetime | None: First arrival timestamp, or None if track misses
    """
    start_time = _parse_datetime(storm["start_time"])
    start_lat = float(storm.get("start_lat", 39.90))
    start_lon = float(storm.get("start_lon", -83.15))
    heading_deg = float(storm.get("heading_degrees", 60.0))
    speed_kmh = float(storm.get("speed_kmh", 40.0))
    wind_radius = float(storm.get("wind_radius_km", 15.0))

    if speed_kmh <= 0.0:
        # Stationary storm: either covers point or does not
        init_dist = haversine_distance_km(start_lat, start_lon, lat, lon)
        return start_time if init_dist <= wind_radius else None

    # Local equirectangular tangent plane centered at start point
    # x: East distance (km), y: North distance (km)
    mid_lat = math.radians((start_lat + lat) / 2.0)
    x = EARTH_RADIUS_KM * math.radians(lon - start_lon) * math.cos(mid_lat)
    y = EARTH_RADIUS_KM * math.radians(lat - start_lat)

    # Velocity components (heading: 0=N, 90=E, 180=S, 270=W)
    theta = math.radians(heading_deg)
    vx = speed_kmh * math.sin(theta)
    vy = speed_kmh * math.cos(theta)
    v = speed_kmh

    # Closest approach time (hours from start_time)
    # The dot product of position vector and velocity vector
    t_closest_hours = (x * vx + y * vy) / (v * v)

    # Minimum perpendicular distance squared at closest approach
    d_min_sq = (x * x + y * y) - (v * v) * (t_closest_hours * t_closest_hours)
    d_min_sq = max(0.0, d_min_sq)
    d_min = math.sqrt(d_min_sq)

    # Check if closest approach enters the wind radius
    if d_min > wind_radius:
        # Storm track misses this location
        return None

    # Half-duration spent inside the wind circle
    half_chord_km = math.sqrt(max(0.0, wind_radius * wind_radius - d_min_sq))
    t_half_hours = half_chord_km / v

    t_entry_hours = t_closest_hours - t_half_hours
    t_exit_hours = t_closest_hours + t_half_hours

    # If storm already completely passed before start_time
    if t_exit_hours < 0.0:
        return None

    # If location is already inside the wind circle at start_time
    if t_entry_hours <= 0.0:
        return start_time

    # Normal case: storm arrives in the future
    arrival_seconds = round(t_entry_hours * 3600.0)
    return start_time + timedelta(seconds=arrival_seconds)
