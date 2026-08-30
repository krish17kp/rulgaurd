# Project Handoff — RULGuard

Reconstructed 2026-08-03 after a Windows -> Linux migration, from direct repo inspection (no prior-session memory available). Source-of-truth order used: real files/artifacts > docs > `command.md` (original prompt). Where this document and an older doc disagree, this one reflects what was actually verified on disk today.

## 1. Purpose and users
Research capstone (not production software): estimate rolling-bearing degradation state and Remaining Useful Life (RUL) from vibration (+ temperature where available) sensor data, and explain predictions with an evidence-grounded RAG layer that never overrides the numeric prediction. Primary audience: faculty evaluators (review held 2026-07-25) and the student researcher demonstrating a leakage-safe, honestly-scoped ML pipeline. A "maintenance engineer" persona shapes dashboard UX only — this is explicitly not a validated deployment target. Full framing: `docs/brd.md` (business) and `docs/prd.md` (product).

## 2. Repository duplication — read this first
Two copies of this project exist on disk:
- **`data/rlguard/` (this repo) — canonical.** Full git history (8 commits, branch `main`, HEAD `fd9273a`), real datasets checked out (`datasets/college/`, `datasets/femto/*.zip`), trained model artifacts, processed Parquet, DuckDB metadata, and `deliverables/review/` presentation materials. All active development happened here.
- **`rulgaurd-public/` (sibling top-level folder) — derived export.** Single commit (`028e216a`, "initial public release... code-only, no raw datasets"), generated from this repo via `git archive` (`docs/decisions.md` D12) for GitHub publishing under the free LFS quota. Its `TODO.md`/`CLAUDE.md` are a stale snapshot frozen at 2026-07-21 — several days behind this repo's real state (BRD, corrected milestone statuses, DB materialization notes added 2026-07-25 only exist here).

**Recommendation:** treat `data/rlguard/` as the working repo going forward. `rulgaurd-public/` should only be regenerated deliberately (fresh `git archive` snapshot) when ready to push a public update — do not hand-edit it to "catch up," that defeats its purpose as a generated artifact.

## 3. Technology stack
- **Language/runtime:** Python >=3.11 (developed on 3.13.7 on Windows; this Linux machine has system Python 3.12.3, compatible but unconfirmed against this specific codebase).
- **Core libs:** numpy, pandas, scipy, scikit-learn, pyarrow, duckdb, joblib, matplotlib, plotly, streamlit, py7zr, reportlab.
- **Dev/test:** pytest, ruff.
- **Optional (M7, not installed anywhere yet):** faiss-cpu, ollama (Python client) — `requirements-rag.txt`. Local Ollama with `llama3.1:8b` + `nomic-embed-text` was verified installed on the old Windows machine (`AGENTS.md`); status on this Linux machine is unknown/unverified.
- **Storage:** Parquet (feature rows) + DuckDB (metadata/lineage only, no ORM) + joblib (sklearn models) + flat files under `reports/`. No SQL server, no ORM, no ORM migrations tool beyond a planned `scripts/migrate_db.py` (not yet written).
- **Frontend:** Streamlit dashboard only (`src/bearing_pdm/dashboard.py`), no separate web frontend/API server.
- **No CI/CD, no Docker/containers, no `.github/` workflows anywhere in the repo** — this is a local-first solo research project, run entirely from the CLI.

## 4. Architecture and major components
Two independent, format-specific adapters normalize into one shared feature-row contract; everything downstream is dataset-agnostic.

```
datasets/femto/*.zip (extracted locally) --> femto.py   --\
datasets/college/*.csv (Git LFS)         --> college.py --> canonical feature-row contract (docs/data-contract.md, v1)
                                                              |
                                                              v
                                                   Parquet feature store (data/processed/)
                                                              |
                                                              v
                                            DuckDB metadata/lineage (artifacts/metadata.duckdb)
                                                              |
                                                              v
                                    health.py (transparent + PCA-based HI) --> modeling.py (naive + ExtraTrees RUL)
                                                              |
                                                              v
                                              evaluation.py (leave-one-bearing-out / walk-forward)
                                                              |
                                                              v
                                     dashboard.py (Streamlit: signal/FFT/HI/RUL/metrics/limits tabs)
                                                              |
                                                    [deferred] FAISS retrieval --> Ollama/template report (M7)
```
Source: `docs/architecture.md`, `docs/database-structure.md`.

