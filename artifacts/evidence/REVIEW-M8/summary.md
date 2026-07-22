# REVIEW-M8 evidence (minimal dashboard)

Date: 2026-07-21. Task IDs M8-T1..T4.

## Code delivered
- `src/bearing_pdm/dashboard.py` — 5-tab Streamlit app: Signal & FFT, Health Indicator, RUL Prediction, Model Evaluation, Architecture & Limitations. Loads cached Parquet/DuckDB/joblib only, never trains on page load.
- `scripts/run_dashboard.py` — CLI launcher.
- `tests/test_dashboard.py` — Streamlit `AppTest` headless startup test (2 tests: no exception, all 5 tabs present).

## One real correctness bug found via actual screenshot, fixed (docs/decisions.md D11)
A real Playwright screenshot of the college Health Indicator tab showed PCA HI swinging below -3 (should be ~[0,1]). Root cause: the Health Indicator and RUL Prediction tabs applied FEMTO-fit models (`build_health.py`/`train_models.py` only ever fit on FEMTO learning bearings) to whichever dataset was selected, including college — applying a scaler/PCA fit on FEMTO's feature scale to college's very different scale is meaningless, not just less accurate. Fixed: both tabs now gate on `dataset_id == "femto"` and show an explanatory message for college instead of a silently-wrong chart. College's real RUL evidence remains the walk-forward evaluation (already correctly self-contained per fold), shown in the Model Evaluation tab regardless of dataset selection.

## Verification performed (three independent layers, not just "it imports")
1. **Direct logic smoke test** (`m2_smoke.py`-style, not committed) — called the dashboard's internal data-loading/raw-reread/FFT/HI/RUL functions directly against the real cached artifacts (both datasets, 3 rows each incl. first/middle/last). All raw-signal reloads matched `n_samples` exactly; HI and RUL predictions ran without error.
2. **Streamlit `AppTest`** (`tests/test_dashboard.py`, committed, 2 tests) — runs the actual dashboard script headlessly. Confirmed no exception; Streamlit renders every `st.tabs()` body in one script run (not lazy-loaded), so this exercises all 5 tabs' code paths in one pass.
3. **Real browser screenshots** (Playwright, `reports/figures/dashboard_{college,femto}_*_tab.png`) — this is what caught the D11 bug that layers 1-2 missed (both would have "passed" with the wrong college HI values, since neither layer inspected the actual numeric output against a domain sanity check). Screenshots confirm: real vibration signal loaded from the actual source CSV/acc file (not fabricated), real FFT, real HI trend matching `reports/figures/hi_transparent.png` from M3, real LOBO metrics matching M4's evidence exactly, and the corrected college domain-guard message.

## M8 acceptance criteria (docs/milestone.md, minimal scope)
- Dataset select, signal/FFT/HI/RUL panels: yes, all present and screenshotted.
- Cached artifact loading, no page-load training: yes - `st.cache_data`/`st.cache_resource` on all load functions; models loaded via joblib, never fit in the dashboard process.
- Fails gracefully: yes - `FileNotFoundError` on source-file reads is caught (falls back to cached feature values); missing joblib models show a warning instead of crashing; the D11 fix itself is a graceful-degradation pattern (explanatory message instead of a wrong chart).

## Verdict
M8 (minimal) gate met. Accelerated review track (`command.md -> M0 -> M1 -> M2 -> M3 -> M4 -> minimal M8`) complete.
