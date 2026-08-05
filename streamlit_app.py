import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import pycountry
import geonamescache
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests

st.set_page_config(
    page_title="HydroPulse | Hydrological Risk Analytics",
    layout="wide",
    page_icon="🌊",
)

RISK_LEVELS = ["Low", "Moderate", "High", "Critical"]

RISK_BANDS = {
    "Low": {"emoji": "🟢", "color": [34, 197, 94, 180], "min_score": 0.0},
    "Moderate": {"emoji": "🟡", "color": [234, 179, 8, 180], "min_score": 0.25},
    "High": {"emoji": "🟠", "color": [249, 115, 22, 180], "min_score": 0.50},
    "Critical": {"emoji": "🔴", "color": [239, 68, 68, 180], "min_score": 0.75},
}

TIER_FACTORS = {
    "Low": (0.12, 0.10),
    "Moderate": (0.40, 0.38),
    "High": (0.72, 0.65),
    "Critical": (1.05, 0.92),
}

# ---------------------------------------------------------------------------
# LIVE WEATHER — Open-Meteo API
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600)
def fetch_live_weather(lat: float, lon: float) -> dict:
    """
    Fetch current conditions and 72-hour hourly precipitation forecast from
    Open-Meteo.  Returns a dict with keys:
        precipitation_mm_hr, temperature_c, humidity_pct, wind_speed_kmh,
        hourly_precipitation (list[float], 72 values), live (bool)

    Falls back gracefully to None-filled values when offline or rate-limited.
    """
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=precipitation,rain,showers,temperature_2m,"
        "relative_humidity_2m,wind_speed_10m"
        "&hourly=precipitation,rain"
        "&forecast_days=3"
        "&timezone=auto"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        current = data.get("current", {})
        hourly = data.get("hourly", {})

        precip_current = current.get("precipitation", 0.0) or 0.0
        rain_current = current.get("rain", 0.0) or 0.0
        showers_current = current.get("showers", 0.0) or 0.0
        # total precipitation rate = sum of rain + showers + any other precip
        total_precip = precip_current + rain_current + showers_current

        hourly_precip_raw = hourly.get("precipitation", [])
        hourly_rain_raw = hourly.get("rain", [])
        # combine rain + precipitation for a robust hourly signal
        n = max(len(hourly_precip_raw), len(hourly_rain_raw))
        hourly_combined = []
        for i in range(n):
            p = hourly_precip_raw[i] if i < len(hourly_precip_raw) else 0.0
            r = hourly_rain_raw[i] if i < len(hourly_rain_raw) else 0.0
            hourly_combined.append(float((p or 0.0) + (r or 0.0)))

        # Ensure exactly 72 values — pad/truncate
        if len(hourly_combined) >= 72:
            hourly_combined = hourly_combined[:72]
        else:
            hourly_combined += [0.0] * (72 - len(hourly_combined))

        return {
            "precipitation_mm_hr": round(total_precip, 2),
            "temperature_c": round(current.get("temperature_2m", 0.0) or 0.0, 1),
            "humidity_pct": round(current.get("relative_humidity_2m", 0.0) or 0.0, 1),
            "wind_speed_kmh": round(current.get("wind_speed_10m", 0.0) or 0.0, 1),
            "hourly_precipitation": hourly_combined,
            "live": True,
        }

    except Exception:
        return {
            "precipitation_mm_hr": None,
            "temperature_c": None,
            "humidity_pct": None,
            "wind_speed_kmh": None,
            "hourly_precipitation": [0.0] * 72,
            "live": False,
        }


# ---------------------------------------------------------------------------
# CACHED HELPERS
# ---------------------------------------------------------------------------

@st.cache_data
def load_countries():
    return sorted(
        [(country.name, country.alpha_2) for country in pycountry.countries],
        key=lambda item: item[0],
    )


@st.cache_data
def load_cities():
    gc = geonamescache.GeonamesCache()
    return gc.get_cities()


# ---------------------------------------------------------------------------
# HYDROLOGY HELPERS
# ---------------------------------------------------------------------------

