"""
services.forecasting bridge

Exposes Person 2 models:
    outage_risk(feeder_id, storm)
    predict_etr(damage_type, crews_available, now)
    storm_position(storm, t)
    storm_arrival_time(storm, lat, lon)
    in_high_wind_zone(storm, lat, lon, t)
"""

try:
    from analytics.predictive import outage_risk, calculate_risk, predict_etr, ETR
    from analytics.geospatial import storm_position, storm_arrival_time, in_high_wind_zone
except ImportError:
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from analytics.predictive import outage_risk, calculate_risk, predict_etr, ETR
    from analytics.geospatial import storm_position, storm_arrival_time, in_high_wind_zone

__all__ = [
    "outage_risk",
    "calculate_risk",
    "predict_etr",
    "ETR",
    "storm_position",
    "storm_arrival_time",
    "in_high_wind_zone",
]
