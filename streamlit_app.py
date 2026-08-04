import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk

# --- PAGE SETUP ---
st.set_page_config(
    page_title="HydroPulse | Hydrological Risk Analytics",
    layout="wide",
    page_icon="🌊"
)

# --- TITLE & HEADER ---
st.title("🌊 HydroPulse | Hydrological Risk Analytics")
st.markdown("Real-time flood risk monitoring, hydrograph simulations, and spatial surge analytics.")

# --- SIDEBAR CONTROLS ---
st.sidebar.header("Control Panel")
region = st.sidebar.selectbox("Select Target Basin", ["Awash Basin", "Abbay Basin", "Omo Basin"])
selected_risk = st.sidebar.multiselect("Filter Risk Level", ["Low", "Moderate", "High", "Critical"], default=["High", "Critical"])
time_horizon = st.sidebar.slider("Forecast Horizon (Hours)", min_value=6, max_value=72, value=24, step=6)

st.divider()

# --- TOP KPI METRICS ---
col1, col2, col3, col4 = st.columns(4)
col1.metric(label="Rainfall Rate", value="20.59 mm/hr", delta="+2.4 mm/hr")
col2.metric(label="Slope Gradient", value="87.62°", delta="Steep Slope")
col3.metric(label="Time to Peak Surge", value="15.9 hrs", delta="-1.2 hrs")
col4.metric(label="Overall Risk Status", value="HIGH", delta_color="inverse")

st.divider()

# --- MAIN DASHBOARD LAYOUT ---
col_map, col_charts = st.columns([1.2, 1])

with col_map:
    st.subheader("📍 Spatial Risk Map (Pydeck 3D)")
    
    # Coordinates centered around Lat 6.5, Lon 38.0
    map_data = pd.DataFrame({
        'lat': [6.50, 6.52, 6.48, 6.55, 6.45, 6.51, 6.49],
        'lon': [38.00, 38.05, 37.95, 38.02, 38.10, 37.98, 38.07],
        'risk_score': [85, 92, 45, 78, 30, 88, 62],
        'elevation': [850, 920, 450, 780, 300, 880, 620]
    })
    
    # 3D Pydeck Column Layer
    pydeck_layer = pdk.Layer(
        'ColumnLayer',
        data=map_data,
        get_position='[lon, lat]',
        get_elevation='elevation',
        elevation_scale=10,
        radius=1200,
        get_fill_color='[239, 68, 68, 180]',
        pickable=True,
        auto_highlight=True
    )
    
    view_state = pdk.ViewState(
        latitude=6.50,
        longitude=38.00,
        zoom=9.5,
        pitch=45,
        bearing=15
    )
    
    st.pydeck_chart(pdk.Deck(
        layers=[pydeck_layer],
        initial_view_state=view_state,
        tooltip={"text": "Risk Index: {risk_score}\nLat: {lat}\nLon: {lon}"}
    ))

with col_charts:
    st.subheader("📊 Hydrological Analytics")
    
    # Chart 1: Hydrograph Line Chart
    st.markdown("**Runoff Surge vs. Precipitation Forecast**")
    hydro_df = pd.DataFrame({
        'Hour': ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '24:00'],
        'Precipitation (mm/h)': [5.0, 12.2, 18.4, 20.59, 15.1, 8.3, 3.0],
        'Runoff Surge (m³/s)': [2.1, 5.4, 14.2, 28.5, 22.1, 12.0, 4.8]
    }).set_index('Hour')
    
    st.line_chart(hydro_df)
    
    # Chart 2: Risk Breakdown Bar Chart
    st.markdown("**Regional Vulnerability Breakdown (%)**")
    risk_df = pd.DataFrame({
        'Category': ['Low Risk', 'Moderate', 'High Risk', 'Critical'],
        'Percentage': [40, 30, 20, 10]
    }).set_index('Category')
    
    st.bar_chart(risk_df)
