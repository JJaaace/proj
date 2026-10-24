"""
test_predictive.py - Unit tests for analytics/predictive modules.
Tests features.py, outage_risk.py, etr.py, and train.py.
"""

from datetime import datetime, timedelta
import pytest

from analytics.predictive.features import (
    extract_feeder_features,
    extract_storm_features,
    build_interaction_features,
    create_feature_vector,
)
from analytics.predictive.outage_risk import outage_risk, calculate_risk
from analytics.predictive.etr import predict_etr, ETR
from analytics.predictive.train import (
    generate_synthetic_historical_data,
    train_and_save_model,
    load_model,
)


@pytest.fixture
def sample_feeder_fdr3():
    return {
        "id": "FDR-3",
        "substation_id": "SUB-1",
        "overhead_pct": 0.80,
        "vegetation_density": 0.60,
        "avg_asset_age_years": 32,
    }


@pytest.fixture
def sample_storm_ava():
    return {
        "name": "Storm Ava",
        "start_time": "2026-10-24T18:00:00",
        "start_lat": 39.75,
        "start_lon": -83.35,
        "heading_degrees": 60.0,
        "speed_kmh": 40.0,
        "wind_radius_km": 15.0,
        "peak_gust_kmh": 110.0,
        "rainfall_mm": 60.0,
    }


def test_feature_engineering_pipeline(sample_feeder_fdr3, sample_storm_ava):
    feats = create_feature_vector(sample_feeder_fdr3, sample_storm_ava)
    assert "overhead_pct" in feats
    assert "wind_severity" in feats
    assert "tree_fall_hazard" in feats
    assert feats["tree_fall_hazard"] > 0.0
    assert feats["underground_exposure"] >= 0.0


def test_outage_risk_fdr3_storm_ava(sample_storm_ava):
    score = outage_risk("FDR-3", sample_storm_ava)
    assert 0.68 <= score <= 0.76, f"Expected ~0.72, got {score}"


def test_predict_etr_unknown_damage():
    now = datetime(2026, 10, 24, 20, 0, 0)
    etr = predict_etr("unknown", crews_available=3, now=now)
    assert etr["confidence"] == "low"
    assert (etr["etr_end"] - etr["etr_start"]).total_seconds() / 3600.0 >= 2.0


def test_predict_etr_broken_pole_vs_fuse():
    now = datetime(2026, 10, 24, 20, 0, 0)
    fuse_etr = predict_etr("blown_fuse", crews_available=1, now=now)
    pole_etr = predict_etr("broken_pole", crews_available=1, now=now)
    assert pole_etr["etr_end"] > fuse_etr["etr_end"]


def test_train_and_load_model():
    artifact = train_and_save_model(num_samples=100)
    assert artifact["model_name"] == "OutageRiskCalibratedPhysicalModel"
    loaded = load_model()
    assert "calibration_factor" in loaded