def location_seed(latitude: float, longitude: float) -> int:
    return int(abs(latitude * 1_000 + longitude * 1_000)) % (2**32)


def slope_pct_to_degrees(slope_pct: float) -> float:
    return float(np.degrees(np.arctan(max(slope_pct, 0.01) / 100.0)))


def classify_risk_level(risk_score: float) -> str:
    if risk_score >= RISK_BANDS["Critical"]["min_score"]:
        return "Critical"
    if risk_score >= RISK_BANDS["High"]["min_score"]:
        return "High"
    if risk_score >= RISK_BANDS["Moderate"]["min_score"]:
        return "Moderate"
    return "Low"


def compute_risk_score(rainfall_mm_hr: float, slope_deg: float) -> float:
    rain_component = np.clip(rainfall_mm_hr / 50.0, 0.0, 1.0)
    slope_component = np.clip(slope_deg / 45.0, 0.0, 1.0)
    twi_proxy = np.clip((rainfall_mm_hr / 30.0) * (slope_deg / 20.0), 0.0, 1.0)
    return float(np.clip(0.50 * rain_component + 0.35 * slope_component + 0.15 * twi_proxy, 0.0, 1.0))


def estimate_time_to_peak(rainfall_mm_hr: float, slope_deg: float) -> float:
    velocity = max(0.01, (rainfall_mm_hr / 100.0) * np.sin(np.radians(max(slope_deg, 0.5))))
    return float(np.clip(5000.0 / velocity / 3600.0, 0.1, 48.0))


def compute_water_level(rainfall_mm_hr: float, risk_score: float, latitude: float, seed: int) -> float:
    rng = np.random.default_rng(seed + 17)
    base = 1.5 + abs(latitude) * 0.05 + rng.uniform(0.0, 1.5)
    return float(base * (1.0 + risk_score * 0.9 + rainfall_mm_hr / 100.0))


def generate_spatial_grid(
    center_lat: float,
    center_lon: float,
    rainfall_rate: float,
    slope_pct: float,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 101)
    base_rain = max(rainfall_rate, 1.0)
    base_slope_pct = max(slope_pct, 1.0)
    rows = []

    anchor_offsets = [
        (-0.22, -0.22),
        (-0.22, 0.22),
        (0.22, -0.22),
        (0.22, 0.22),
    ]
    for tier, (dlat, dlon) in zip(RISK_LEVELS, anchor_offsets):
        rain_mult, slope_mult = TIER_FACTORS[tier]
        rain = base_rain * rain_mult
        slope_pct_local = min(base_slope_pct * slope_mult, 50.0)
        slope_deg = slope_pct_to_degrees(slope_pct_local)
        risk_score = compute_risk_score(rain, slope_deg)
        rows.append({
            "lat": center_lat + dlat,
            "lon": center_lon + dlon,
            "rain_rate_mm_hr": round(rain, 2),
            "slope_percent": round(slope_pct_local, 2),
            "elevation": round(180 + abs(center_lat) * 12 + rng.uniform(120, 900), 1),
            "risk_score": round(risk_score * 100, 1),
            "risk_level": classify_risk_level(risk_score),
            "time_to_peak_hrs": round(estimate_time_to_peak(rain, slope_deg), 1),
            "water_level_m": round(compute_water_level(rain, risk_score, center_lat, seed + len(rows)), 2),
        })

    lat_points = np.linspace(center_lat - 0.25, center_lat + 0.25, 6)
    lon_points = np.linspace(center_lon - 0.25, center_lon + 0.25, 6)
    for lat in lat_points:
        for lon in lon_points:
            rain = base_rain * rng.uniform(0.25, 1.15)
            slope_pct_local = min(base_slope_pct * rng.uniform(0.20, 1.10), 50.0)
            slope_deg = slope_pct_to_degrees(slope_pct_local)
            risk_score = compute_risk_score(rain, slope_deg)
            rows.append({
                "lat": round(float(lat + rng.uniform(-0.01, 0.01)), 5),
                "lon": round(float(lon + rng.uniform(-0.01, 0.01)), 5),
                "rain_rate_mm_hr": round(rain, 2),
                "slope_percent": round(slope_pct_local, 2),
                "elevation": round(180 + abs(center_lat) * 12 + rng.uniform(80, 950), 1),
                "risk_score": round(risk_score * 100, 1),
                "risk_level": classify_risk_level(risk_score),
                "time_to_peak_hrs": round(estimate_time_to_peak(rain, slope_deg), 1),
                "water_level_m": round(compute_water_level(rain, risk_score, center_lat, seed + len(rows)), 2),
            })

    return pd.DataFrame(rows).drop_duplicates(subset=["lat", "lon"], keep="first").reset_index(drop=True)


