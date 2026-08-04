"""
Risk Classifier and Time-to-Peak Estimator Module.
Classifies continuous risk scores into discrete threat levels [LOW, MODERATE, HIGH, SEVERE]
and calculates estimated runoff time to peak hydrograph surge.
"""

from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)


class RiskClassifier:
    """Classifies risk scores and estimates peak hydrograph arrival times."""

    def __init__(self, default_flow_distance_m: float = 5000.0) -> None:
        self.default_flow_distance_m = default_flow_distance_m

    @staticmethod
    def classify_risk_level(risk_score: float) -> str:
        """
        Map a continuous risk score [0.0, 1.0] to a threat category string.
        """
        if risk_score >= 0.75:
            return "SEVERE"
        elif risk_score >= 0.50:
            return "HIGH"
        elif risk_score >= 0.25:
            return "MODERATE"
        else:
            return "LOW"

    def calculate_time_to_peak(
        self, velocity_m_s: float, flow_distance_m: Optional[float] = None
    ) -> float:
        """
        Calculate estimated hours to peak hydrograph surge based on runoff velocity.
        """
        distance = flow_distance_m or self.default_flow_distance_m
        vel = max(velocity_m_s, 0.01)
        time_seconds = distance / vel
        time_hours = time_seconds / 3600.0
        return float(np.clip(time_hours, 0.1, 48.0))

    def process_dataset(
        self, dataset: xr.Dataset, max_grid_points: int = 40
    ) -> Dict:
        """
        Transform risk-calculated Dataset into a structured dictionary ready for GeoJSON exporter.

        Args:
            dataset: xarray.Dataset containing 'rain_rate_mm_hr', 'slope_degrees',
                     'runoff_velocity_m_s', and 'risk_score'.
            max_grid_points: Max grid samples to include for payload compression (< 5 KB).

        Returns:
            Dictionary matching the HydroPulse Low-Bandwidth Data Contract structure.
        """
        lats = dataset["latitude"].values
        lons = dataset["longitude"].values

        min_lat = float(np.min(lats))
        max_lat = float(np.max(lats))
        min_lon = float(np.min(lons))
        max_lon = float(np.max(lons))

        # Flatten grid points
        lat_mesh, lon_mesh = np.meshgrid(lats, lons, indexing="ij")
        flat_lats = lat_mesh.flatten()
        flat_lons = lon_mesh.flatten()
        flat_rain = dataset["rain_rate_mm_hr"].values.flatten()
        flat_slope = dataset["slope_degrees"].values.flatten()
        flat_vel = dataset["runoff_velocity_m_s"].values.flatten()
        flat_risk = dataset["risk_score"].values.flatten()

        total_points = len(flat_risk)
        step = max(1, total_points // max_grid_points)

        spatial_grid: List[Dict] = []
        for idx in range(0, total_points, step):
            if len(spatial_grid) >= max_grid_points:
                break

            r_score = float(flat_risk[idx])
            risk_cat = self.classify_risk_level(r_score)
            time_peak = self.calculate_time_to_peak(float(flat_vel[idx]))

            spatial_grid.append({
                "lat": round(float(flat_lats[idx]), 4),
                "lon": round(float(flat_lons[idx]), 4),
                "rain_rate_mm_hr": round(float(flat_rain[idx]), 2),
                "slope_degrees": round(float(flat_slope[idx]), 2),
                "calculated_risk_level": risk_cat,
                "estimated_time_to_peak_hours": round(time_peak, 1),
            })

        timestamp_str = dataset.attrs.get(
            "timestamp", datetime.now(timezone.utc).isoformat()
        )

        return {
            "timestamp": timestamp_str,
            "location_bounds": {
                "min_latitude": round(min_lat, 4),
                "max_latitude": round(max_lat, 4),
                "min_longitude": round(min_lon, 4),
                "max_longitude": round(max_lon, 4),
            },
            "spatial_grid": spatial_grid,
        }
