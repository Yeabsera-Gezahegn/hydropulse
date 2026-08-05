"""
HydroPulse — Interactive Hydrological Risk Analytics.

Scenario-driven Streamlit dashboard that mirrors the physics-informed weighting of
`src.engine.risk.model.RiskEngine` and the time-to-peak estimator of
`src.engine.risk.classifier.RiskClassifier`, expressed on a 0-100 risk scale.

Adds a dual-axis storm hydrograph, a 3D sub-catchment risk map, an automated
early-warning banner, and CSV export of the active scenario.
"""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
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

RISK_RGB = {
    "Low": [34, 197, 94],
    "Moderate": [234, 179, 8],
    "High": [249, 115, 22],
    "Critical": [239, 68, 68],
}

# Sub-catchment monitoring zones inside the default bounding box of config.settings.
MONITORING_ZONES = [
    {"zone": "Zone A — Upper Headwater", "lat": 6.94, "lon": 38.08, "exposure": 1.00},
    {"zone": "Zone B — Steep Tributary", "lat": 6.86, "lon": 38.22, "exposure": 1.12},
    {"zone": "Zone C — Valley Confluence", "lat": 6.76, "lon": 38.14, "exposure": 0.95},
    {"zone": "Zone D — Terraced Farmland", "lat": 6.70, "lon": 38.33, "exposure": 0.82},
    {"zone": "Zone E — Downstream Town", "lat": 6.61, "lon": 38.22, "exposure": 0.90},
    {"zone": "Zone F — Floodplain Outlet", "lat": 6.55, "lon": 38.42, "exposure": 0.68},
]

STORM_PEAK_HOUR = 6.0
STORM_WIDTH_HOURS = 3.5
CATCHMENT_AREA_KM2 = 180.0
RUNOFF_COEFFICIENT = 0.55

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


def storm_hydrograph(
    rain_mm_hr: float, saturation_pct: float, lag_hours: float
) -> pd.DataFrame:
    """
    Build a 24-hour hyetograph and the basin discharge response it drives.

    Precipitation is a Gaussian storm cell peaking at `rain_mm_hr`; discharge is the
    rational-method response to it, shifted by `lag_hours` so the surge arrives at the
    computed time to peak and attenuated over a broader recession limb.
    """
    hours = np.arange(0.0, 24.0, 1.0)
    precipitation = rain_mm_hr * np.exp(
        -(((hours - STORM_PEAK_HOUR) / STORM_WIDTH_HOURS) ** 2)
    )

    # Rational method Q = C * i * A, with C lifted by antecedent soil saturation.
    runoff_coefficient = RUNOFF_COEFFICIENT * (0.6 + 0.4 * saturation_pct / 100.0)
    peak_discharge = (
        runoff_coefficient * (rain_mm_hr / 1000.0 / 3600.0) * CATCHMENT_AREA_KM2 * 1e6
    )

    lag = float(np.clip(lag_hours, 0.0, 23.0))
    discharge = peak_discharge * np.exp(
        -(((hours - STORM_PEAK_HOUR - lag) / (STORM_WIDTH_HOURS * 1.6)) ** 2)
    )

    return pd.DataFrame(
        {
            "hour": hours,
            "label": [f"T+{int(h):02d}:00" for h in hours],
            "precipitation_mm_hr": precipitation,
            "discharge_m3_s": discharge,
        }
    )


def zone_risk_table(
    rain_mm_hr: float, saturation_pct: float, slope_deg: float
) -> pd.DataFrame:
    """Per-zone risk index, band, colour, and column height for the 3D map."""
    base_score = risk_score(rain_mm_hr, saturation_pct, slope_deg)
    base_lead = time_to_peak_hours(rain_mm_hr, slope_deg)

    rows = []
    for zone in MONITORING_ZONES:
        zone_score = float(np.clip(base_score * zone["exposure"], 0.0, 100.0))
        zone_level = classify_risk(zone_score)
        rows.append(
            {
                "zone": zone["zone"],
                "lat": zone["lat"],
                "lon": zone["lon"],
                "risk_index": round(zone_score, 1),
                "risk_level": zone_level,
                # Column height scales directly with the active risk index.
                "column_height": zone_score * 40.0,
                "color": RISK_RGB[zone_level] + [205],
                "time_to_peak": round(base_lead / zone["exposure"], 1),
            }
        )
    return pd.DataFrame(rows)


