# Final Implemented Architecture — overnight/capstone/full-dataset-zip-rag

This document records what the Phase D–Z nightshift build added on top of the
`ui-explanation-cleanup` baseline. It does not replace or supersede
`command.md`, `docs/milestone.md`, or `docs/decisions.md` — those remain the
historical record. This is a map of the new data/ZIP/bundle/RAG surface.

## 1. Single-acquisition path (unchanged, pre-existing)

`POST /predict/rul/femto-acquisition` — one FEMTO `acc_*.csv` → features →
HI/applicability → ExtraTrees RUL → reliability block. Regression anchor:
`Bearing2_1/acc_00450.csv` → `rul_seconds=4610.0`, `HIGH`, `FULLY_SUPPORTED`.
Verified unchanged on every phase of this build, including live on the final
Vercel Preview.

## 2. Bearing-ZIP path (Phase F/G)

`src/bearing_pdm/bearing_archive.py::analyze_femto_bearing_zip()` validates a
ZIP of one FEMTO bearing's acquisitions (e.g. `Bearing2_1.zip`) through
`archive.py`'s manifest classification, then runs the *same* `femto.py` /
`pipeline.py` feature extraction, `health.py` HI, and `stages.py` staging used
by the canonical dataset — no duplicated formulas. Held-out RUL predictions
are looked up from `deploy_data/trajectory_data.json`'s leave-one-bearing-out
artifact, never recomputed in-sample. Verified byte-exact against that
artifact for Bearing2_1.

Web: `POST /analyze/femto-bearing-zip` (direct body, ≤4MB) and
`/analyze/femto-bearing-zip/blob` (Vercel Blob, ≤64MB — the real path, since a
full bearing ZIP measures ~18.3MB). Oversized/unsupported input returns
`analysis_bundle_required` rather than timing out. Frontend: `/analyze-bearing-zip`.
Per-acquisition applicability/reliability scoring was **not** added to this
endpoint (scoped out — the existing applicability code is coupled to the
single-acquisition flow); this is a known gap, not a silent omission.

## 3. Full offline FEMTO / College paths (Phase H/I)

- `scripts/inspect_femto_dataset.py` — read-only explorer for a FEMTO role
  directory or raw `datasets/femto/*.zip`. Labels `Full_Test_Set` **FROZEN
  EVALUATION ONLY**.
- Role enforcement: `evaluation.py::assert_no_leakage()` already gated every
  real fit call site (`health.py`, `stages.py`, `applicability.py`,
  `evaluation.py`, `experiments.py`) against `Full_Test_Set`/`test_censored`
  roles. This build closed one gap: `scripts/train_models.py` and
  `scripts/compare_cross_domain_targets.py` now call the guard explicitly as
  defense-in-depth (they were safe by construction via role-column filtering,
  but undefended against a future edit removing that filter).
- `scripts/build_college_trajectory.py` → `deploy_data/college_trajectory.json`
  — a compact whole-run artifact (timeline, RMS/kurtosis/crest-factor/spectral
  trends, temperatures, D10/D11 caveats) built from the already-cached
  per-acquisition feature parquet. **Known coverage limitation, disclosed in
  the artifact itself**: the cached feature parquet only covers 26 of the 129
  raw college files (built with `--sample-stride 5` in an earlier session);
  the artifact's `n_source_files_in_cache`/`n_raw_college_files_on_disk`/
  `coverage_note` fields state this explicitly rather than implying full
  129-file coverage.

## 4. RULGuard Analysis Bundle (Phase J)

`src/bearing_pdm/analysis_bundle.py::build_bundle()`/`load_bundle()` — a
checksummed `.rulguard.zip` container (`manifest.json`/`dataset.json`/
`checksums.json`, SHA256-verified on load, rejects tampered or
schema-mismatched bundles). Generic: holds any dict-shaped derived result
(a FEMTO bearing analysis, the college trajectory, or an evaluation
snapshot) — never raw datasets. Round-trip parity verified for both FEMTO
Bearing2_1 and the college trajectory (loaded values exactly match the
offline source). No web upload endpoint was wired for generic bundles this
pass (`/knowledge/load` exists for the *knowledge* variant — see §6 — but a
general `/bundle/upload` was scoped out).

## 5. Streamlit full research mode (Phase K)

New "Raw / ZIP / Bundle Explorer" sidebar view in `dashboard.py` (the existing
7 views are unchanged): (1) read-only FEMTO-role/college folder browser,
(2) bearing-ZIP upload → `analyze_femto_bearing_zip()` behind an explicit "Run
Analysis" button (never on upload), (3) `.rulguard.zip` upload →
`load_bundle()`. **Known limitation**: modes 2/3 show a compact `st.json`
summary, not full chart-by-chart reuse of the existing Feature-trends/HI/RUL
views — wiring every chart helper to three more data shapes was out of scope
for one pass.

## 6. PDF / multi-document RAG ingestion (Phase L) + Knowledge Bundle (Phase M)

