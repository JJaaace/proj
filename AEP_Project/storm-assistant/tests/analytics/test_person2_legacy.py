"""
test_person2_models.py - Comprehensive tests for Person 2 deliverables.

Validates:
1. outage_risk(feeder_id, storm)
2. predict_etr(damage_type, crews_available, now)
3. storm_position(storm, t)
4. storm_arrival_time(storm, lat, lon)
5. in_high_wind_zone(storm, lat, lon, t)
"""

from datetime import datetime, timedelta
import pytest

from analytics.predictive.outage_risk import outage_risk, calculate_risk
from analytics.predictive.etr import predict_etr, ETR, DAMAGE_PROFILES
from analytics.geospatial.storm_overlay import (
    storm_position,
    storm_arrival_time,
    in_high_wind_zone,
    haversine_distance_km,
)


@pytest.fixture
def storm_ava():
    """Sample storm matching Section 6.1 of the specification."""
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


# ============================================================================
# 1. OUTAGE RISK TESTS
# ============================================================================

def test_outage_risk_fdr3_calibrated_to_spec(storm_ava):
    """
    Maria on FDR-3 in the spec example snapshot has risk_score: 0.72.
    Verify FDR-3 with Storm Ava produces approx 0.72.
    """
    score = outage_risk("FDR-3", storm_ava)
    assert 0.68 <= score <= 0.76, f"Expected ~0.72, got {score}"
    assert 0.0 <= score <= 1.0


def test_outage_risk_mild_weather():
    """Mild weather should produce low risk score."""
    mild_storm = {
        "peak_gust_kmh": 25.0,
        "rainfall_mm": 5.0,
    }
    score = outage_risk("FDR-1", mild_storm)
    assert score < 0.20, f"Expected low risk for mild weather, got {score}"


def test_outage_risk_severe_weather():
    """Severe storm with aging high-vegetation feeder should produce high risk."""
    severe_storm = {
        "peak_gust_kmh": 130.0,
        "rainfall_mm": 80.0,
    }
    score = outage_risk("FDR-4", severe_storm)
    assert score >= 0.80, f"Expected high risk for severe storm, got {score}"


def test_outage_risk_underground_vs_overhead():
    """Underground lines (overhead_pct=0) should have much lower risk than overhead lines."""
    storm = {"peak_gust_kmh": 100.0, "rainfall_mm": 50.0}
    underground_risk = calculate_risk(
        overhead_pct=0.0,
        vegetation_density=0.8,
        avg_asset_age_years=30.0,
        peak_gust_kmh=100.0,
        rainfall_mm=50.0,
    )
    overhead_risk = calculate_risk(
        overhead_pct=1.0,
        vegetation_density=0.8,
        avg_asset_age_years=30.0,
        peak_gust_kmh=100.0,
        rainfall_mm=50.0,
    )
    assert underground_risk < overhead_risk
    assert underground_risk < 0.20


def test_outage_risk_unknown_feeder():
    """Unknown feeder ID should gracefully fallback to sensible estimate without error."""
    storm = {"peak_gust_kmh": 90.0, "rainfall_mm": 40.0}
    score = outage_risk("FDR-NONEXISTENT-999", storm)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


# ============================================================================
# 2. RESTORATION TIME (ETR) TESTS
# ============================================================================

def test_predict_etr_all_damage_types():
    """Ensure all 6 spec damage types return valid ETR with positive range."""
    damage_types = [
        "unknown",
        "tree_on_line",
        "blown_fuse",
        "broken_pole",
        "transformer_failure",
        "substation_damage",
    ]
    now = datetime(2026, 10, 24, 20, 0, 0)
    for dt in damage_types:
        etr = predict_etr(damage_type=dt, crews_available=1, now=now)
        assert isinstance(etr, dict)
        assert "etr_start" in etr
        assert "etr_end" in etr
        assert "confidence" in etr
        assert etr["etr_start"] > now
        assert etr["etr_end"] > etr["etr_start"]
        assert etr["confidence"] in ["low", "medium", "high"]


def test_predict_etr_unknown_damage_rule():
    """
    SPEC MANDATED RULE:
    unknown damage always returns confidence = 'low' and a wide range.
    """
    now = datetime(2026, 10, 24, 20, 0, 0)
    # Even if 5 crews are available, unknown damage MUST be low confidence
    etr = predict_etr(damage_type="unknown", crews_available=5, now=now)
    assert etr["confidence"] == "low"
    range_duration = (etr["etr_end"] - etr["etr_start"]).total_seconds() / 3600.0
    assert range_duration >= 2.0, "Unknown damage must return a wide range"


