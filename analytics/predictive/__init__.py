"""
analytics.predictive package

Exposes:
    outage_risk(feeder_id: str, storm: dict) -> float
    predict_etr(damage_type: str, crews_available: int, now: datetime) -> ETR
"""

from analytics.predictive.outage_risk import outage_risk, calculate_risk
from analytics.predictive.etr import predict_etr, ETR

__all__ = ["outage_risk", "calculate_risk", "predict_etr", "ETR"]
