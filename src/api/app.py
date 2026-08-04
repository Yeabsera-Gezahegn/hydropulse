"""
Lightweight Web Interface Server for HydroPulse.
Serves compressed risk payloads and static PWA web assets using standard WSGI/HTTP interfaces.
"""

import gzip
import json
import logging
from pathlib import Path
from typing import Callable, Dict, List
from wsgiref.simple_server import make_server

from config.settings import settings

logger = logging.getLogger(__name__)

DATA_FILE_PATH = settings.PROCESSED_DIR / "risk_output.json"
WEB_DIR = settings.BASE_DIR / "src" / "web"


def _generate_fallback_payload() -> None:
    """Generate initial risk output payload if file is not found."""
    from src.engine.ingestion.pipeline import IngestionPipeline
    from src.engine.risk.classifier import RiskClassifier
    from src.engine.risk.model import RiskEngine
    from src.exporters.geojson_exporter import GeoJSONExporter

    pipeline = IngestionPipeline()
    engine = RiskEngine()
    classifier = RiskClassifier()
    exporter = GeoJSONExporter()

    aligned_ds = pipeline.run()
    risk_ds = engine.calculate_risk_score(aligned_ds)
    payload_dict = classifier.process_dataset(risk_ds)
    exporter.export(payload_dict)


def app(environ: Dict, start_response: Callable) -> List[bytes]:
    """
    Standard WSGI Web Application Entrypoint.
    Handles health checks, risk API endpoints, and static file serving.
    """
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    accept_encoding = environ.get("HTTP_ACCEPT_ENCODING", "")

    if method != "GET":
        start_response("405 Method Not Allowed", [("Content-Type", "text/plain")])
        return [b"Method Not Allowed"]

    # Health Check Endpoint
    if path == "/health":
        start_response("200 OK", [("Content-Type", "application/json")])
        return [json.dumps({"status": "ok", "system": "HydroPulse"}).encode("utf-8")]

    # Risk Data API Endpoint
    if path == "/api/v1/risk-data":
        if not DATA_FILE_PATH.exists():
            _generate_fallback_payload()

        try:
            with open(DATA_FILE_PATH, "rb") as f:
                raw_bytes = f.read()

            headers = [
                ("Content-Type", "application/json"),
                ("Cache-Control", "public, max-age=300"),
                ("X-HydroPulse-Payload-Size-Bytes", str(len(raw_bytes))),
            ]

            # Gzip compression if requested by client
            if "gzip" in accept_encoding.lower():
                compressed_bytes = gzip.compress(raw_bytes)
                headers.append(("Content-Encoding", "gzip"))
                start_response("200 OK", headers)
                return [compressed_bytes]

            start_response("200 OK", headers)
            return [raw_bytes]

        except Exception as err:
            logger.error("Failed to read risk payload: %s", err)
            start_response("500 Internal Server Error", [("Content-Type", "application/json")])
            return [json.dumps({"error": "Internal data retrieval error"}).encode("utf-8")]

    # Serve static assets
    if path == "/" or path.startswith("/static/"):
        rel_path = path.lstrip("/")
        if rel_path == "" or rel_path == "static":
            target_file = WEB_DIR / "index.html"
        else:
            clean_rel = rel_path.replace("static/", "", 1) if rel_path.startswith("static/") else rel_path
            target_file = WEB_DIR / clean_rel

        if target_file.exists() and target_file.is_file():
            content_type = "text/html"
            if target_file.suffix == ".css":
                content_type = "text/css"
            elif target_file.suffix == ".js":
                content_type = "application/javascript"
            elif target_file.suffix == ".json":
                content_type = "application/json"

            with open(target_file, "rb") as f:
                content = f.read()

            start_response("200 OK", [("Content-Type", content_type)])
            return [content]

    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"Not Found"]


def run_server(port: int = 8000) -> None:
    """Run local WSGI development server."""
    with make_server("", port, app) as httpd:
        logger.info("Serving HydroPulse Web Interface on http://localhost:%d", port)
        httpd.serve_forever()


if __name__ == "__main__":
    run_server()
