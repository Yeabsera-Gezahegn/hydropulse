"""
HydroPulse — Interactive Hydrological Risk Analytics (Round 1).

Scenario-driven Streamlit dashboard that mirrors the physics-informed weighting of
`src.engine.risk.model.RiskEngine` and the time-to-peak estimator of
`src.engine.risk.classifier.RiskClassifier`, expressed on a 0-100 risk scale.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Weighting mirrors RiskEngine.calculate_risk_score (rain / slope / wetness).
RAIN_WEIGHT = 0.50
SLOPE_WEIGHT = 0.35
SATURATION_WEIGHT = 0.15

RAIN_REFERENCE_MM_HR = 50.0
SLOPE_REFERENCE_DEG = 45.0

MANNING_N = 0.04
FLOW_DISTANCE_M = 5000.0

RISK_BANDS = {
    "Low": "#22c55e",
    "Moderate": "#eab308",
    "High": "#f97316",
    "Critical": "#ef4444",
}

st.set_page_config(
    page_title="HydroPulse | Hydrological Risk Analytics",
    layout="wide",
    page_icon="🌊",
)

st.markdown(
    """
    <style>
        .stApp { background-color: #0b1220; color: #e2e8f0; }
        section[data-testid="stSidebar"] { background-color: #111a2b; }
        div[data-testid="stMetric"] {
            background-color: #131d31;
            border: 1px solid #1f2c47;
            border-radius: 12px;
            padding: 16px 18px;
        }
        div[data-testid="stMetricLabel"] p {
            color: #93a4c3;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }
        div[data-testid="stMetricValue"] { color: #f8fafc; }
        h1, h2, h3 { color: #f1f5f9; }
        hr { border-color: #1f2c47; }
    </style>
    """,
    unsafe_allow_html=True,
)


def runoff_velocity_m_s(rain_mm_hr: float, slope_deg: float) -> float:
    """Manning kinematic-wave overland velocity (m/s), matching the risk engine."""
    slope_sine = np.sin(np.radians(max(slope_deg, 0.05)))
    hydraulic_radius = max(rain_mm_hr * 1e-5, 1e-4)
    velocity = (1.0 / MANNING_N) * (hydraulic_radius ** (2.0 / 3.0)) * (slope_sine**0.5)
    return float(np.clip(velocity, 0.01, 15.0))


def risk_score(rain_mm_hr: float, saturation_pct: float, slope_deg: float) -> float:
    """Composite hazard index rescaled to 0-100."""
    rain_component = np.clip(rain_mm_hr / RAIN_REFERENCE_MM_HR, 0.0, 1.0)
    slope_component = np.clip(slope_deg / SLOPE_REFERENCE_DEG, 0.0, 1.0)
    saturation_component = np.clip(saturation_pct / 100.0, 0.0, 1.0)

    composite = (
        RAIN_WEIGHT * rain_component
        + SLOPE_WEIGHT * slope_component
        + SATURATION_WEIGHT * saturation_component
    )
    return float(np.clip(composite * 100.0, 0.0, 100.0))


def classify_risk(score: float) -> str:
    """Categorise a 0-100 risk score into a threat band."""
    if score > 80.0:
        return "Critical"
    if score >= 60.0:
        return "High"
    if score >= 30.0:
        return "Moderate"
    return "Low"


def time_to_peak_hours(rain_mm_hr: float, slope_deg: float) -> float:
    """Estimated surge delay to peak hydrograph, from runoff travel time."""
    velocity = runoff_velocity_m_s(rain_mm_hr, slope_deg)
    hours = (FLOW_DISTANCE_M / velocity) / 3600.0
    return float(np.clip(hours, 0.1, 48.0))


st.title("🌊 HydroPulse | Hydrological Risk Analytics")
st.caption(
    "Scenario-driven flash-flood and landslide risk analytics for ungauged "
    "headwater catchments."
)

st.sidebar.header("Scenario Controls")
rainfall = st.sidebar.slider(
    "Rainfall Intensity (mm/hr)", 0.0, 100.0, 25.0, step=0.5
)
saturation = st.sidebar.slider("Soil Saturation Rate (%)", 0, 100, 60, step=1)
slope = st.sidebar.slider("Slope Gradient (°)", 0.0, 90.0, 45.0, step=0.5)

score = risk_score(rainfall, saturation, slope)
level = classify_risk(score)
peak_hours = time_to_peak_hours(rainfall, slope)
velocity = runoff_velocity_m_s(rainfall, slope)

st.sidebar.divider()
st.sidebar.metric("Runoff Velocity", f"{velocity:.2f} m/s")
st.sidebar.caption(
    f"Flow path {FLOW_DISTANCE_M / 1000:.0f} km · Manning n = {MANNING_N}"
)

st.divider()

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Rainfall Intensity", f"{rainfall:.1f} mm/hr")
kpi2.metric("Slope Gradient", f"{slope:.1f}°")
kpi3.metric("Time to Peak Surge", f"{peak_hours:.1f} hrs")
kpi4.metric("Overall Risk Level", level, f"Index {score:.1f}/100")

st.divider()

col_gauge, col_breakdown = st.columns([1, 1])

with col_gauge:
    st.subheader("Composite Risk Index")
    gauge = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": " / 100", "font": {"color": "#f8fafc"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#93a4c3"},
                "bar": {"color": RISK_BANDS[level]},
                "bgcolor": "#131d31",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 30], "color": "#14311f"},
                    {"range": [30, 60], "color": "#3a3312"},
                    {"range": [60, 80], "color": "#43250f"},
                    {"range": [80, 100], "color": "#451717"},
                ],
            },
        )
    )
    gauge.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#e2e8f0"},
        height=320,
        margin={"t": 30, "b": 10, "l": 30, "r": 30},
    )
    st.plotly_chart(gauge, use_container_width=True)

with col_breakdown:
    st.subheader("Risk Driver Contribution")
    contributions = pd.DataFrame(
        {
            "Driver": ["Rainfall", "Slope", "Soil Saturation"],
            "Contribution": [
                RAIN_WEIGHT * np.clip(rainfall / RAIN_REFERENCE_MM_HR, 0.0, 1.0) * 100,
                SLOPE_WEIGHT * np.clip(slope / SLOPE_REFERENCE_DEG, 0.0, 1.0) * 100,
                SATURATION_WEIGHT * (saturation / 100.0) * 100,
            ],
        }
    )
    bars = go.Figure(
        go.Bar(
            x=contributions["Contribution"],
            y=contributions["Driver"],
            orientation="h",
            marker_color=["#38bdf8", "#a78bfa", "#34d399"],
            text=[f"{v:.1f}" for v in contributions["Contribution"]],
            textposition="outside",
        )
    )
    bars.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#e2e8f0"},
        height=320,
        xaxis={"title": "Index points", "range": [0, 60], "gridcolor": "#1f2c47"},
        margin={"t": 30, "b": 40, "l": 10, "r": 30},
    )
    st.plotly_chart(bars, use_container_width=True)

st.subheader("Rainfall Sensitivity Sweep")
sweep_rain = np.arange(0.0, 100.5, 2.5)
sweep = pd.DataFrame(
    {
        "Rainfall (mm/hr)": sweep_rain,
        "Risk Index": [risk_score(r, saturation, slope) for r in sweep_rain],
        "Time to Peak (hrs)": [time_to_peak_hours(r, slope) for r in sweep_rain],
    }
).set_index("Rainfall (mm/hr)")
st.line_chart(sweep, height=300)

st.caption(
    f"Current scenario — risk **{level}** ({score:.1f}/100), surge arrival in "
    f"{peak_hours:.1f} hours at {velocity:.2f} m/s overland velocity."
)
