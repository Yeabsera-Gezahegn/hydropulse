"""
Data Ingestion modules for NASA GPM and Copernicus DEM.
"""

from src.engine.ingestion.dem_fetcher import DEMFetcher
from src.engine.ingestion.gpm_fetcher import GPMFetcher
from src.engine.ingestion.pipeline import IngestionPipeline

__all__ = ["GPMFetcher", "DEMFetcher", "IngestionPipeline"]
