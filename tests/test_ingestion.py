"""
Unit test suite for the HydroPulse satellite and elevation data ingestion pipeline.
Uses pytest to verify URL creation, API connection fallback, DEM slope gradient computation,
and array shape/coordinate alignment.
"""

from datetime import datetime, timezone
import pytest
import numpy as np
import xarray as xr

from config.settings import settings
from src.engine.ingestion.dem_fetcher import DEMFetcher
from src.engine.ingestion.gpm_fetcher import GPMFetcher, GPMDataIngestionError
from src.engine.ingestion.pipeline import IngestionPipeline


def test_gpm_url_builder():
    """Verify that GPM IMERG URL builder generates valid NASA GES DISC path strings."""
    fetcher = GPMFetcher()
    test_time = datetime(2026, 8, 4, 14, 15, tzinfo=timezone.utc)
    url = fetcher.build_granule_url(test_time)

    assert "gpm1.gesdisc.eosdis.nasa.gov" in url
    assert "2026/216" in url or "2026" in url
    assert "3B-HHR-L.GIS.IMERG.20260804-S140000" in url


def test_gpm_synthetic_fallback_extraction():
    """Verify GPM rainfall synthetic grid generation and coordinate metadata."""
    fetcher = GPMFetcher()
    bbox = (6.50, 38.00, 6.70, 38.20)
    dataset = fetcher._generate_synthetic_grid(bbox)

    assert isinstance(dataset, xr.Dataset)
    assert "rain_rate_mm_hr" in dataset.data_vars
    assert "latitude" in dataset.coords
    assert "longitude" in dataset.coords
    assert np.all(dataset["rain_rate_mm_hr"].values >= 0.0)


def test_dem_slope_computation():
    """Verify slope gradient computation on a known 45-degree planar incline elevation matrix."""
    fetcher = DEMFetcher(cell_size_m=1.0)
    
    # Create a 5x5 elevation grid with dz/dx = 1.0 (45-degree incline)
    x = np.arange(5, dtype=float)
    y = np.arange(5, dtype=float)
    xx, _ = np.meshgrid(x, y)
    elevation = xx * 1.0  # Elevation increases 1 meter per 1 meter horizontal distance

    slope = fetcher.compute_slope(elevation, cell_size_m=1.0)

    # Interior cells (excluding boundaries due to gradient edge effects) should equal 45 degrees
    interior_slope = slope[1:-1, 1:-1]
    assert np.allclose(interior_slope, 45.0, atol=1e-2)


def test_ingestion_pipeline_alignment():
    """Verify that the ingestion pipeline outputs aligned variables with matching grid shapes."""
    bbox = (6.50, 38.00, 6.80, 38.30)
    pipeline = IngestionPipeline()

    unified_ds = pipeline.run(bbox=bbox)

    assert isinstance(unified_ds, xr.Dataset)
    assert "rain_rate_mm_hr" in unified_ds.data_vars
    assert "elevation" in unified_ds.data_vars
    assert "slope_degrees" in unified_ds.data_vars

    rain_shape = unified_ds["rain_rate_mm_hr"].shape
    elev_shape = unified_ds["elevation"].shape
    slope_shape = unified_ds["slope_degrees"].shape

    # Shapes must match across all variables
    assert rain_shape == elev_shape == slope_shape
    assert np.isnan(unified_ds["rain_rate_mm_hr"].values).sum() == 0
