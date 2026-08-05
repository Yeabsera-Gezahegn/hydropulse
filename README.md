# HydroPulse — Real-Time Hydrological Risk & Flood Analytics

![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?style=flat&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.28%2B-FF4B4B.svg?style=flat&logo=streamlit&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Weather: Open-Meteo](https://img.shields.io/badge/Weather-Open--Meteo%20API-00AAFF.svg)

HydroPulse is a Streamlit dashboard that tracks localized rainfall, topographical slope, and flood runoff risk using live weather data from the [Open-Meteo API](https://open-meteo.com/). Select any country and city from the sidebar, and the dashboard fetches current conditions — precipitation, temperature, humidity, wind speed — then feeds a 72-hour hourly forecast directly into a runoff hydrograph and a 3D spatial risk map.

It is built around a simple composite risk model (rainfall intensity, slope gradient, and a topographic wetness index proxy) that rerenders all charts and map layers in real time as you adjust the sliders.

---

## Features

- **Live weather metrics** — current precipitation (mm/hr), temperature (°C), relative humidity (%), and wind speed (km/h) pulled from Open-Meteo every 10 minutes.
- **Augmented precipitation parsing** — when the instantaneous API snapshot returns 0 mm (common during dry hours), the dashboard checks the first 6 forecast hours and uses their maximum so dry-hour zeros don't silently zero out the risk model.
- **Scenario override** — if no active rainfall is detected, the Rainfall Rate slider lets you model hypothetical storm intensities without losing live temperature and humidity readings.
- **3D spatial risk map** — PyDeck ColumnLayer and ScatterplotLayer showing risk-zoned sensor points within ±0.25° of the selected city, colour-coded by risk tier and extruded by elevation. Updates instantly on slider changes.
- **Dual-axis Plotly hydrograph** — 72-hour bar/line chart showing forecast rainfall (mm/hr) on one axis and estimated runoff volume (m³/s) on the other.
- **Regional vulnerability breakdown** — stacked bar chart summarising the share of Low / Moderate / High / Critical risk points visible on the map.
- **CSV export** — one-click download of the full forecast and spatial sensor dataset for offline analysis.
- **Graceful offline fallback** — if the API is unreachable, every chart and metric continues to work using a location-seeded deterministic model.

---

## Tech Stack

| Layer | Library |
|---|---|
| Dashboard framework | [Streamlit](https://streamlit.io/) |
| Weather data | [Open-Meteo API](https://open-meteo.com/) (free, no key required) |
| Data manipulation | [Pandas](https://pandas.pydata.org/), [NumPy](https://numpy.org/) |
| 3D map | [PyDeck](https://deckgl.readthedocs.io/) |
| Charts | [Plotly](https://plotly.com/python/) |
| Geo lookups | [pycountry](https://github.com/flyingcircusio/pycountry), [geonamescache](https://github.com/yaph/geonamescache) |
| HTTP | [Requests](https://requests.readthedocs.io/) |

---

## Setup

**Requirements:** Python 3.10 or newer, pip.

```bash
# 1. Clone the repository
git clone https://github.com/Yeabsera-Gezahegn/hydropulse.git
cd hydropulse

# 2. Create and activate a virtual environment (optional but recommended)
python -m venv venv
# macOS / Linux
source venv/bin/activate
# Windows
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the dashboard
streamlit run streamlit_app.py
```

The app will open in your browser at `http://localhost:8501`.

---

## How It Works

### Risk Score

Each sensor point (and the dashboard header) is scored using a weighted composite index:

```
risk = 0.50 × (rainfall / 50) + 0.35 × (slope_deg / 45) + 0.15 × TWI_proxy
```

where `TWI_proxy = (rainfall / 30) × (slope_deg / 20)` approximates topographic
wetness. Scores are clamped to `[0, 1]` and mapped to four alert tiers:

| Tier | Risk Index |
|---|---|
| 🟢 Low | 0 – 24% |
| 🟡 Moderate | 25 – 49% |
| 🟠 High | 50 – 74% |
| 🔴 Critical | 75 – 100% |

### Hydrograph

When the Open-Meteo 72-hour forecast contains non-zero precipitation values,
those are used directly as the rainfall signal (with a small floor from the
slider so manual overrides register). When the forecast is entirely dry or the
API is offline, the hydrograph falls back to a location-seeded sinusoidal
model driven by the slider value.

### Spatial Grid

Forty grid points are generated around the city centre (±0.25° bounding box).
Four anchor points are pinned to each risk tier to guarantee the full colour
spectrum always appears on the map. The remaining 36 points inherit risk scores
computed from the current slider inputs, so every adjustment immediately
recolours and re-extrudes the map columns.

---

## Project Structure

```
hydropulse/
├── streamlit_app.py      # Main dashboard — single-file Streamlit app
├── requirements.txt      # Python dependencies
├── config/               # Environment settings
├── data/                 # Raw and processed data cache
├── src/                  # Supporting modules (ingestion, risk engine, API)
├── tests/                # Unit and integration tests
├── RESEARCH_PAPER.md     # Academic writeup and mathematical derivations
└── LICENSE               # MIT
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## License

MIT — see [LICENSE](LICENSE) for details.
