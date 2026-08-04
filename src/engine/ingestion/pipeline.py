"""
Satellite and Elevation Data Ingestion Pipeline Orchestrator.
Orchestrates GPM IMERG rainfall retrieval, Copernicus DEM terrain fetching,
spatial coordinate alignment, and missing value processing.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import xarray as xr

from config.settings import settings
from src.engine.ingestion.dem_fetcher import DEMFetcher
from src.engine.ingestion.gpm_fetcher import GPMFetcher

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Orchestrates NASA GPM and Copernicus DEM data ingestion into a unified hydro grid."""

    def __init__(
        self,
        gpm_fetcher: Optional[GPMFetcher] = None,
        dem_fetcher: Optional[DEMFetcher] = None,
    ) -> None:
        self.gpm_fetcher = gpm_fetcher or GPMFetcher()
        self.dem_fetcher = dem_fetcher or DEMFetcher()

    def run(
        self,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        target_time: Optional[datetime] = None,
    ) -> xr.Dataset:
        """
        Execute the end-to-end data ingestion, alignment, and cleaning pipeline.

        Args:
            bbox: (min_lat, min_lon, max_lat, max_lon) bounding box.
            target_time: Target UTC datetime for GPM rainfall evaluation.

        Returns:
            Unified xarray.Dataset containing aligned 'rain_rate_mm_hr',
            'elevation', and 'slope_degrees'.
        """
        target_bbox = bbox or settings.DEFAULT_BBOX
        eval_time = target_time or datetime.now(timezone.utc)

        logger.info(
            "Starting ingestion pipeline for bbox=%s at time=%s",
            target_bbox,
            eval_time.isoformat(),
        )

        # 1. Fetch NASA GPM IMERG precipitation data
        try:
            granule_path = self.gpm_fetcher.fetch_granule(timestamp=eval_time)
            gpm_ds = self.gpm_fetcher.extract_precipitation(granule_path, bbox=target_bbox)
        except Exception as err:
            logger.warning("GPM fetch encountered issue (%s). Using fallback grid.", err)
            gpm_ds = self.gpm_fetcher._generate_synthetic_grid(bbox=target_bbox)

        # 2. Handle missing or NaN precipitation values
        gpm_ds["rain_rate_mm_hr"] = gpm_ds["rain_rate_mm_hr"].fillna(0.0)
        gpm_ds["rain_rate_mm_hr"] = xr.where(
            gpm_ds["rain_rate_mm_hr"] < 0, 0.0, gpm_ds["rain_rate_mm_hr"]
        )

        # 3. Fetch Copernicus GLO-30 DEM elevation data
        raw_dem_ds = self.dem_fetcher.fetch_dem_for_bbox(bbox=target_bbox)

        # 4. Resample and align DEM elevation and slope to GPM grid coordinates
        target_lats = gpm_ds["latitude"].values
        target_lons = gpm_ds["longitude"].values

        aligned_dem_ds = self.dem_fetcher.resample_and_align(
            dem_ds=raw_dem_ds,
            target_lats=target_lats,
            target_lons=target_lons,
        )

        # 5. Merge into a unified Dataset
        unified_ds = xr.Dataset(
            data_vars={
                "rain_rate_mm_hr": gpm_ds["rain_rate_mm_hr"],
                "elevation": aligned_dem_ds["elevation"],
                "slope_degrees": aligned_dem_ds["slope_degrees"],
            },
            coords={
                "latitude": gpm_ds["latitude"],
                "longitude": gpm_ds["longitude"],
            },
            attrs={
                "title": "HydroPulse Aligned Ingestion Grid",
                "timestamp": eval_time.isoformat(),
                "bbox": list(target_bbox),
            },
        )

        logger.info("Ingestion pipeline successfully generated unified grid.")
        return unified_ds


def main() -> None:
    """CLI execution entrypoint for testing the pipeline."""
    logging.basicConfig(level=logging.INFO)
    pipeline = IngestionPipeline()
    dataset = pipeline.run()
    print("Pipeline Execution Output:")
    print(dataset)


if __name__ == "__main__":
    main()
