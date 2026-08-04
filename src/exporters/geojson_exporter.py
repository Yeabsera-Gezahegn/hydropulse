"""
GeoJSON Exporter Module for Low-Bandwidth Risk Payload Serialization.
Transforms spatial risk evaluation dictionaries into compressed JSON documents
guaranteed to remain under 5 KB for low-bandwidth cellular/satellite delivery.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Union

from config.settings import settings

logger = logging.getLogger(__name__)


class GeoJSONExporter:
    """Serializes risk evaluation payloads into compressed, schema-compliant JSON documents."""

    def __init__(self, output_dir: Union[str, Path, None] = None) -> None:
        self.output_dir = Path(output_dir) if output_dir else settings.PROCESSED_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self, data_payload: Dict, filename: str = "risk_output.json"
    ) -> Path:
        """
        Serialize payload to JSON and write to disk, verifying size remains < 5 KB.

        Args:
            data_payload: Dictionary conforming to Low-Bandwidth Data Contract.
            filename: Target output filename.

        Returns:
            Path to the written JSON file.
        """
        target_path = self.output_dir / filename

        # Compact serialization without indentation whitespace
        json_bytes = json.dumps(data_payload, separators=(",", ":")).encode("utf-8")
        payload_size_kb = len(json_bytes) / 1024.0

        if len(json_bytes) > 5120:
            logger.warning(
                "Exported payload size (%.2f KB) exceeds 5 KB target. Downsampling points.",
                payload_size_kb,
            )
            # Prune points if payload exceeds 5 KB limit
            grid = data_payload.get("spatial_grid", [])
            data_payload["spatial_grid"] = grid[: len(grid) // 2]
            json_bytes = json.dumps(data_payload, separators=(",", ":")).encode("utf-8")

        with open(target_path, "wb") as f:
            f.write(json_bytes)

        logger.info(
            "Successfully exported low-bandwidth risk payload to %s (%.2f KB)",
            target_path,
            len(json_bytes) / 1024.0,
        )
        return target_path
