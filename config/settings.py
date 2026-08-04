"""
Configuration settings for the HydroPulse ingestion and processing pipeline.
Handles environment variables, API endpoints, bounding boxes, and cache paths.
"""

import os
from pathlib import Path
from typing import Tuple


class Settings:
    """Application configuration and environment settings."""

    # Earthdata Authentication
    EARTHDATA_USERNAME: str = os.getenv("EARTHDATA_USERNAME", "")
    EARTHDATA_PASSWORD: str = os.getenv("EARTHDATA_PASSWORD", "")
    EARTHDATA_TOKEN: str = os.getenv("EARTHDATA_TOKEN", "")

    # Endpoints
    GPM_BASE_URL: str = os.getenv(
        "GPM_BASE_URL",
        "https://gpm1.gesdisc.eosdis.nasa.gov/data/GPM_L3/GPM_3IMERGHH.07",
    )
    COPERNICUS_STAC_URL: str = os.getenv(
        "COPERNICUS_STAC_URL",
        "https://earth-search.aws.element84.com/v1",
    )

    # Spatial Bounds: (min_lat, min_lon, max_lat, max_lon)
    DEFAULT_BBOX: Tuple[float, float, float, float] = (
        float(os.getenv("BBOX_MIN_LAT", "6.50")),
        float(os.getenv("BBOX_MIN_LON", "38.00")),
        float(os.getenv("BBOX_MAX_LAT", "7.00")),
        float(os.getenv("BBOX_MAX_LON", "38.50")),
    )

    # Resolution settings
    GPM_SPATIAL_RES_DEG: float = 0.1
    DEM_SPATIAL_RES_M: float = 30.0

    # Storage Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    CACHE_DIR: Path = DATA_DIR / "raw"
    PROCESSED_DIR: Path = DATA_DIR / "processed"

    @classmethod
    def ensure_directories(cls) -> None:
        """Ensure all required local directories exist."""
        cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cls.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