def alert_message(
    level_name: str,
    score_value: float,
    rain_mm_hr: float,
    saturation_pct: float,
    slope_deg: float,
    lead_hours: float,
    hotspot: str,
) -> str:
    """Compose the operational early-warning text for the active scenario."""
    context = (
        f"Rainfall {rain_mm_hr:.1f} mm/hr on a {slope_deg:.0f}° slope with "
        f"{saturation_pct}% soil saturation (risk index {score_value:.1f}/100)"
    )

    if level_name == "Critical":
        return (
            f"🚨 CRITICAL ALERT: {context} indicates severe flash flooding and slope "
            f"failure in ~{lead_hours:.1f} hours. Immediate evacuation recommended "
            f"for {hotspot}."
        )
    if level_name == "High":
        return (
            f"⚠️ HIGH ALERT: {context} indicates a damaging surge in "
            f"~{lead_hours:.1f} hours. Pre-position response teams and warn "
            f"communities in {hotspot}."
        )
    if level_name == "Moderate":
        return (
            f"🔶 MODERATE WATCH: {context} suggests localised runoff peaking in "
            f"~{lead_hours:.1f} hours. Monitor {hotspot} and keep drainage clear."
        )
    return (
        f"✅ LOW RISK: {context} indicates no significant surge expected; nominal "
        f"peak in ~{lead_hours:.1f} hours. Routine monitoring of {hotspot} continues."
    )


def scenario_csv(
    rain_mm_hr: float,
    saturation_pct: float,
    slope_deg: float,
    score_value: float,
    level_name: str,
    lead_hours: float,
    velocity_m_s: float,
) -> str:
    """Serialise the active scenario inputs and derived metrics as CSV."""
    report = pd.DataFrame(
        [
            {
                "generated_utc": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "rainfall_intensity_mm_hr": round(rain_mm_hr, 2),
                "soil_saturation_pct": saturation_pct,
                "slope_gradient_deg": round(slope_deg, 2),
                "risk_score": round(score_value, 1),
                "risk_status": level_name,
                "time_to_peak_hours": round(lead_hours, 2),
                "runoff_velocity_m_s": round(velocity_m_s, 3),
                "flow_distance_m": FLOW_DISTANCE_M,
                "manning_n": MANNING_N,
            }
        ]
    )
    return report.to_csv(index=False)


st.title("🌊 HydroPulse | Hydrological Risk Analytics")
st.caption(
    "Scenario-driven flash-flood and landslide risk analytics for ungauged "
    "headwater catchments."
)

st.sidebar.header("Scenario Controls")
rainfall = st.sidebar.slider("Rainfall Intensity (mm/hr)", 0.0, 100.0, 25.0, step=0.5)
saturation = st.sidebar.slider("Soil Saturation Rate (%)", 0, 100, 60, step=1)
slope = st.sidebar.slider("Slope Gradient (°)", 0.0, 90.0, 45.0, step=0.5)

score = risk_score(rainfall, saturation, slope)
level = classify_risk(score)
peak_hours = time_to_peak_hours(rainfall, slope)
velocity = runoff_velocity_m_s(rainfall, slope)

zones = zone_risk_table(rainfall, saturation, slope)
hotspot_row = zones.loc[zones["risk_index"].idxmax()]
hotspot = str(hotspot_row["zone"])
hydrograph = storm_hydrograph(rainfall, saturation, peak_hours)

st.sidebar.divider()
st.sidebar.metric("Runoff Velocity", f"{velocity:.2f} m/s")
st.sidebar.caption(f"Flow path {FLOW_DISTANCE_M / 1000:.0f} km · Manning n = {MANNING_N}")

