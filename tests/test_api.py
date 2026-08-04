"""
End-to-end API integration tests for the HydroPulse WSGI web service.
Verifies HTTP endpoint responses, contract schema validity, and Gzip compression headers.
"""

import gzip
import io
import json
import pytest

from src.api.app import app


def make_wsgi_request(path: str, accept_encoding: str = "") -> tuple:
    """Helper to test WSGI application directly without launching a network socket."""
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8000",
        "HTTP_ACCEPT_ENCODING": accept_encoding,
        "wsgi.input": io.BytesIO(),
        "wsgi.errors": io.BytesIO(),
        "wsgi.version": (1, 0),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "wsgi.url_scheme": "http",
    }

    status_code = 0
    headers_dict = {}

    def start_response(status, response_headers, exc_info=None):
        nonlocal status_code, headers_dict
        status_code = int(status.split()[0])
        headers_dict = dict(response_headers)

    response_chunks = app(environ, start_response)
    body = b"".join(response_chunks)
    return status_code, headers_dict, body


def test_health_check_endpoint():
    """Verify that the health check endpoint returns 200 OK."""
    status, headers, body = make_wsgi_request("/health")
    assert status == 200
    assert headers["Content-Type"] == "application/json"
    data = json.loads(body.decode("utf-8"))
    assert data["status"] == "ok"
    assert data["system"] == "HydroPulse"


def test_risk_data_endpoint_contract():
    """Verify that /api/v1/risk-data returns 200 OK with schema-compliant payload."""
    status, headers, body = make_wsgi_request("/api/v1/risk-data")
    assert status == 200
    assert headers["Content-Type"] == "application/json"
    assert "X-HydroPulse-Payload-Size-Bytes" in headers

    data = json.loads(body.decode("utf-8"))
    assert "timestamp" in data
    assert "location_bounds" in data
    assert "spatial_grid" in data

    bounds = data["location_bounds"]
    assert "min_latitude" in bounds
    assert "max_latitude" in bounds
    assert "min_longitude" in bounds
    assert "max_longitude" in bounds

    grid = data["spatial_grid"]
    assert isinstance(grid, list)
    assert len(grid) > 0

    first_item = grid[0]
    assert "lat" in first_item
    assert "lon" in first_item
    assert "rain_rate_mm_hr" in first_item
    assert "slope_degrees" in first_item
    assert "calculated_risk_level" in first_item
    assert first_item["calculated_risk_level"] in ["LOW", "MODERATE", "HIGH", "SEVERE"]
    assert "estimated_time_to_peak_hours" in first_item


def test_risk_data_gzip_compression_header():
    """Verify that response headers support Gzip compression for low-bandwidth transfer."""
    status, headers, body = make_wsgi_request("/api/v1/risk-data", accept_encoding="gzip")
    assert status == 200
    assert headers.get("Content-Encoding") == "gzip"

    # Decompress body to verify validity
    decompressed = gzip.decompress(body)
    data = json.loads(decompressed.decode("utf-8"))
    assert "spatial_grid" in data