def test_predict_etr_relative_durations():
    """
    SPEC MANDATED RULE:
    broken_pole and substation_damage take much longer than blown_fuse.
    """
    now = datetime(2026, 10, 24, 20, 0, 0)
    fuse_etr = predict_etr("blown_fuse", crews_available=1, now=now)
    pole_etr = predict_etr("broken_pole", crews_available=1, now=now)
    sub_etr = predict_etr("substation_damage", crews_available=1, now=now)

    fuse_duration = (fuse_etr["etr_end"] - now).total_seconds() / 3600.0
    pole_duration = (pole_etr["etr_end"] - now).total_seconds() / 3600.0
    sub_duration = (sub_etr["etr_end"] - now).total_seconds() / 3600.0

    assert pole_duration > fuse_duration * 2.5
    assert sub_duration > fuse_duration * 4.0


def test_predict_etr_crew_availability_impact():
    """Crews available = 0 should delay restoration and widen/degrade confidence."""
    now = datetime(2026, 10, 24, 20, 0, 0)
    etr_no_crew = predict_etr("tree_on_line", crews_available=0, now=now)
    etr_with_crew = predict_etr("tree_on_line", crews_available=1, now=now)

    assert etr_no_crew["etr_start"] > etr_with_crew["etr_start"]
    assert etr_no_crew["etr_end"] > etr_with_crew["etr_end"]


def test_predict_etr_iso_string_input():
    """predict_etr should accept ISO timestamp string as now parameter."""
    etr = predict_etr("tree_on_line", crews_available=1, now="2026-10-24T20:05:00")
    assert isinstance(etr["etr_start"], datetime)
    assert etr.confidence in ["low", "medium", "high"]


# ============================================================================
# 3. GEOSPATIAL & STORM OVERLAY TESTS
# ============================================================================

def test_storm_position_movement(storm_ava):
    """Test storm moves along heading at specified speed."""
    t0 = datetime(2026, 10, 24, 18, 0, 0)
    pos0 = storm_position(storm_ava, t0)
    assert pytest.approx(pos0[0], abs=1e-3) == storm_ava["start_lat"]
    assert pytest.approx(pos0[1], abs=1e-3) == storm_ava["start_lon"]

    # 1 hour later: moved 40 km along bearing 60 degrees (North-East)
    t1 = t0 + timedelta(hours=1)
    pos1 = storm_position(storm_ava, t1)
    # Both lat (North) and lon (East) must have increased
    assert pos1[0] > pos0[0], "Lat should increase when heading is 60 deg"
    assert pos1[1] > pos0[1], "Lon should increase when heading is 60 deg"

    # Great circle distance should equal 40 km
    dist = haversine_distance_km(pos0[0], pos0[1], pos1[0], pos1[1])
    assert pytest.approx(dist, abs=0.5) == 40.0


def test_in_high_wind_zone(storm_ava):
    """Test detection of whether a point is inside the wind radius."""
    t = datetime(2026, 10, 24, 18, 0, 0)
    c_lat, c_lon = storm_ava["start_lat"], storm_ava["start_lon"]

    # At the storm eye: definitely in wind zone
    assert in_high_wind_zone(storm_ava, c_lat, c_lon, t) is True

    # 5 km away: well within 15 km wind radius
    assert in_high_wind_zone(storm_ava, c_lat + 0.03, c_lon, t) is True

    # 60 km away: well outside 15 km wind radius
    assert in_high_wind_zone(storm_ava, c_lat + 0.6, c_lon, t) is False


def test_storm_arrival_time_direct_hit(storm_ava):
    """Test storm arrival time for a point directly along its trajectory."""
    # Point ~35 km northeast of start
    target_lat = 39.91
    target_lon = -83.05

    arrival = storm_arrival_time(storm_ava, target_lat, target_lon)
    assert arrival is not None
    t0 = datetime.fromisoformat(storm_ava["start_time"])
    assert arrival > t0
    # At 40 km/h, arrival should be within 2 hours
    diff_hours = (arrival - t0).total_seconds() / 3600.0
    assert 0.2 <= diff_hours <= 2.5


def test_storm_arrival_time_miss(storm_ava):
    """A customer far off the storm track should return None."""
    # Point 200 km to the south
    far_lat = 37.50
    far_lon = -83.20

    arrival = storm_arrival_time(storm_ava, far_lat, far_lon)
    assert arrival is None


def test_storm_arrival_time_already_inside(storm_ava):
    """If point is already within wind radius at start time, arrival is start time."""
    start_lat = storm_ava["start_lat"]
    start_lon = storm_ava["start_lon"]
    t0 = datetime.fromisoformat(storm_ava["start_time"])

    arrival = storm_arrival_time(storm_ava, start_lat, start_lon)
    assert arrival == t0