Module sizes (`src/bearing_pdm/`, 1,464 lines total): `dashboard.py` 237, `health.py` 219, `pipeline.py` 194, `features.py` 178, `femto.py` 164, `college.py` 110, `storage.py` 124, `evaluation.py` 94, `modeling.py` 93, `config.py` 48, `__init__.py` 3.

**Key design decision:** raw high-frequency sensor rows never enter DuckDB (would defeat "bounded memory" — full college run is ~18GB). DuckDB holds only IDs, schema version, Parquet paths, and checksums.

## 5. Data flow (frontend/backend/DB/API)
There is no client-server API in the usual sense — this is a batch pipeline + local dashboard:
1. `scripts/build_features.py --dataset {femto|college}` reads raw files via the matching adapter, in bounded-memory chunks, and writes a versioned Parquet batch + registers it in DuckDB (`feature_batches`, `acquisitions` tables).
2. `scripts/build_health.py` fits health-indicator models (transparent + PCA) on FEMTO `Learning_set` only, writes `artifacts/models/{transparent_hi_baseline,pca_hi_model}.joblib` and `reports/figures/hi_*.png` + `reports/metrics/health_indicator_comparison.json`.
3. `scripts/train_models.py` fits naive + ExtraTrees RUL regressors, writes `artifacts/models/rul_*.joblib` + `rul_selected_model.json`.
4. `scripts/evaluate_models.py` runs leave-one-bearing-out (FEMTO) and walk-forward (college) evaluation, writes `reports/metrics/rul_evaluation.json`.
5. `scripts/run_dashboard.py` launches Streamlit, which **reads cached Parquet/DuckDB/joblib artifacts only** — it never trains on page load, and gates HI/RUL tabs to FEMTO data only (college shows an explicit domain-mismatch message rather than a wrong number — see D11 in section 7).

## 6. Fully completed features (real-data evidence, not just code existing)
All backed by `artifacts/evidence/REVIEW-M{0,1,2,3,4,8}/summary.md`:
- **M0** — foundation docs, dataset audit (`docs/dataset-audit.md`), decisions log.
- **M1** — FEMTO adapter (6-col accel + 5-col temp, delimiter auto-detect, nearest-wall-clock temp alignment) and college adapter (chunked, header-detecting, NaN-tolerant), both with fixture-based tests.
- **M2** — feature pipeline (time/freq/temp formulas) + Parquet/DuckDB store. FEMTO: 7,534 acquisitions, all 6 learning bearings, full row counts. College: 4,030 windows from a **1-in-5 file sample (26/129 files)**, not the full run.
- **M3** — health indicator: transparent HI selected over PCA HI (mean trend_corr −0.5255 vs −0.4648), both fit train-fold-only.
- **M4** — RUL baselines with leakage-safe evaluation. FEMTO LOBO mean MAE: naive 6,584.8s vs **ExtraTrees 5,061.0s (selected, beats naive)**. College walk-forward ExtraTrees MAE: 116,657s / 118,904s / 131,762s across 3 expanding-window folds (naive baseline here is a documented **MAE=0.0 mathematical identity, not a real result** — see D10).
- **M8 (minimal)** — Streamlit dashboard, 5 tabs, real screenshots under `reports/figures/dashboard_*.png`, one real bug found and fixed via screenshot (D11, FEMTO-fit models were being silently applied to college data).
- **Document alignment pass (2026-07-25)** — every doc cross-checked against real code/artifacts; corrected `docs/milestone.md` status markers and `docs/database-schema.md` materialization claims; added `docs/brd.md`. See `deliverables/review/DOCUMENT_ALIGNMENT_REVIEW.md`.
- Test suite: 72 tests passing as of the last verified run (`pytest -q`), `ruff check .` clean. **Not re-verified on this Linux machine yet** — no dependencies installed (see section 8/11).

Test coverage by file (`tests/`, 896 lines total): college, dashboard, evaluation, features, femto, health, modeling, pipeline, storage — one test file per corresponding `src/bearing_pdm/` module, plus dashboard-specific tests.

