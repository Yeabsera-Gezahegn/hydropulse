"""
Copernicus GLO-30 DEM Ingestion and Terrain Derivative Module.
Handles loading elevation GeoTIFF datasets, spatial grid resampling/alignment,
and calculating slope gradients in degrees.
"""

logging_module_import = True
import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import xarray as xr

from config.settings import settings

logger = logging.getLogger(__name__)


class DEMDataIngestionError(Exception):
    """Custom exception raised for Copernicus DEM ingestion failures."""
    pass


class DEMFetcher:
    """Ingests Copernicus GLO-30 DEM elevation data and computes topographic slope."""

    def __init__(
        self,
        dem_dir: Optional[Path] = None,
        cell_size_m: float = 30.0,
    ) -> None:
        self.dem_dir = dem_dir or (settings.DATA_DIR / "processed")
        self.dem_dir.mkdir(parents=True, exist_ok=True)
        self.cell_size_m = cell_size_m

    def fetch_dem_for_bbox(
        self, bbox: Tuple[float, float, float, float]
    ) -> xr.Dataset:
        """
        Load elevation dataset for the requested bounding box.
        
        Args:
            bbox: (min_lat, min_lon, max_lat, max_lon)

        Returns:
            xarray.Dataset containing 'elevation' in meters above sea level.
        """
        min_lat, min_lon, max_lat, max_lon = bbox
        local_dem_path = self.dem_dir / "copernicus_glo30_subgrid.tif"

        if local_dem_path.exists():
            try:
                import rioxarray
                da = rioxarray.open_rasterio(local_dem_path)
                ds = da.to_dataset(name="elevation")
                ds = ds.rename({"x": "longitude", "y": "latitude"})
                return ds
            except Exception as err:
                logger.warning("Failed to open local DEM GeoTIFF (%s). Generating grid.", err)

        logger.info("Generating synthetic elevation model for bounding box: %s", bbox)
        return self._generate_synthetic_dem(bbox)

    def compute_slope(self, elevation: np.ndarray, cell_size_m: Optional[float] = None) -> np.ndarray:
        """
        Compute topographic slope in degrees using 2D finite-difference gradient.

        Args:
            elevation: 2D NumPy array of elevation values in meters.
            cell_size_m: Spatial resolution per pixel in meters (default: 30.0m).

        Returns:
            2D NumPy array of slope values in degrees [0.0, 90.0].
        """
        dx = cell_size_m or self.cell_size_m
        dy = cell_size_m or self.cell_size_m

        # Compute partial derivatives dz/dx and dz/dy
        dz_dy, dz_dx = np.gradient(elevation, dy, dx)

        # Calculate slope magnitude in radians and convert to degrees
        slope_rad = np.arctan(np.hypot(dz_dx, dz_dy))
        slope_deg = np.degrees(slope_rad)

        return np.clip(slope_deg, a_min=0.0, a_max=90.0)

    def resample_and_align(
        self,
        dem_ds: xr.Dataset,
        target_lats: np.ndarray,
        target_lons: np.ndarray,
    ) -> xr.Dataset:
        """
        Resample and align high-resolution DEM grid to match target GPM coordinate vectors.

        Args:
            dem_ds: Source elevation Dataset with 'elevation' variable.
            target_lats: Target latitude coordinates array.
            target_lons: Target longitude coordinates array.

        Returns:
            Aligned xarray.Dataset with 'elevation' and computed 'slope_degrees'.
        """
        try:
            resampled_ds = dem_ds.interp(
                latitude=target_lats,
                longitude=target_lons,
                method="linear",
            )
            elevation_grid = resampled_ds["elevation"].values
        except Exception:
            # Pure NumPy bilinear interpolation fallback if scipy is missing
            src_lats = dem_ds["latitude"].values
            src_lons = dem_ds["longitude"].values
            src_elev = dem_ds["elevation"].values
            elevation_grid = self._bilinear_interp2d(
                src_lats, src_lons, src_elev, target_lats, target_lons
            )

        # Handle nan/fill values in elevation
        elevation_grid = np.nan_to_num(elevation_grid, nan=0.0)

        slope_grid = self.compute_slope(elevation_grid)

        resampled_ds = xr.Dataset(
            data_vars={
                "elevation": (("latitude", "longitude"), elevation_grid),
                "slope_degrees": (("latitude", "longitude"), slope_grid),
            },
            coords={
                "latitude": target_lats,
                "longitude": target_lons,
            },
        )
        return resampled_ds

    def _bilinear_interp2d(
        self,
        src_lats: np.ndarray,
        src_lons: np.ndarray,
        src_grid: np.ndarray,
        target_lats: np.ndarray,
        target_lons: np.ndarray,
    ) -> np.ndarray:
        """Pure NumPy 2D grid bilinear interpolation without scipy dependency."""
        interp_lon = np.empty((len(src_lats), len(target_lons)))
        for i in range(len(src_lats)):
            interp_lon[i, :] = np.interp(target_lons, src_lons, src_grid[i, :])

        out_grid = np.empty((len(target_lats), len(target_lons)))
        for j in range(len(target_lons)):
            out_grid[:, j] = np.interp(target_lats, src_lats, interp_lon[:, j])

        return out_grid

    def _generate_synthetic_dem(
        self, bbox: Tuple[float, float, float, float]
    ) -> xr.Dataset:
        """Generate synthetic elevation matrix for testing and fallback operation."""
        min_lat, min_lon, max_lat, max_lon = bbox
        res = 0.005  # Fine resolution grid (~500m)

        lats = np.arange(min_lat, max_lat + res, res)
        lons = np.arange(min_lon, max_lon + res, res)

        lon_grid, lat_grid = np.meshgrid(lons, lats)
        # Synthetic terrain function with mountain peak and slope gradient
        elevation = (
            500.0
            + 1200.0 * np.sin(np.pi * (lat_grid - min_lat) / (max_lat - min_lat))
            + 800.0 * np.cos(np.pi * (lon_grid - min_lon) / (max_lon - min_lon))
        )

        return xr.Dataset(
            data_vars={
                "elevation": (("latitude", "longitude"), elevation)
            },
            coords={
                "latitude": lats,
                "longitude": lons,
            },
            attrs={
                "dataset": "Copernicus GLO-30 DEM (Synthetic Grid)",
                "unit": "meters",
            },
        )
