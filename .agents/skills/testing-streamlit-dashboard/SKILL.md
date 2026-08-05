---
name: testing-streamlit-dashboard
description: How to run and UI-test the HydroPulse Streamlit dashboard (streamlit_app.py) locally, including slider automation and formula verification.
---

# Testing the HydroPulse Streamlit dashboard

## Run it
- Deps: `streamlit`, `pandas`, `numpy`, `plotly` (listed in `requirements.txt`; may already be installed
  globally on the box). Install with `pip install -r requirements.txt` if missing.
- Another agent's instance may already own port 8501. Start your own:
  `nohup streamlit run streamlit_app.py --server.port 8502 --server.headless true > /tmp/st8502.log 2>&1 &`
- Verify readiness with `curl -s -o /dev/null -w "%{http_code}" http://localhost:8502` (expect 200) and
  grep `/tmp/st8502.log` for `traceback|error|exception` — Streamlit renders tracebacks in-page, so also
  check the page visually.
- No auth, no backend, no secrets required.

## Driving Streamlit sliders with computer-use
- Sliders live in the left sidebar. Use `left_click_drag` from the current handle position to the target
  x on the track; the track spans from the left-label x to the right-label x. Value ≈ `x_left + px_per_unit * value`.
- Dragging is snapped to the slider `step` (e.g. 0.5), so you often land one step off the intended value
  (45.0 → 45.5). Read the numeric badge above the handle (also exposed in the DOM as
  `div[aria-label="Rainfall Intensity (mm/hr)"]`) and recompute expectations rather than fighting the snap;
  fine-tune by clicking the handle and pressing Left/Right arrow keys (one step per press).
- Drag slightly past the track end to reach the min/max reliably.

## Verifying computed values
- Do not eyeball formulas: re-implement the app's functions in a throwaway `python3 - <<'EOF'` script and
  print expected values for each scenario before driving the UI. Compare against KPI cards, the Plotly
  gauge number, the driver bars' text labels, the sidebar metric, and the footer caption — they are all
  derived from the same numbers, so a mismatch between any two is a real bug.
- Useful boundary scenarios: all sliders at 0 (clip floors / divide-by-zero), max on all sliders
  (component clipping), and inputs chosen so the composite score lands exactly on a band threshold
  (checks `>` vs `>=` in the classifier).

## Known benign console noise
- `WARN Infinite extent for field "..."` from Vega-Lite appears while `st.line_chart` mounts. It is a
  warning, not an error, and the chart renders fine. Don't report it as a failure; do report any
  console entries at `error` level.
