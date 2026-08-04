"""
Unit test suite for the HydroPulse Flash-Flood & Landslide Risk Engine.
Verifies risk score boundary constraints, threat category thresholds,
and low-bandwidth GeoJSON export payload size limits (< 5 KB).
"""

import json
from pathlib import Path
import numpy as np
import pytest
import xarray as xr

from src.engine.risk.classifier import RiskClassifier
from src.engine.risk.model import RiskEngine
from src.exporters.geojson_exporter import GeoJSONExporter


def create_sample_dataset(
    rain_val: float = 10.0, slope_val: float = 15.0, elev_val: float = 1000.0
) -> xr.Dataset:
    """Helper to generate a mock aligned spatial grid Dataset."""
    lats = np.linspace(6.5, 6.6, 5)
    lons = np.linspace(38.0, 38.1, 5)
    shape = (len(lats), len(lons))

    return xr.Dataset(
        data_vars={
            "rain_rate_mm_hr": (("latitude", "longitude"), np.full(shape, rain_val)),
            "slope_degrees": (("latitude", "longitude"), np.full(shape, slope_val)),
            "elevation": (("latitude", "longitude"), np.full(shape, elev_val)),
        },
        coords={"latitude": lats, "longitude": lons},
        attrs={"timestamp": "2026-08-04T18:00:00Z"},
    )


def test_risk_score_boundaries():
    """Verify that composite risk scores remain strictly within [0.0, 1.0]."""
    engine = RiskEngine()

    # Extreme low conditions
    ds_low = create_sample_dataset(rain_val=0.0, slope_val=0.0, elev_val=100.0)
    res_low = engine.calculate_risk_score(ds_low)
    scores_low = res_low["risk_score"].values
    assert np.all(scores_low >= 0.0) and np.all(scores_low <= 1.0)

    # Extreme high conditions
    ds_high = create_sample_dataset(rain_val=300.0, slope_val=80.0, elev_val=3000.0)
    res_high = engine.calculate_risk_score(ds_high)
    scores_high = res_high["risk_score"].values
    assert np.all(scores_high >= 0.0) and np.all(scores_high <= 1.0)


def test_classification_thresholds():
    """Verify threat level mapping for extreme rainfall and steep slope conditions."""
    classifier = RiskClassifier()

    assert classifier.classify_risk_level(0.10) == "LOW"
    assert classifier.classify_risk_level(0.35) == "MODERATE"
    assert classifier.classify_risk_level(0.60) == "HIGH"
    assert classifier.classify_risk_level(0.85) == "SEVERE"

    # Test severe scenario end-to-end
    engine = RiskEngine()
    ds_severe = create_sample_dataset(rain_val=60.0, slope_val=45.0, elev_val=2000.0)
    res_severe = engine.calculate_risk_score(ds_severe)
    processed = classifier.process_dataset(res_severe)

    for point in processed["spatial_grid"]:
        assert point["calculated_risk_level"] in ["HIGH", "SEVERE"]


def test_geojson_payload_size_limit(tmp_path: Path):
    """Verify that exported JSON payload stays strictly under 5 KB (5120 bytes)."""
    engine = RiskEngine()
    classifier = RiskClassifier()
    exporter = GeoJSONExporter(output_dir=tmp_path)

    ds = create_sample_dataset(rain_val=45.0, slope_val=30.0, elev_val=1500.0)
    res_ds = engine.calculate_risk_score(ds)
    payload_dict = classifier.process_dataset(res_ds, max_grid_points=30)

    exported_file = exporter.export(payload_dict, filename="test_risk_output.json")
    file_size_bytes = exported_file.stat().st_size

    assert file_size_bytes < 5120, f"Payload size {file_size_bytes} exceeds 5 KB limit."

    # Validate JSON payload structure against contract fields
    with open(exported_file, "r") as f:
        data = json.load(f)

    assert "timestamp" in data
    assert "location_bounds" in data
    assert "spatial_grid" in data
    assert len(data["spatial_grid"]) > 0

    first_point = data["spatial_grid"][0]
    assert "rain_rate_mm_hr" in first_point
    assert "slope_degrees" in first_point
    assert "calculated_risk_level" in first_point
    assert "estimated_time_to_peak_hours" in first_point
