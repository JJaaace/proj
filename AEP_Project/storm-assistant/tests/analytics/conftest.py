"""Isolate Person 2's calibrated unit town and generated training artifacts."""

from importlib import import_module

import pytest


@pytest.fixture(autouse=True)
def isolated_calibration_catalog(monkeypatch, tmp_path):
    """Retain original calibration assertions independently of Shaun's scenario IDs."""
    risk = import_module("analytics.predictive.outage_risk")
    train = import_module("analytics.predictive.train")
    monkeypatch.setattr(risk, "_FEEDERS_CACHE", dict(risk.DEFAULT_FEEDERS))
    monkeypatch.setattr(train, "MODELS_DIR", tmp_path / "models")