## 7. Partially implemented / broken / known-limited
- **College feature batch is a 1-in-5 sample (26/129 files)**, not the full run — a background full-129-file job was killed by the environment twice on the old machine (documented, not silently skipped).
- **`Full_Test_Set` (FEMTO hidden RUL continuation) has never been scored.** The pipeline is frozen and ready; scoring it is a deliberately separate, not-yet-taken step — this is the single highest-scientific-value remaining task.
- **College naive RUL baseline is a mathematical identity (MAE=0.0)**, not a working predictor — a labeling-definition artifact fully documented in `docs/decisions.md` D10. Never quote it as a result.
- **FEMTO-fit HI/RUL models are never applied to college data** — the dashboard deliberately gates on `dataset_id` and shows a mismatch message instead (D11), rather than a silently-wrong chart.
- **No physical fault-type diagnosis anywhere** (inner/outer race, ball, lubrication) — explicit non-claim; bearing geometry for BPFO/BPFI/BSF/FTF is not verified.
- **DuckDB schema is only ~50% materialized**: `schema_version`, `datasets` (2 rows), `bearing_runs` (7 rows), `acquisitions` (11,564 rows), `feature_batches` (2 rows) exist. `model_runs`, `evaluation_metrics`, `predictions`, `knowledge_documents`, `retrieval_events`, `generated_reports` are designed (`docs/database-schema.md`) but not yet created — metrics currently live as JSON under `reports/metrics/` instead.
- **`scripts/audit_data.py` was never written** as a standalone script — the M0/M1 audit was done via direct manual inspection, independently re-verified through the adapters' own tests. Documented gap, not a silent one.
- **Post-review milestones not started:** M5 (degradation-stage classification), M6 (optional 1D-CNN-over-HI), M7 (RAG/local-LLM report generation via Ollama + FAISS), M9 (final reproducibility/scientific audit).
- **No uncertainty interval on the RUL point estimate.**

## 8. Important technical decisions and constraints
All in `docs/decisions.md` (D1–D12) — read this file for the full "what went wrong and how it was caught" trail (12 documented findings). Highlights:
- No leakage: leave-one-bearing-out for FEMTO, strict chronological walk-forward for college; runtime assertions reject non-compliant splits (`evaluation.py`).
- `Validation_Set/Full_Test_Set` never used for fitting, only for final frozen-model scoring (not yet done).
- Missing temperature/vibration values are preserved as explicit NaN with an availability flag — never fabricated, never globally imputed (D6, D7).
- College window default is 25,600 samples (~1s) at 50% overlap — not 1024. FEMTO uses the full 2,560-sample acquisition, never subdivided.
- **D12 (2026-07-21):** this repo used to be two separate repos (a GitHub-hosted dataset repo and a local-only app repo) — they were merged with full history preserved, and this became the single canonical repo. `rulgaurd-public/` is the *new* public-facing export created after that merge (see section 2).
- Constraint: tight local disk (~19–21GB free after both datasets are materialized via LFS) — avoid creating further large local duplicates of the datasets.

## 9. Setup, build, test, run commands
```bash
# One-time setup (NOT yet done on this Linux machine):
pip install -e . --no-deps
pip install -r requirements.txt
# optional, M7 only:
pip install -r requirements-rag.txt

# Pipeline (needs config/data_paths.toml pointed at real local paths first):
python scripts/build_features.py --dataset femto --config config/data_paths.toml
python scripts/build_features.py --dataset college --config config/data_paths.toml --sample-stride 5
python scripts/build_health.py --config config/data_paths.toml
python scripts/train_models.py --config config/data_paths.toml
python scripts/evaluate_models.py --config config/data_paths.toml
python scripts/run_dashboard.py     # streamlit run src/bearing_pdm/dashboard.py under the hood

# Tests (need only fixtures in data/fixtures/, no full dataset required):
pytest -q
ruff check .
```
Last verified run (Windows, 2026-07-21): `pytest -q` → 72 passed, 1 unrelated Streamlit/Altair deprecation warning; `ruff check .` → all checks passed.

## 10. Environment variables and external services
- **No `.env` file or environment-variable-driven config anywhere** — configuration is entirely via `config/data_paths.toml` (local paths, gitignored) and `config/project.example.toml`/`config/data_paths.example.toml` (committed templates).
- **External services:** none required for the review-scope pipeline (fully local/offline). Optional, deferred (M7 only): local **Ollama** server (`llama3.1:8b` generation model, `nomic-embed-text` embedding model) for RAG report generation — was installed and verified on the old Windows machine; status on this Linux machine unverified. No API keys, no cloud dependencies anywhere in the reviewed scope.
- `config/data_paths.toml` currently contains **stale Windows paths** (`D:/capstone/data/...`) for FEMTO training/test/validation dirs — will need Linux-equivalent paths before the pipeline can run here. College's `raw_dir` should just work once repointed at `datasets/college` (relative, matches the committed example).