st.sidebar.divider()
st.sidebar.subheader("Scenario Export")
st.sidebar.download_button(
    label="⬇️ Download Scenario Report (CSV)",
    data=scenario_csv(
        rainfall, saturation, slope, score, level, peak_hours, velocity
    ),
    file_name=(
        "hydropulse_scenario_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
    ),
    mime="text/csv",
    use_container_width=True,
)

st.divider()

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Rainfall Intensity", f"{rainfall:.1f} mm/hr")
kpi2.metric("Slope Gradient", f"{slope:.1f}°")
kpi3.metric("Time to Peak Surge", f"{peak_hours:.1f} hrs")
kpi4.metric("Overall Risk Level", level, f"Index {score:.1f}/100")

st.divider()

st.subheader("24-Hour Storm Hydrograph")
hydro_fig = go.Figure()
hydro_fig.add_trace(
    go.Bar(
        x=hydrograph["label"],
        y=hydrograph["precipitation_mm_hr"],
        name="Precipitation (mm/hr)",
        marker_color="#38bdf8",
        opacity=0.75,
        hovertemplate="%{x}<br>%{y:.1f} mm/hr<extra></extra>",
    )
)
hydro_fig.add_trace(
    go.Scatter(
        x=hydrograph["label"],
        y=hydrograph["discharge_m3_s"],
        name="Basin Discharge (m³/s)",
        mode="lines+markers",
        yaxis="y2",
        line={"color": RISK_BANDS[level], "width": 3},
        hovertemplate="%{x}<br>%{y:.1f} m³/s<extra></extra>",
    )
)
hydro_fig.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font={"color": "#e2e8f0"},
    height=380,
    margin={"t": 40, "b": 40, "l": 10, "r": 10},
    legend={"orientation": "h", "y": 1.12, "x": 0},
    hovermode="x unified",
    xaxis={"title": "Forecast hour", "gridcolor": "#1f2c47"},
    yaxis={
        "title": "Precipitation (mm/hr)",
        "gridcolor": "#1f2c47",
        "rangemode": "tozero",
    },
    yaxis2={
        "title": "Discharge (m³/s)",
        "overlaying": "y",
        "side": "right",
        "showgrid": False,
        "rangemode": "tozero",
    },
)
st.plotly_chart(hydro_fig, use_container_width=True)
st.caption(
    f"Rainfall peaks at T+{int(STORM_PEAK_HOUR):02d}:00; discharge is lagged by the "
    f"{peak_hours:.1f} h surge delay, peaking near "
    f"T+{int(min(STORM_PEAK_HOUR + peak_hours, 23)):02d}:00."
)

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

st.divider()

st.subheader("Sub-Catchment Risk Map (3D)")
deck_layer = pdk.Layer(
    "ColumnLayer",
    data=zones,
    get_position="[lon, lat]",
    get_elevation="column_height",
    get_fill_color="color",
    radius=1800,
    elevation_scale=1,
    pickable=True,
    auto_highlight=True,
)
st.pydeck_chart(
    pdk.Deck(
        layers=[deck_layer],
        initial_view_state=pdk.ViewState(
            latitude=float(zones["lat"].mean()),
            longitude=float(zones["lon"].mean()),
            zoom=8.6,
            pitch=50,
            bearing=15,
        ),
        map_style="dark",
        tooltip={
            "text": (
                "{zone}\nRisk index: {risk_index} ({risk_level})"
                "\nTime to peak: {time_to_peak} hrs"
            )
        },
    )
)

alert_text = alert_message(
    level, score, rainfall, saturation, slope, peak_hours, hotspot
)
if level == "Critical":
    st.error(alert_text)
elif level == "High":
    st.warning(alert_text)
elif level == "Moderate":
    st.warning(alert_text, icon="🔶")
else:
    st.info(alert_text)

with st.expander("Zone-level risk breakdown"):
    st.dataframe(
        zones[["zone", "risk_index", "risk_level", "time_to_peak"]].rename(
            columns={
                "zone": "Monitoring Zone",
                "risk_index": "Risk Index",
                "risk_level": "Risk Level",
                "time_to_peak": "Time to Peak (hrs)",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

st.divider()

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
