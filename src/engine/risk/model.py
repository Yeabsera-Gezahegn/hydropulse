"""
Hydrological Risk Engine Module.
Calculates Topographic Wetness Index (TWI), Manning's runoff velocity,
and composite flash-flood and landslide risk scores.
"""

import logging
import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)


class RiskEngine:
    """Computes physics-informed hydrological risk metrics on aligned spatial grids."""

    def __init__(
        self,
        manning_n: float = 0.04,
        cell_size_m: float = 30.0,
    ) -> None:
        self.manning_n = manning_n
        self.cell_size_m = cell_size_m

    def compute_twi(
        self, slope_deg: np.ndarray, elevation: np.ndarray
    ) -> np.ndarray:
        """
        Compute Topographic Wetness Index (TWI) = ln(As / tan(slope)).
        
        Args:
            slope_deg: 2D array of slope values in degrees.
            elevation: 2D array of elevation values in meters.

        Returns:
            2D array of TWI values.
        """
        slope_rad = np.radians(np.maximum(slope_deg, 0.1))
        tan_slope = np.tan(slope_rad)

        # Approximate upslope contributing area As based on elevation accumulation
        elev_min = np.min(elevation)
        elev_range = np.maximum(np.ptp(elevation), 1.0)
        elev_norm = (elevation - elev_min) / elev_range
        
        # Specific contributing area As (m^2 / m)
        as_area = self.cell_size_m * (1.0 + 10.0 * (1.0 - elev_norm))

        twi = np.log(as_area / tan_slope)
        return np.clip(twi, a_min=0.0, a_max=25.0)

    def compute_runoff_velocity(
        self, rain_rate_mm_hr: np.ndarray, slope_deg: np.ndarray
    ) -> np.ndarray:
        """
        Estimate runoff flow velocity (m/s) using Manning's equation:
        V = (1/n) * Rh^(2/3) * S^(1/2)

        Args:
            rain_rate_mm_hr: 2D array of rainfall intensity in mm/hr.
            slope_deg: 2D array of slope angles in degrees.

        Returns:
            2D array of runoff velocities in m/s.
        """
        slope_rad = np.radians(np.maximum(slope_deg, 0.05))
        slope_sine = np.sin(slope_rad)

        # Convert rain rate from mm/hr to hydraulic depth estimate Rh (meters)
        rain_m_s = (rain_rate_mm_hr / 1000.0) / 3600.0
        hydraulic_radius = np.maximum(rain_m_s * 3600.0 * 0.01, 1e-4)

        velocity = (1.0 / self.manning_n) * (hydraulic_radius ** (2.0 / 3.0)) * (slope_sine ** 0.5)
        return np.clip(velocity, a_min=0.01, a_max=15.0)

    def calculate_risk_score(self, dataset: xr.Dataset) -> xr.Dataset:
        """
        Calculate composite risk index score (0.0 to 1.0) combining rainfall, slope, and TWI.

        Args:
            dataset: Aligned xarray.Dataset containing 'rain_rate_mm_hr', 'slope_degrees', 'elevation'.

        Returns:
            xarray.Dataset augmented with 'twi', 'runoff_velocity_m_s', and 'risk_score'.
        """
        rain = dataset["rain_rate_mm_hr"].values
        slope = dataset["slope_degrees"].values
        elevation = dataset["elevation"].values

        twi = self.compute_twi(slope, elevation)
        velocity = self.compute_runoff_velocity(rain, slope)

        # Normalized risk components
        rain_component = np.clip(rain / 50.0, 0.0, 1.0)
        slope_component = np.clip(slope / 45.0, 0.0, 1.0)
        twi_component = np.clip(twi / 12.0, 0.0, 1.0)

        # Weighted composite risk index (0.0 to 1.0)
        composite_risk = (
            0.50 * rain_component
            + 0.35 * slope_component
            + 0.15 * twi_component
        )
        composite_risk = np.clip(composite_risk, 0.0, 1.0)

        result_ds = dataset.copy()
        result_ds["twi"] = (("latitude", "longitude"), twi)
        result_ds["runoff_velocity_m_s"] = (("latitude", "longitude"), velocity)
        result_ds["risk_score"] = (("latitude", "longitude"), composite_risk)

        return result_ds