`src/bearing_pdm/rag/ingest.py` — ingests single file / directory / ZIP for
PDF (via existing `pypdf` dependency, no new dependency), Markdown, TXT, and
DOCX (via stdlib `zipfile`+`xml.etree`, no new dependency). ZIP handling
reuses Phase E's `archive.safe_extract_zip`. Incremental by SHA256 (skips
unchanged files), deterministic chunking, per-file status
(`processed`/`unchanged`/`failed`/`unsupported` — never silent drops), real
page numbers for PDF chunks. Separate from `corpus.py`'s curated project-doc
allowlist, which is untouched.

`VectorIndex.save_knowledge_bundle()`/`load_knowledge_bundle()` (in
`retrieval.py`, reusing Phase J's bundle container) package a built index into
a portable `.rulguard-knowledge.zip` — retrieval parity (same chunk order,
same scores) verified between the in-memory and bundle-reloaded index.

## 7. Bounded cloud PDF ingestion (Phase N)

`POST /knowledge/ingest-zip` (direct upload ≤4MB, per-file status report, does
**not** mutate the live `/explain` retrieval index — explicit-rebuild
philosophy) and `POST /knowledge/load` (uploads a pre-built
`.rulguard-knowledge.zip`, checksum-validated, swaps it in as the live index).
Oversized input returns `knowledge_bundle_required`. Backend-only — no
frontend "Add Knowledge" page was built this pass.

## 8. Cross-dataset view (Phase S) — scoped to FEMTO + College

`GET /evaluation/cross-dataset` and frontend `/cross-dataset` page. FEMTO's
leave-one-bearing-out evaluation is shown under **"in-domain trained
results"**; college's chronological walk-forward evaluation is shown under a
**structurally separate** "not zero-shot, single-dataset results" section —
this is a hard separation (distinct JSON keys, distinct page sections), not a
caption, because college is explicitly *not* a zero-shot application of the
FEMTO model (D11) and its naive baseline is an oracle identity (D10), so
averaging it with FEMTO's numbers would misrepresent both. IMS and XJTU-SY
appear as explicit `NOT_YET_AVAILABLE` entries with the real blocker reasons
(see §10) rather than being silently omitted.

## 9. CLI scripts (Phase U) + compute cache (Phase V)

- `scripts/analyze_archive.py` — manifest classification or full bearing-ZIP
  analysis from the command line.
- `scripts/build_analysis_bundle.py` — build a `.rulguard.zip` from a bearing
  ZIP or the college trajectory JSON.
- `scripts/build_knowledge_bundle.py` — ingest a doc corpus → `.rulguard-knowledge.zip`.
- `scripts/evaluate_external_dataset.py` — documented stub for the IMS/XJTU
  zero-shot workflow; refuses to guess dataset structure without real data,
  points at the exact blockers in §10.

All four have working `--help`, no hardcoded machine-specific paths.

`src/bearing_pdm/compute_cache.py::cached_json_call()` — a content-addressed
disk cache (`sha256(raw_input) + version string`, no TTL/eviction) wired into
`analyze_femto_bearing_zip_cached()` with an explicit
`BEARING_ANALYSIS_SCHEMA_VERSION` constant to bump on formula changes. Proven
(not just asserted) to produce identical cached/uncached results and to miss
correctly on input or version changes. College trajectory building (already
0.74s) and RAG index building were **not** wrapped in this cache this pass.

## 10. Scientific limitations

- College trajectory artifact has cached-feature coverage for 26 of 129 raw
  files (disclosed in the artifact, see §3) — not a full-run feature trend in
  the strictest sense, though the chronological walk-forward RUL evaluation
  numbers it reports come from the full, separately-computed evaluation
  pipeline, not from this 26-file sample.
- IMS and XJTU-SY cross-dataset validation (Phase O/P/Q) did not happen this
  run — see Infrastructure Limitations below. The frozen FEMTO model was
  never touched by any code path added in this build (verified by the W/X
  safety audit: `bearing_archive.py`/`analysis_bundle.py` only ever read
  model artifacts via `_load_joblib`, never write/fit).
- No physical fault diagnosis, no claim of cross-machine generalization, no
  real-time deployment claim — all pre-existing project constraints,
  unaffected and unviolated by this build.

## 11. Infrastructure limitations

- **IMS**: real archive downloaded and checksum-verified
  (`IMS.zip`, SHA256 `6cb42c263b0281c725abf99f4b9fcf49915c949f31dbd2333877dc2e06ce9ec2`,
  from `https://data.nasa.gov/docs/legacy/IMS.zip`) but its three experiments
  are packaged as RAR archives, and this environment has no `unrar`/`unar`/
  `7z` and no passwordless `sudo` to install one. **Human action required:**
  run `sudo apt-get install unrar` (or `p7zip-full`) once, then Phase O/P can
  resume immediately using the already-downloaded file.
- **XJTU-SY**: no direct-HTTP mirror exists — all six listed mirrors (Google
  Drive, Dropbox, MediaFire, MEGA, Baidu Netdisk, personal site) require
  interactive browser/JS auth that a non-interactive environment cannot
  complete. **Human action required:** manually download one mirror's files
  through a browser and hand them off.
- **No production deployment of this branch** — by design. A Vercel Preview
  was deployed and verified (see the FINAL STATUS report for the URL); the
  branch has not been promoted to production and production promotion
  remains gated on explicit human approval, as it has been for every prior
  phase of this build.
