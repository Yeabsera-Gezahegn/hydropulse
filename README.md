# HydroPulse – Real‑Time Flood & Landslide Risk Dashboard

## 1. Repository Title & Systems Overview
**HydroPulse** is a pure‑software, hardware‑free geospatial analytics platform that ingests satellite‑based precipitation (NASA GPM) and digital elevation model (DEM) data to model flash‑flood and landslide risk in near‑real‑time. The system runs as an interactive Streamlit web app, exposing a low‑bandwidth JSON export for downstream alerting services.

## 2. Directory Tree
```
hydropulse/
├─ .git/                     # Git repository metadata
├─ .gitignore
├─ .pytest_cache/
├─ LICENSE
├─ README.md                 # ← you are reading this file
├─ RESEARCH.md               # Technical research paper (see below)
├─ config/                   # Configuration files (e.g., API keys, defaults)
├─ data/                     # Example static datasets (optional)
├─ requirements.txt          # Python dependencies
├─ src/
│   ├─ __init__.py
│   ├─ api/                  # API wrappers (e.g., Open‑Meteo client)
│   ├─ engine/               # Core risk‑engine implementations
│   └─ risk/                 # Risk calculations and thresholds
├─ streamlit_app.py          # Streamlit entry‑point (UI, calculations, export)
└─ tests/                    # Unit‑test suite
```

## 3. System Architecture
```
+-------------------+      +---------------------+      +-------------------+
|  Open‑Meteo API  | ---> |  fetch_live_weather | ---> |  Live weather    |
+-------------------+      +---------------------+      +-------------------+
                                 |                         |
                                 v                         v
+-------------------+   +---------------------+   +------------------------------+
|  DEM / GPM data   |   |  generate_spatial_  |   |  Streamlit UI (metric cards, |
|  (local / remote) |   |  grid / forecast   |   |   PyDeck map, Plotly hydrograph)
+-------------------+   +---------------------+   +------------------------------+
                                 |                         |
                                 v                         v
                         +-------------------+   +--------------------------+
                         |  compute_risk_    |   |  build_export_dataframe  |
                         |  score / TWI / V  |   |  → low‑bandwidth JSON    |
                         +-------------------+   +--------------------------+
```
*Open‑Meteo* provides a 72‑hour hourly precipitation forecast. When the API is unavailable, a deterministic sinusoidal model seeded by the location is used. The *risk engine* blends rainfall intensity, slope, and a Topographic Wetness Index (TWI) proxy to produce a composite risk index **R** (0–1). The UI renders the risk map with **PyDeck** and the hydrograph with **Plotly**, and users can download a compact CSV export (< 5 KB).

## 4. Tech Stack & Dependencies
| Layer | Technology |
|-------|------------|
| Language | Python 3.11 |
| Web UI | Streamlit, Plotly, PyDeck |
| Data handling | pandas, numpy |
| Geospatial | pydeck, geonamescache, pycountry |
| HTTP client | requests |
| Testing | pytest |
| Packaging | pip (requirements.txt) |

## 5. Setup & Execution Guide
```bash
# 1️⃣ Clone the repository (if not already done)
git clone https://github.com/Yeabsera-Gezahegn/hydropulse.git
cd hydropulse

# 2️⃣ Install Python dependencies (prefer a virtualenv)
python -m venv .venv
# On Windows
.venv\Scripts\activate
# On macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt

# 3️⃣ Run the Streamlit dashboard locally
streamlit run streamlit_app.py

# 4️⃣ Interact with the UI
#    • Choose country / city (or enter lat/lon)
#    • Adjust Rainfall Rate (mm/hr) and Slope Gradient (%) sliders
#    • View live metric cards, risk map, and hydrograph
#    • Click **Prepare Data Export** to generate a low‑bandwidth CSV payload

# 5️⃣ Export payload (example filename)
#    hydropulse_<city>_<hours>h.csv (≈ <5 KB)
```
**Note:** The live weather feed requires internet access to query Open‑Meteo. If unavailable, the app falls back to a deterministic model seeded by the selected location.

---
*All formulas and variable names referenced below correspond exactly to the source code in `streamlit_app.py` and the `src/engine` package.*
