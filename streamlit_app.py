import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import pycountry
import geonamescache
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- PAGE SETUP ---
st.set_page_config(
    page_title="HydroPulse | Hydrological Risk Analytics",
    layout="wide",
    page_icon="🌊",
)

RISK_BANDS = {
    "Low": {"emoji": "🟢", "color": [34, 197, 94, 180], "min_score": 0.0},
    "Moderate": {"emoji": "🟡", "color": [234, 179, 8, 180], "min_score": 0.25},
    "High": {"emoji": "🟠", "color": [249, 115, 22, 180], "min_score": 0.50},
    "Severe": {"emoji": "🔴", "color": [239, 68, 68, 180], "min_score": 0.75},
}

BASIN_PROFILES = {
    "Awash Basin": {"rain_base": 20.59, "slope_base": 12.4, "water_level_base": 3.2},
    "Abbay Basin": {"rain_base": 18.2, "slope_base": 15.8, "water_level_base": 4.1},
    "Omo Basin": {"rain_base": 14.7, "slope_base": 9.6, "water_level_base": 2.8},
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


def classify_risk_level(risk_score: float) -> str:
    if risk_score >= RISK_BANDS["Severe"]["min_score"]:
        return "Severe"
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


def generate_spatial_grid(center_lat: float, center_lon: float) -> pd.DataFrame:
    offsets = [
        (0.00, 0.00), (0.02, 0.05), (-0.02, -0.05), (0.05, 0.02),
        (-0.05, -0.02), (0.01, -0.02), (-0.01, 0.07),
    ]
    rain_rates = [20.59, 22.1, 8.4, 17.9, 5.2, 19.5, 11.3]
    slopes = [12.4, 14.2, 6.8, 11.5, 4.1, 13.7, 9.2]
    elevations = [850, 920, 450, 780, 300, 880, 620]

    rows = []
    for (d_lat, d_lon), rain, slope, elev in zip(offsets, rain_rates, slopes, elevations):
        risk_score = compute_risk_score(rain, slope)
        rows.append({
            "lat": center_lat + d_lat,
            "lon": center_lon + d_lon,
            "rain_rate_mm_hr": rain,
            "slope_degrees": slope,
            "elevation": elev,
            "risk_score": round(risk_score * 100, 1),
            "risk_level": classify_risk_level(risk_score),
            "time_to_peak_hrs": round(estimate_time_to_peak(rain, slope), 1),
        })
    return pd.DataFrame(rows)


def generate_hydrograph_data(timeframe: str) -> pd.DataFrame:
    if timeframe == "Daily":
        periods = pd.date_range("2026-08-01", periods=24, freq="h")
        rainfall = 3.0 + 8.0 * np.sin(np.linspace(0, 2 * np.pi, 24)) + np.random.default_rng(7).normal(0, 1.2, 24)
        discharge = 5.0 + 18.0 * np.maximum(0, np.sin(np.linspace(-0.5, 2.5 * np.pi, 24))) + np.random.default_rng(9).normal(0, 1.5, 24)
        label = periods.strftime("%H:%M")
    else:
        periods = pd.date_range("2026-07-07", periods=7, freq="D")
        rainfall = 12.0 + 6.0 * np.sin(np.linspace(0, np.pi, 7)) + np.random.default_rng(11).normal(0, 2.0, 7)
        discharge = 20.0 + 35.0 * np.maximum(0, np.sin(np.linspace(-0.3, 2.0 * np.pi, 7))) + np.random.default_rng(13).normal(0, 3.0, 7)
        label = periods.strftime("%b %d")

    return pd.DataFrame({
        "timestamp": periods,
        "label": label,
        "rainfall_mm_hr": np.clip(rainfall, 0, None).round(2),
        "discharge_m3_s": np.clip(discharge, 0, None).round(2),
    })


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
            y=hydro_df["discharge_m3_s"],
            name="Water Discharge (m³/s)",
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
    fig.update_xaxes(title_text="Time")
    fig.update_yaxes(title_text="Rainfall (mm/hr)", secondary_y=False)
    fig.update_yaxes(title_text="Discharge (m³/s)", secondary_y=True)
    return fig


def render_alert_banners(active_band: str, rainfall: float, slope: float) -> None:
    st.markdown("#### 4-Band Hazard Alert Engine")
    cols = st.columns(4)
    for col, (band, meta) in zip(cols, RISK_BANDS.items()):
        is_active = band == active_band
        border = f"3px solid {'#111827' if is_active else '#e5e7eb'}"
        bg = "#f9fafb" if is_active else "#ffffff"
        col.markdown(
            f"""
            <div style="border:{border}; border-radius:8px; padding:12px; background:{bg}; text-align:center;">
                <div style="font-size:1.5rem;">{meta['emoji']}</div>
                <div style="font-weight:700;">{band}</div>
                <div style="font-size:0.8rem; color:#6b7280;">≥ {meta['min_score']:.0%} risk index</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.caption(f"Active alert driven by rainfall {rainfall:.1f} mm/hr and slope {slope:.1f}°.")


# --- TITLE & HEADER ---
st.title("🌊 HydroPulse | Hydrological Risk Analytics")
st.markdown("Real-time flood risk monitoring, hydrograph simulations, and spatial surge analytics.")

# --- SIDEBAR: LOCATION SELECTORS ---
st.sidebar.header("Location Filters")

countries = load_countries()
country_names = [name for name, _ in countries]
country_name_to_code = {name: code for name, code in countries}

selected_country = st.sidebar.selectbox("Select Country", country_names)
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
    selected_city_name = st.sidebar.selectbox("Select City", city_names)
    selected_city = next(city for city in country_cities if city["name"] == selected_city_name)
    map_latitude = selected_city["latitude"]
    map_longitude = selected_city["longitude"]
else:
    st.sidebar.warning("No major cities found for this country. Enter coordinates manually.")
    selected_city_name = st.sidebar.text_input("Enter City Name", value=selected_country)
    map_latitude = st.sidebar.number_input("Latitude", value=6.50, format="%.4f")
    map_longitude = st.sidebar.number_input("Longitude", value=38.00, format="%.4f")

# --- SIDEBAR: ROUND 1 MONITORING CONTROLS ---
st.sidebar.header("Monitoring Controls")
region = st.sidebar.selectbox("Select Target Basin", list(BASIN_PROFILES.keys()))
basin = BASIN_PROFILES[region]

rainfall_rate = st.sidebar.slider(
    "Rainfall Rate (mm/hr)",
    min_value=0.0,
    max_value=50.0,
    value=float(basin["rain_base"]),
    step=0.1,
)
slope_gradient = st.sidebar.slider(
    "Slope Gradient (°)",
    min_value=0.0,
    max_value=45.0,
    value=float(basin["slope_base"]),
    step=0.1,
)
selected_risk = st.sidebar.multiselect(
    "Filter Risk Level",
    list(RISK_BANDS.keys()),
    default=["High", "Severe"],
)
time_horizon = st.sidebar.slider("Forecast Horizon (Hours)", min_value=6, max_value=72, value=24, step=6)
timeframe = st.sidebar.radio("Hydrograph Timeframe", ["Daily", "Weekly"], horizontal=True)

# --- ROUND 1: CORE METRICS ---
risk_index = compute_risk_score(rainfall_rate, slope_gradient)
active_risk_band = classify_risk_level(risk_index)
water_level = basin["water_level_base"] * (1.0 + risk_index * 0.8)
time_to_peak = estimate_time_to_peak(rainfall_rate, slope_gradient)
rain_delta = rainfall_rate - basin["rain_base"]

st.divider()
st.subheader("Round 1 — Base Monitoring Engine")
metric_cols = st.columns(5)
metric_cols[0].metric("Rainfall Rate", f"{rainfall_rate:.2f} mm/hr", f"{rain_delta:+.1f} mm/hr")
metric_cols[1].metric("Slope Gradient", f"{slope_gradient:.1f}°", "Terrain incline")
metric_cols[2].metric("Water Level", f"{water_level:.2f} m", f"{region}")
metric_cols[3].metric("Risk Index", f"{risk_index:.0%}", active_risk_band)
metric_cols[4].metric("Time to Peak Surge", f"{time_to_peak:.1f} hrs", f"{time_horizon}h horizon")

st.divider()

# --- ROUND 2 + 3: ALERTS ---
render_alert_banners(active_risk_band, rainfall_rate, slope_gradient)

st.divider()

# --- MAIN DASHBOARD ---
col_map, col_charts = st.columns([1.2, 1])

map_data = generate_spatial_grid(map_latitude, map_longitude)
if selected_risk:
    map_data = map_data[map_data["risk_level"].isin(selected_risk)]

display_map_data = map_data.copy()

with col_map:
    st.subheader("Round 2 — 3D PyDeck Risk Map")
    st.caption(f"Centered on {selected_city_name}, {selected_country} · {len(display_map_data)} risk zones displayed")

    if display_map_data.empty:
        st.warning("No risk zones match the current filter. Adjust the risk level filter in the sidebar.")
    else:
        display_map_data["fill_color"] = display_map_data["risk_level"].map(
            lambda level: RISK_BANDS[level]["color"]
        )

        column_layer = pdk.Layer(
            "ColumnLayer",
            data=display_map_data,
            get_position="[lon, lat]",
            get_elevation="elevation",
            elevation_scale=10,
            radius=1200,
            get_fill_color="fill_color",
            pickable=True,
            auto_highlight=True,
        )

        scatter_layer = pdk.Layer(
            "ScatterplotLayer",
            data=display_map_data,
            get_position="[lon, lat]",
            get_radius=800,
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
                        "Slope: {slope_degrees}°<br/>"
                        "Peak ETA: {time_to_peak_hrs} hrs"
                    ),
                    "style": {"backgroundColor": "steelblue", "color": "white"},
                },
            )
        )

with col_charts:
    st.subheader("Round 3 — Advanced Analytics")
    st.markdown("**Dual-Axis Hydrograph: Water Discharge vs. Rainfall**")
    hydro_df = generate_hydrograph_data(timeframe)
    st.plotly_chart(build_dual_axis_hydrograph(hydro_df), use_container_width=True)

    st.markdown("**Regional Vulnerability Breakdown (%)**")
    if display_map_data.empty:
        st.info("Risk breakdown unavailable — no zones match the current filter.")
    else:
        risk_counts = display_map_data["risk_level"].value_counts(normalize=True).reindex(RISK_BANDS.keys(), fill_value=0) * 100
        risk_breakdown = pd.DataFrame({"Percentage": risk_counts.round(1)})
        st.bar_chart(risk_breakdown)

st.divider()

# --- CSV EXPORT ---
if display_map_data.empty:
    st.subheader("Data Export")
    st.info("Export unavailable — adjust risk filters to include at least one zone.")
else:
    export_df = display_map_data.merge(
    hydro_df[["label", "rainfall_mm_hr", "discharge_m3_s"]],
    how="cross",
)
export_df.insert(0, "country", selected_country)
export_df.insert(1, "city", selected_city_name)
export_df.insert(2, "basin", region)
    export_df.insert(3, "forecast_horizon_hrs", time_horizon)

    st.subheader("Data Export")
    st.download_button(
    label="⬇️ Download Filtered Hydrological Dataset (CSV)",
    data=export_df.to_csv(index=False).encode("utf-8"),
    file_name=f"hydropulse_{selected_city_name.lower().replace(' ', '_')}_{timeframe.lower()}.csv",
        mime="text/csv",
    )