def generate_forecast_data(
    center_lat: float,
    center_lon: float,
    forecast_hours: int,
    slope_pct: float,
    seed: int,
    live_hourly_precip: list,
) -> pd.DataFrame:
    """
    Build the hydrograph DataFrame.

    When live_hourly_precip contains non-zero values (Open-Meteo feed is
    active), those values are used directly as the rainfall signal.
    Otherwise the function falls back to the location-seeded sine wave model.
    """
    rng = np.random.default_rng(seed + 303)
    slope_deg = slope_pct_to_degrees(slope_pct)
    periods = pd.date_range("now", periods=forecast_hours, freq="h", tz="UTC")

    # ---- rainfall array ----
    live_slice = live_hourly_precip[:forecast_hours]
    if any(v > 0.0 for v in live_slice):
        # Live feed: use directly, add tiny sensor noise
        rainfall = np.array(live_slice, dtype=float) + rng.normal(0, 0.05, forecast_hours)
    else:
        # Fallback: location-seeded sinusoidal model
        phase = abs(center_lat + center_lon) % (2 * np.pi)
        base_rate = max(np.mean(live_hourly_precip) if live_hourly_precip else 5.0, 1.0)
        rainfall = base_rate * (
            0.55 + 0.45 * np.sin(np.linspace(0, 2 * np.pi, forecast_hours) + phase)
        ) + rng.normal(0, base_rate * 0.08, forecast_hours)

    # ---- discharge (unit hydrograph convolution proxy) ----
    discharge = (
        4.0
        + (np.mean(np.clip(rainfall, 0, None)) * 0.9)
        + 12.0 * np.maximum(0, np.sin(np.linspace(-0.4, 2.4 * np.pi, forecast_hours)))
        + rng.normal(0, 1.2, forecast_hours)
    )

    rows = []
    for idx, (timestamp, rain, runoff) in enumerate(zip(periods, rainfall, discharge)):
        rain_val = float(np.clip(rain, 0, None))
        runoff_val = float(np.clip(runoff, 0, None))
        risk_score = compute_risk_score(rain_val, slope_deg)
        alert_status = classify_risk_level(risk_score)
        rows.append({
            "timestamp": timestamp,
            "hour_offset": idx,
            "label": f"T+{idx:02d}h",
            "rainfall_mm_hr": round(rain_val, 2),
            "runoff_m3_s": round(runoff_val, 2),
            "water_level_m": round(compute_water_level(rain_val, risk_score, center_lat, seed + idx), 2),
            "risk_index": round(risk_score, 3),
            "alert_status": alert_status,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# PLOTLY CHARTS
# ---------------------------------------------------------------------------

def build_dual_axis_hydrograph(hydro_df: pd.DataFrame) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=hydro_df["label"],
            y=hydro_df["rainfall_mm_hr"],
            name="Rainfall (mm/hr)",
            marker_color="rgba(59, 130, 246, 0.6)",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=hydro_df["label"],
            y=hydro_df["runoff_m3_s"],
            name="Runoff (m³/s)",
            mode="lines+markers",
            line=dict(color="rgba(239, 68, 68, 1)", width=3),
        ),
        secondary_y=True,
    )
    fig.update_layout(
        height=380,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    fig.update_xaxes(title_text="Forecast Hour")
    fig.update_yaxes(title_text="Rainfall (mm/hr)", secondary_y=False)
    fig.update_yaxes(title_text="Runoff (m³/s)", secondary_y=True)
    return fig


# ---------------------------------------------------------------------------
# EXPORT
# ---------------------------------------------------------------------------

def build_export_dataframe(
    country: str,
    city: str,
    latitude: float,
    longitude: float,
    forecast_df: pd.DataFrame,
    spatial_df: pd.DataFrame,
    forecast_hours: int,
) -> pd.DataFrame:
    forecast_export = forecast_df.copy()
    forecast_export.insert(0, "record_type", "forecast")
    forecast_export.insert(1, "country", country)
    forecast_export.insert(2, "city", city)
    forecast_export.insert(3, "latitude", latitude)
    forecast_export.insert(4, "longitude", longitude)
    forecast_export.insert(5, "forecast_horizon_hrs", forecast_hours)

    spatial_export = spatial_df.copy()
    spatial_export.insert(0, "record_type", "spatial_sensor")
    spatial_export.insert(1, "country", country)
    spatial_export.insert(2, "city", city)
    spatial_export.insert(3, "latitude", latitude)
    spatial_export.insert(4, "longitude", longitude)
    spatial_export.insert(5, "forecast_horizon_hrs", forecast_hours)
    spatial_export["alert_status"] = spatial_export["risk_level"]

    shared_columns = sorted(set(forecast_export.columns) | set(spatial_export.columns))
    return pd.concat(
        [forecast_export.reindex(columns=shared_columns), spatial_export.reindex(columns=shared_columns)],
        ignore_index=True,
    )


# ---------------------------------------------------------------------------
# ALERT SYSTEM
# ---------------------------------------------------------------------------

def render_alert_system(active_band: str, rainfall: float, slope_pct: float) -> None:
    st.subheader("Alert System")
    cols = st.columns(4)
    for col, (band, meta) in zip(cols, RISK_BANDS.items()):
        is_active = band == active_band
        border = f"3px solid {'#111827' if is_active else '#e5e7eb'}"
        background = "#f9fafb" if is_active else "#ffffff"
        col.markdown(
            f"""
            <div style="border:{border}; border-radius:8px; padding:12px; background:{background}; text-align:center;">
                <div style="font-size:1.5rem;">{meta['emoji']}</div>
                <div style="font-weight:700;">{band}</div>
                <div style="font-size:0.8rem; color:#6b7280;">≥ {meta['min_score']:.0%} risk index</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.caption(
        f"Active alert for {rainfall:.1f} mm/hr rainfall and {slope_pct:.1f}% slope gradient."
    )


# ===========================================================================
# SIDEBAR
# ===========================================================================
st.sidebar.header("Controls")

countries = load_countries()
country_names = [name for name, _ in countries]
country_name_to_code = {name: code for name, code in countries}

selected_country = st.sidebar.selectbox("Country", country_names)
country_code = country_name_to_code[selected_country]

all_cities = load_cities()
country_cities = sorted(
    [
        city
        for city in all_cities.values()
        if city.get("countrycode") == country_code and city.get("name")
    ],
    key=lambda city: city["name"],
)

if country_cities:
    city_names = [city["name"] for city in country_cities]
    selected_city_name = st.sidebar.selectbox("City", city_names)
    selected_city = next(city for city in country_cities if city["name"] == selected_city_name)
    map_latitude = float(selected_city["latitude"])
    map_longitude = float(selected_city["longitude"])
else:
    st.sidebar.warning("No major cities found for this country. Enter a location manually.")
    selected_city_name = st.sidebar.text_input("City Name", value=selected_country)
    map_latitude = st.sidebar.number_input("Latitude", value=6.50, format="%.4f")
    map_longitude = st.sidebar.number_input("Longitude", value=38.00, format="%.4f")

# ---- Live weather fetch ----
weather = fetch_live_weather(map_latitude, map_longitude)

location_rng_seed = location_seed(map_latitude, map_longitude)
location_defaults = np.random.default_rng(location_rng_seed)
location_id = f"{map_latitude:.4f}_{map_longitude:.4f}"

selected_risk = st.sidebar.multiselect(
    "Risk Level Filter",
    RISK_LEVELS,
    default=RISK_LEVELS,
)

# Rainfall slider: default from live feed when available, else location-seeded
live_precip = weather["precipitation_mm_hr"]
default_rainfall = (
    float(round(live_precip, 1))
    if live_precip is not None
    else float(round(8.0 + location_defaults.uniform(0, 18), 1))
)
rainfall_rate = st.sidebar.slider(
    "Rainfall (mm/hr)",
    min_value=0.0,
    max_value=50.0,
    value=min(default_rainfall, 50.0),
    step=0.1,
    key=f"rainfall_{location_id}",
)
slope_gradient_pct = st.sidebar.slider(
    "Slope Gradient (%)",
    min_value=0.0,
    max_value=50.0,
    value=float(round(4.0 + location_defaults.uniform(0, 16), 1)),
    step=0.1,
    key=f"slope_{location_id}",
)
forecast_horizon = st.sidebar.slider(
    "Forecast Horizon (Hours)",
    min_value=24,
    max_value=72,
    value=24,
    step=6,
)

# ===========================================================================
# CALCULATIONS
# ===========================================================================
slope_degrees = slope_pct_to_degrees(slope_gradient_pct)
risk_index = compute_risk_score(rainfall_rate, slope_degrees)
active_risk_band = classify_risk_level(risk_index)
water_level = compute_water_level(rainfall_rate, risk_index, map_latitude, location_rng_seed)
time_to_peak = estimate_time_to_peak(rainfall_rate, slope_degrees)

spatial_full = generate_spatial_grid(
    map_latitude,
    map_longitude,
    rainfall_rate,
    slope_gradient_pct,
    location_rng_seed,
)
forecast_df = generate_forecast_data(
    center_lat=map_latitude,
    center_lon=map_longitude,
    forecast_hours=forecast_horizon,
    slope_pct=slope_gradient_pct,
    seed=location_rng_seed,
    live_hourly_precip=weather["hourly_precipitation"],
)

active_risk_filter = selected_risk if selected_risk else RISK_LEVELS
spatial_filtered = spatial_full[spatial_full["risk_level"].isin(active_risk_filter)].copy()

# ===========================================================================
# MAIN UI
# ===========================================================================
st.title("🌊 HydroPulse")
st.subheader("Real-Time Flood & Risk Monitoring Dashboard")

# Live feed status indicator
if weather["live"]:
    st.markdown(
        "🟢 **Live Weather Feed (Open-Meteo API)** &nbsp;|&nbsp; "
        f"Monitoring **{selected_city_name}, {selected_country}** "
        f"({map_latitude:.4f}°, {map_longitude:.4f}°)",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        "🔴 **Offline / Fallback Mode** &nbsp;|&nbsp; "
        f"Monitoring **{selected_city_name}, {selected_country}** "
        f"({map_latitude:.4f}°, {map_longitude:.4f}°) — using location-seeded estimates",
        unsafe_allow_html=True,
    )

# ---- Top metric cards ----
metric_cols = st.columns(7)

# Precipitation (live)
metric_cols[0].metric(
    "☔ Precipitation",
    f"{weather['precipitation_mm_hr']:.2f} mm/hr" if weather["precipitation_mm_hr"] is not None else "N/A",
    "Live observed" if weather["live"] else "Offline",
)

# Temperature (live)
metric_cols[1].metric(
    "🌡️ Temperature",
    f"{weather['temperature_c']:.1f} °C" if weather["temperature_c"] is not None else "N/A",
    "Live observed" if weather["live"] else "Offline",
)

# Humidity (live)
metric_cols[2].metric(
    "💧 Humidity",
    f"{weather['humidity_pct']:.1f}%" if weather["humidity_pct"] is not None else "N/A",
    "Live observed" if weather["live"] else "Offline",
)

# Wind speed (live)
metric_cols[3].metric(
    "🌬️ Wind Speed",
    f"{weather['wind_speed_kmh']:.1f} km/h" if weather["wind_speed_kmh"] is not None else "N/A",
    "Live observed" if weather["live"] else "Offline",
)

# Derived hydrological metrics
metric_cols[4].metric("Water Level", f"{water_level:.2f} m", "Localized estimate")
metric_cols[5].metric("Risk Index", f"{risk_index:.0%}", active_risk_band)
metric_cols[6].metric("Time to Peak Surge", f"{time_to_peak:.1f} hrs", f"{forecast_horizon}h forecast")

st.divider()
render_alert_system(active_risk_band, rainfall_rate, slope_gradient_pct)
st.divider()

col_map, col_charts = st.columns([1.2, 1])

with col_map:
    st.subheader("Spatial Risk Map")
    st.caption(
        f"{len(spatial_filtered)} of {len(spatial_full)} sensor points shown within "
        f"±0.25° of {selected_city_name}"
    )

    map_display = spatial_filtered.copy()
    map_display["fill_color"] = map_display["risk_level"].map(
        lambda level: RISK_BANDS[level]["color"]
    )

    column_layer = pdk.Layer(
        "ColumnLayer",
        data=map_display,
        get_position="[lon, lat]",
        get_elevation="elevation",
        elevation_scale=10,
        radius=900,
        get_fill_color="fill_color",
        pickable=True,
        auto_highlight=True,
    )
    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_display,
        get_position="[lon, lat]",
        get_radius=700,
        get_fill_color="fill_color",
        pickable=True,
    )
    view_state = pdk.ViewState(
        latitude=map_latitude,
        longitude=map_longitude,
        zoom=9.5,
        pitch=45,
        bearing=15,
    )

    st.pydeck_chart(
        pdk.Deck(
            layers=[column_layer, scatter_layer],
            initial_view_state=view_state,
            tooltip={
                "html": (
                    "<b>{risk_level}</b><br/>"
                    "Risk Index: {risk_score}<br/>"
                    "Rain: {rain_rate_mm_hr} mm/hr<br/>"
                    "Slope: {slope_percent}%<br/>"
                    "Water Level: {water_level_m} m<br/>"
                    "Peak ETA: {time_to_peak_hrs} hrs"
                ),
                "style": {"backgroundColor": "steelblue", "color": "white"},
            },
        )
    )

with col_charts:
    st.subheader("Hydrograph & Risk Analytics")
    source_label = "72-hr Open-Meteo forecast" if weather["live"] else "Location-seeded model"
    st.markdown(f"**Water Discharge vs. Rainfall Forecast** — *{source_label}*")
    st.plotly_chart(build_dual_axis_hydrograph(forecast_df), use_container_width=True)

    st.markdown("**Regional Vulnerability Breakdown (%)**")
    breakdown_source = spatial_full if not selected_risk else spatial_filtered
    risk_counts = (
        breakdown_source["risk_level"]
        .value_counts(normalize=True)
        .reindex(RISK_LEVELS, fill_value=0)
        * 100
    )
    risk_breakdown = pd.DataFrame({"Percentage": risk_counts.round(1)})
    st.bar_chart(risk_breakdown)

st.divider()
st.subheader("Data Export")

if st.button("Prepare Data Export", type="primary"):
    st.session_state["export_df"] = build_export_dataframe(
        selected_country,
        selected_city_name,
        map_latitude,
        map_longitude,
        forecast_df,
        spatial_full,
        forecast_horizon,
    )
    st.session_state["export_location_id"] = location_id

if "export_df" in st.session_state:
    export_df = st.session_state["export_df"]
    st.caption(
        f"Prepared {len(export_df)} records "
        f"({forecast_horizon}-hour forecast + {len(spatial_full)} spatial sensors)."
    )
    st.download_button(
        label="Download Hydrological Dataset (CSV)",
        data=export_df.to_csv(index=False).encode("utf-8"),
        file_name=(
            f"hydropulse_{selected_city_name.lower().replace(' ', '_')}_"
            f"{forecast_horizon}h.csv"
        ),
        mime="text/csv",
    )
else:
    st.info("Click **Prepare Data Export** to generate a localized forecast and spatial risk dataset.")