## 11. Security, performance, maintainability concerns
- **Security:** no auth, no user input surface, no secrets in the repo (confirmed no `.env`/API keys present; `config/data_paths.toml` is gitignored specifically to keep private absolute paths out of history). Not a concern area for this project's current scope.
- **Performance/robustness:** bounded-memory chunked reads are a hard design constraint (a full college CSV is ~2M rows/~64MB in memory) — deviating from chunked processing anywhere is a regression, not an optimization.
- **Maintainability:** the project's own verification discipline is unusually strong for a solo capstone — 12 documented real bugs caught by testing against real data, a document-alignment pass that cross-checks every doc against actual artifacts rather than trusting prose. Keep this habit: any new claim in a doc should trace to a generated metric or an inspected file.
- **Current environment risk:** this Linux machine has **no dependencies installed and no `git` CLI available** (checked `PATH`, `dpkg -l`, `snap list` — absent; only unrelated `gitdiff`/`gitdiffview` binaries found in `/usr/bin`). Until both are installed, nothing in section 9 can actually run, and there is no way to get `git log`/`git status`/`git diff` output — repo state above was reconstructed by reading `.git/HEAD`, `.git/logs/HEAD`, and `.git/config` directly.

## 12. Most likely previous stopping point
The last commit (`fd9273a`, 2026-07-25, "docs: add BRD, fix milestone statuses, note DB materialization state") corresponds exactly to the review-day document-alignment pass (`deliverables/review/DOCUMENT_ALIGNMENT_REVIEW.md`). That document's own "most important work remaining" list (Full_Test_Set scoring, full 129-file college run, M7 RAG, M5 stage classification, M9 final audit) was written the same day and nothing in the repo suggests any of it was started afterward. The project was almost certainly paused right after the review, then the machine was migrated from Windows to Linux, and no development has resumed here yet — this handoff/onboarding session is the first activity on the new machine.

## 13. Correct logical next steps
In order of what unblocks the most:
1. **Get the environment usable again**: install `git` (+ `git-lfs`, though LFS content is already checked out so it's lower priority), create a venv, `pip install -e . --no-deps && pip install -r requirements.txt`, confirm `pytest -q` and `ruff check .` still pass unmodified on Linux/Python 3.12.
2. **Repoint `config/data_paths.toml`** at Linux paths and extract the FEMTO zips locally (college already resolves via the relative `datasets/college` path).
3. **Sanity-check the dashboard** launches against the already-present cached artifacts (`data/processed/*.parquet`, `artifacts/models/*.joblib`, `artifacts/metadata.duckdb`) without needing to rerun the full pipeline.
4. Decide with the user: resume post-review capstone work (M5/M6/M7/M9, full college run, hidden-set scoring — see `deliverables/review/DOCUMENT_ALIGNMENT_REVIEW.md` §"Most important work remaining") or treat the review-MVP as the finish line.
5. If continuing: `Full_Test_Set` hidden-RUL scoring is the highest-scientific-value single next task (frozen pipeline exists, just needs to be run and reported).
6. Decide whether `rulgaurd-public/` needs a fresh `git archive` regeneration to catch up to this repo's current state, or whether it's being left as a point-in-time public snapshot deliberately.

## 14. Uncertainties that cannot be proven from the repository alone
- Whether the user wants to resume the deferred M5–M9 work, or the capstone is effectively "done" at the review-MVP level for grading purposes.
- Whether Ollama (and the `llama3.1:8b`/`nomic-embed-text` models) is installed on this Linux machine — `AGENTS.md` only confirms it was installed on the old Windows machine.
- Whether the exact same dependency versions are still appropriate on Python 3.12 (vs. the original 3.13.7) — no `requirements.txt` version pins exist (all bare package names), so this is low-risk but unverified.
- Whether `rulgaurd-public/` has an actual GitHub remote already pushed to, or is still purely local — `.git/config` in that folder was not inspected for a remote URL as part of this pass.
- The exact intended relationship going forward between `context/` (gitignored local reference material, includes literature review and papers) and `deliverables/review/` (presentation materials) — both look like personal/output material rather than app code, correctly excluded from the git-tracked "code" surface, but their long-term retention policy isn't stated anywhere.
