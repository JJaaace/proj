"""
analytics.predictive package

Exposes:
    outage_risk(feeder_id: str, storm: dict) -> float
    calculate_risk(overhead_pct, vegetation_density, avg_asset_age_years, peak_gust_kmh, rainfall_mm) -> float
    predict_etr(damage_type: str, crews_available: int, now: datetime) -> ETR
    ETR
    create_feature_vector(feeder: dict, storm: dict) -> dict
    train_and_save_model() -> dict
    load_model() -> dict
"""

from analytics.predictive.outage_risk import outage_risk, calculate_risk
from analytics.predictive.etr import predict_etr, ETR
from analytics.predictive.features import (
    extract_feeder_features,
    extract_storm_features,
    build_interaction_features,
    create_feature_vector,
)
from analytics.predictive.train import train_and_save_model, load_model

__all__ = [
    "outage_risk",
    "calculate_risk",
    "predict_etr",
    "ETR",
    "extract_feeder_features",
    "extract_storm_features",
    "build_interaction_features",
    "create_feature_vector",
    "train_and_save_model",
    "load_model",
]
