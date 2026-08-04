/**
 * HydroPulse PWA Web Application Controller
 * Handles Leaflet map rendering, low-bandwidth risk data ingestion,
 * offline caching interaction, and detail drawer updates.
 */

document.addEventListener("DOMContentLoaded", () => {
  const DEFAULT_LAT = 6.65;
  const DEFAULT_LON = 38.25;
  const DEFAULT_ZOOM = 10;

  // Color mapping based on risk level
  const RISK_COLORS = {
    LOW: "#22c55e",
    MODERATE: "#eab308",
    HIGH: "#f97316",
    SEVERE: "#ef4444",
  };

  // Initialize Leaflet Map
  const map = L.map("map", {
    zoomControl: true,
    attributionControl: false,
  }).setView([DEFAULT_LAT, DEFAULT_LON], DEFAULT_ZOOM);

  // High-contrast dark basemap tiles (OpenStreetMap fallback)
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
  }).addTo(map);

  let gridLayerGroup = L.layerGroup().addTo(map);

  // Network connection monitor
  const networkBadge = document.getElementById("network-badge");
  function updateNetworkStatus() {
    if (navigator.onLine) {
      networkBadge.textContent = "Online";
      networkBadge.className = "badge";
    } else {
      networkBadge.textContent = "Offline";
      networkBadge.className = "badge offline";
    }
  }

  window.addEventListener("online", updateNetworkStatus);
  window.addEventListener("offline", updateNetworkStatus);
  updateNetworkStatus();

  // Fetch Risk Data from API Endpoint
  async function fetchRiskData() {
    try {
      const response = await fetch("/api/v1/risk-data");
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data = await response.json();
      renderRiskGrid(data);
    } catch (err) {
      console.warn("Using offline cached or fallback data:", err);
    }
  }

  // Render Grid Points as Color-Coded Polygons / Circles
  function renderRiskGrid(payload) {
    gridLayerGroup.clearLayers();

    if (!payload || !payload.spatial_grid) return;

    const grid = payload.spatial_grid;
    const bounds = payload.location_bounds;

    if (bounds) {
      map.fitBounds([
        [bounds.min_latitude, bounds.min_longitude],
        [bounds.max_latitude, bounds.max_longitude],
      ]);
    }

    grid.forEach((point) => {
      const color = RISK_COLORS[point.calculated_risk_level] || "#94a3b8";

      // Render grid cell as a distinct circle marker
      const circle = L.circleMarker([point.lat, point.lon], {
        radius: 12,
        fillColor: color,
        color: "#ffffff",
        weight: 1.5,
        opacity: 0.9,
        fillOpacity: 0.75,
      });

      circle.on("click", () => {
        updateDetailDrawer(point, payload.timestamp);
      });

      circle.addTo(gridLayerGroup);
    });

    // Auto-select first point for initial display
    if (grid.length > 0) {
      updateDetailDrawer(grid[0], payload.timestamp);
    }
  }

  // Update Detail Drawer UI Panel
  function updateDetailDrawer(point, timestamp) {
    document.getElementById("cell-location").textContent = `Lat: ${point.lat}, Lon: ${point.lon}`;
    document.getElementById("val-rain").innerHTML = `${point.rain_rate_mm_hr} <small>mm/hr</small>`;
    document.getElementById("val-slope").innerHTML = `${point.slope_degrees} <small>°</small>`;
    document.getElementById("val-time-to-peak").innerHTML = `${point.estimated_time_to_peak_hours} <small>hrs</small>`;
    document.getElementById("val-timestamp").textContent = timestamp ? timestamp.slice(11, 19) + " UTC" : "--";

    const badge = document.getElementById("cell-risk-badge");
    badge.textContent = point.calculated_risk_level;
    badge.className = `risk-badge badge-${point.calculated_risk_level.toLowerCase()}`;
  }

  // Refresh Sync Button Handler
  document.getElementById("refresh-btn").addEventListener("click", fetchRiskData);

  // Initial Data Fetch
  fetchRiskData();

  // Register PWA Service Worker
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker
      .register("/static/service-worker.js")
      .then((reg) => console.log("ServiceWorker registered successfully:", reg.scope))
      .catch((err) => console.warn("ServiceWorker registration failed:", err));
  }
});
