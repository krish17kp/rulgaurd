# FINAL SYSTEM TEST (2026-10-21, session 4)

## Real browser UI pass
Playwright + Chromium (installed into `.venv-linux` this session, see
FINAL_REPRODUCIBILITY.md) driving the actual `scripts/run_dashboard.py`
entrypoint (`dashboard.py` -> `dashboard_cross.render_universal()`).
30 real screenshots in `artifacts/evidence/final_publication_audit/`:
- Session 3: 23 PNGs — FEMTO + XJTU, all 10 Analyze tabs each, plus the
  live-Groq evidence-tab screenshots.
- Session 4: 7 PNGs — `state_switch_{01,02,03}_{xjtu,femto,xjtu}.png`,
  `state_switch_bearing_{01,02,03}_*.png` (Bearing1_1 -> Bearing2_1 ->
  Bearing1_1), `restart_test_fresh_browser.png`.

## State switching (XJTU -> FEMTO -> XJTU; FEMTO Bearing1_1 -> Bearing2_1 -> Bearing1_1)
Verified via screenshot inspection: the FEMTO-after-XJTU screenshot showed
`8,384` files / `2,803` recordings / `femto:Bearing1_1` (correct, not a
carried-over XJTU value); the Bearing2_1 screenshot showed `911`
recordings, matching Bearing2_1's real row count from the RUL evaluation
table independently — no stale dataset or bearing data observed. **PASS**
for dataset and bearing selectors; Signal/FFT/Evidence staleness across a
switch was not separately re-verified this session beyond what the
Overview tab's file/recording counts already demonstrate (time budget).

## Restart test
Stopped the running Streamlit process (`pkill -f "streamlit run"`),
launched a fresh process on a new port, opened a **fresh, isolated
Playwright browser context** (no cookies/storage carried over — the
closest equivalent to "a different user opening the app for the first
time"), navigated to Analyze, selected XJTU, opened the RUL tab: the
persisted real `routing_xjtu.json` artifact loaded correctly and showed
`RUL_SUPPRESSED` / `LOW MODEL APPLICABILITY`, matching the known real
routing decision (not recomputed on page load, no `.fit()` — consistent
with the dashboard's own hard constraint). **PASS.**

## Not covered this session
Export/import through the actual UI buttons (the underlying
`build_routing_bundle`/`load_bundle` round-trip was verified directly in
Python, not through a real browser click-through — see
FINAL_RELEASE_DECISION.md R22). Negative-input UI tests (empty path,
corrupt archive, unsupported file, through the real file-upload widget)
were not run this session — Playwright's handling of Streamlit's
`st.file_uploader` requires more setup than the time budget allowed.

## SESSION 6 UPDATE — real UI bundle round-trip (item 3) + a real bug found and fixed

### Environment finding (CRITICAL, fixed): `~/.venvs/rulguard`'s editable install pointed at the wrong repo
Before this test could run meaningfully, discovered that
`~/.venvs/rulguard` (the project's documented interpreter) had
`__editable__.rulguard-0.1.0.pth` pointing at
`/run/media/krish/New Volume/capstone/data/rlguard/src` — the OTHER
(canonical, private) repo — not `rulgaurd-public`. `pytest` runs were
unaffected (pyproject.toml's `pythonpath=["src"]` overrides this for
tests), but `streamlit run src/bearing_pdm/dashboard.py` is NOT a
pytest invocation: its internal `from bearing_pdm import dashboard_cross`
resolved through the stale editable link to `data/rlguard`, which does
not have `dashboard_cross.py` at all, crashing with `ImportError` the
moment the Analyze view was opened via a real browser session. **Fixed**
by `pip install -e . --no-deps` from inside `rulgaurd-public` with
`~/.venvs/rulguard/bin/python`, repointing the `.pth` file to this
checkout's `src/`. Verified: `bearing_pdm.__file__` now resolves inside
`rulgaurd-public`; full suite still 973/973 after the fix. This means
**any prior session's browser screenshots taken with `~/.venvs/rulguard`
that exercised the Analyze/universal view must be treated as unverified
provenance** (they may have silently run `data/rlguard`'s code) — this
session's own screenshots, taken after the fix, are the first ones
confirmed to run `rulgaurd-public`'s actual code end-to-end through this
venv. `data/rlguard` itself was never read from or written to beyond
this diagnostic check (standing constraint respected).

### Real UI bundle round-trip (item 3)
Streamlit launched fresh on port 8515, real Playwright + Chromium drove:
1. **Export**: Analyze tab, dataset=femto, bearing=femto:Bearing1_1,
   clicked the real "Export .rulguard.zip" download button -> real
   2,648-byte `femto.rulguard.zip` saved via Playwright's download API
   (not read directly from a Python call). Screenshots:
   `roundtrip_01_analyze.png`, `roundtrip_02_export_done.png`.
2. **Import**: switched to "Legacy FEMTO / College Raw Explorer" ->
   "Input mode" = "RULGuard Analysis Bundle (.rulguard.zip)", uploaded the
   just-exported file via the real `st.file_uploader` widget.
   Screenshot: `roundtrip_04_import_valid_result.png`.
   - **First attempt surfaced a real, previously-undiscovered bug**:
     `bundle_kind()` (`analysis_bundle.py`) checked
     `dataset_id.startswith("femto")` before checking for the routing
     payload shape. `build_routing_bundle("femto", ...)` stores
     `dataset_id = "femto:routing"`, which also starts with `"femto"` -
     so the export/reimport round-trip for FEMTO specifically (not XJTU,
     which is what the existing `test_build_routing_bundle_round_trips_
     and_strips_local_path` test used) silently picked the wrong
     renderer (`_render_femto_bundle` instead of `_render_routing_
     bundle`) and displayed `Bearing: unknown`, `Acquisitions: 0`,
     `Sample rate: 0 Hz` instead of the real data - checksum verification
     still passed (the bundle itself was valid), but the UI showed
     placeholder nulls instead of the real numbers.
   - **Root-caused and fixed**: added an `endswith(":routing")` check
     before the dataset-prefix checks in `bundle_kind()`
     (`src/bearing_pdm/analysis_bundle.py`), plus a regression test
     (`test_bundle_kind_routing_wins_over_femto_college_prefix_collision`,
     `tests/test_analysis_bundle.py`) using the exact femto/college
     collision shape that the existing xjtu-only test didn't cover.
   - **Re-verified after the fix**: the same real browser round-trip now
     shows "Routing bundle for dataset `femto` - 6 bearing(s)", Files
     profiled 8,384, Sampling rate 25,600 Hz - **exactly matching** the
     original Overview tab's numbers before export. Full suite: 973
     passed (972 + 1 new regression test), 0 failed. `ruff check .`:
     clean.
3. **Tampered bundle rejection**: a COPY of the valid export had a byte
   flipped inside `dataset.json` (breaking its checksum), then uploaded
   via the same real file-upload widget. Result:
   `"Bundle rejected: <tmp path>: dataset.json checksum mismatch"` -
   a clean `st.error()` message, **no raw traceback visible in the UI**
   (confirmed via a literal `"Traceback (most recent call last)"`
   substring check on the rendered page text - absent). Screenshot:
   `roundtrip_05_import_tampered_rejected.png`.

**Net for this item: PASS, with one real bug found and fixed** (not
merely re-confirming the already-tested Python-level round-trip - this
is exactly the kind of defect that only a true UI-driven test, not a
library-level test, could have caught, since the collision is specific
to the FEMTO/college dataset names colliding with their own `:routing`
suffix).
