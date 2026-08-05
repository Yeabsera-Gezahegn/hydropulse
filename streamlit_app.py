import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import pycountry
import geonamescache
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
    rainfall_rate: float,
    slope_pct: float,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 303)
    slope_deg = slope_pct_to_degrees(slope_pct)
    periods = pd.date_range("2026-08-01", periods=forecast_hours, freq="h")
    phase = abs(center_lat + center_lon) % (2 * np.pi)

    rainfall = rainfall_rate * (
        0.55 + 0.45 * np.sin(np.linspace(0, 2 * np.pi, forecast_hours) + phase)
    ) + rng.normal(0, rainfall_rate * 0.08, forecast_hours)
    discharge = (
        4.0
        + (rainfall_rate * 0.9)
        + 12.0 * np.maximum(0, np.sin(np.linspace(-0.4, 2.4 * np.pi, forecast_hours) + phase))
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
            "label": timestamp.strftime("%H:%M"),
            "rainfall_mm_hr": round(rain_val, 2),
            "runoff_m3_s": round(runoff_val, 2),
            "water_level_m": round(compute_water_level(rain_val, risk_score, center_lat, seed + idx), 2),
            "risk_index": round(risk_score, 3),
            "alert_status": alert_status,
        })

    return pd.DataFrame(rows)


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


# --- SIDEBAR ---
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

location_rng_seed = location_seed(map_latitude, map_longitude)
location_defaults = np.random.default_rng(location_rng_seed)
location_id = f"{map_latitude:.4f}_{map_longitude:.4f}"

selected_risk = st.sidebar.multiselect(
    "Risk Level Filter",
    RISK_LEVELS,
    default=RISK_LEVELS,
)
rainfall_rate = st.sidebar.slider(
    "Rainfall (mm/hr)",
    min_value=0.0,
    max_value=50.0,
    value=float(round(8.0 + location_defaults.uniform(0, 18), 1)),
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

# --- LOCALIZED CALCULATIONS ---
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
    map_latitude,
    map_longitude,
    forecast_horizon,
    rainfall_rate,
    slope_gradient_pct,
    location_rng_seed,
)

active_risk_filter = selected_risk if selected_risk else RISK_LEVELS
spatial_filtered = spatial_full[spatial_full["risk_level"].isin(active_risk_filter)].copy()

# --- MAIN UI ---
st.title("🌊 HydroPulse")
st.subheader("Real-Time Flood & Risk Monitoring Dashboard")
st.markdown(
    f"Monitoring **{selected_city_name}, {selected_country}** "
    f"({map_latitude:.4f}°, {map_longitude:.4f}°)"
)

metric_cols = st.columns(5)
metric_cols[0].metric("Rainfall Rate", f"{rainfall_rate:.2f} mm/hr", selected_city_name)
metric_cols[1].metric("Slope Gradient", f"{slope_gradient_pct:.1f}%", "Topography")
metric_cols[2].metric("Water Level", f"{water_level:.2f} m", "Localized estimate")
metric_cols[3].metric("Risk Index", f"{risk_index:.0%}", active_risk_band)
metric_cols[4].metric("Time to Peak Surge", f"{time_to_peak:.1f} hrs", f"{forecast_horizon}h forecast")

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
    st.markdown("**Water Discharge vs. Rainfall Forecast**")
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
