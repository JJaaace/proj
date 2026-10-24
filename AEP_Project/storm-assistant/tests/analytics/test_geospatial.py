"""
test_geospatial.py - Unit tests for analytics/geospatial modules.
Tests storm_overlay.py, hazards.py, and clustering.py.
"""

from datetime import datetime, timedelta
import pytest

from analytics.geospatial.storm_overlay import (
    storm_position,
    storm_arrival_time,
    in_high_wind_zone,
    haversine_distance_km,
)
from analytics.geospatial.hazards import assess_hazards, assess_flood_hazard
from analytics.geospatial.clustering import cluster_outages


@pytest.fixture
def sample_storm():
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


def test_storm_position(sample_storm):
    t0 = datetime(2026, 10, 24, 18, 0, 0)
    pos = storm_position(sample_storm, t0)
    assert pytest.approx(pos[0], abs=1e-3) == sample_storm["start_lat"]
    assert pytest.approx(pos[1], abs=1e-3) == sample_storm["start_lon"]


def test_storm_arrival_time(sample_storm):
    arrival = storm_arrival_time(sample_storm, 39.91, -83.05)
    assert arrival is not None
    assert arrival > datetime.fromisoformat(sample_storm["start_time"])


def test_assess_hazards_flooding(sample_storm):
    report = assess_hazards(39.99, -83.01, sample_storm)
    assert "flood_risk" in report
    assert report["flood_risk"] in ["moderate", "severe"]
    assert "downed_line_risk" in report


def test_cluster_outages():
    reports = [
        {"customer_id": "C-1", "lat": 39.990, "lon": -83.010},
        {"customer_id": "C-2", "lat": 39.991, "lon": -83.011},  # ~100m away, same cluster
        {"customer_id": "C-3", "lat": 39.992, "lon": -83.012},  # ~200m away, same cluster
        {"customer_id": "C-4", "lat": 40.050, "lon": -83.080},  # ~10km away, separate cluster
    ]
    clusters = cluster_outages(reports, max_distance_km=0.50)
    assert len(clusters) == 2
    assert clusters[0]["count"] == 3
    assert "C-1" in clusters[0]["customer_ids"]
    assert clusters[1]["count"] == 1
    assert "C-4" in clusters[1]["customer_ids"]
