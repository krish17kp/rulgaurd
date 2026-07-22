# RULGuard: Bearing Health Monitoring and Remaining Useful Life Prediction

Research capstone project. Estimates rolling-bearing degradation state and Remaining Useful Life (RUL) from vibration (+ temperature where available) sensor data, and explains predictions with evidence-grounded retrieval. **Research prototype, not a production or safety system.** The LLM/RAG layer never alters the numeric RUL prediction.

## Status (read this first)

- **Accelerated review MVP (deadline 2026-07-25): DONE.** Milestones M0-M4 plus a minimal M8 (Streamlit dashboard) are complete, each backed by a real-data run with evidence under `artifacts/evidence/REVIEW-M*/`.
- **The full M0-M9 capstone is NOT finished.** M5 (degradation-stage classification), M6 (optional 1D-CNN-over-HI), M7 (RAG/local-LLM report generation), and M9 (final reproducibility/scientific audit) are deferred, post-review work. See `docs/milestone.md` and `TODO.md` for the authoritative per-task status.
- Do not read "review-ready" as "feature-complete." It means the reviewed subset is real, tested, and honestly reported — not that every planned capability exists yet.

## Known limitations (stated up front, not buried)

1. The college dataset is a **single bearing run-to-failure trajectory** (129 hourly files, one NSK 6205 bearing). There is no cross-bearing generalization claim from it.
2. College's naive RUL baseline scores a mathematically trivial `MAE=0.0` — this is an identity of how the label is defined on an uncensored single run, **not evidence of a working predictor**. See `docs/decisions.md` D10. Only the `extra_trees` college numbers are real evidence.
3. FEMTO-trained models (fit only on the 6 FEMTO `Learning_set` bearings) are **never applied to college data** — the dashboard explicitly gates on dataset and shows a domain-mismatch message instead of a silently-wrong number (`docs/decisions.md` D11).
4. No physical fault-type diagnosis (inner/outer race, ball, lubrication) is claimed anywhere — this is RUL regression, not fault diagnosis, and bearing-frequency (BPFO/BPFI/BSF/FTF) claims require verified geometry this project does not have.
5. College feature extraction currently uses a 1-in-5 file sample (26/129 files) for the review run, not the full archive — see `reports/verification/review-readiness.md` for why and what a full run would need.
6. `Validation_Set/Full_Test_Set` (FEMTO's hidden RUL continuation) has not been scored yet — the pipeline is frozen but hidden-set evaluation is a deliberately separate later step, not skipped by accident.

## Architecture

Two independent adapters (`femto.py`, `college.py`) normalize into one canonical feature-row contract (`docs/data-contract.md`), features land in Parquet with DuckDB lineage/metadata (never raw high-frequency rows), then health indicator -> RUL model -> Streamlit dashboard. Full diagram and trust boundaries in `docs/architecture.md`.

## Install

```bash
git clone <this-repo-url>
cd rulgaurd   # or wherever you cloned it
pip install -e . --no-deps
pip install -r requirements.txt
# optional, only needed for the deferred M7 RAG work:
pip install -r requirements-rag.txt
```

Requires Python >=3.11 (developed on 3.13). The importable package is `bearing_pdm` (`src/bearing_pdm/`); the distribution/repo name is `rulguard` / `rulgaurd`.

### Datasets

- **College**: 129 hourly `LogFile_*.csv` files, published in this repo under `datasets/college/` via Git LFS. User-collected run-to-failure recording of one NSK 6205 bearing, 128 hours to failure.
- **FEMTO/PRONOSTIA**: `Training_set.zip`, `Test_set.zip`, `Validation_Set.zip`, published under `datasets/femto/` via Git LFS. IEEE PHM 2012 Prognostic Challenge dataset — cite the original challenge if you reuse this data; the archives are redistributed here under the challenge's original terms.

A `git clone` pulls Git LFS pointers for both; run `git lfs pull` (or clone with LFS enabled) to fetch the actual archive/CSV content. FEMTO's zips need local extraction (gitignored, not committed — extracting ~9GB) before the adapters can read them; college's CSVs are used directly from `datasets/college/`.

Copy the config template and point it at your extracted FEMTO folders:

```bash
cp config/data_paths.example.toml config/data_paths.toml
# edit config/data_paths.toml: set femto training_dir/test_dir/validation_dir
# to your local extracted paths; college raw_dir already points at datasets/college
```

`config/data_paths.toml` is gitignored (local paths only, never committed).

## Run

```bash
python scripts/build_features.py --dataset femto --config config/data_paths.toml
python scripts/build_features.py --dataset college --config config/data_paths.toml
python scripts/build_health.py --config config/data_paths.toml
python scripts/train_models.py --config config/data_paths.toml
python scripts/evaluate_models.py --config config/data_paths.toml
python scripts/run_dashboard.py
```

The dashboard loads cached artifacts only — it never trains on page load. `scripts/audit_data.py` is not yet written; the M0/M1 dataset audit was done via direct inspection and is recorded in `docs/dataset-audit.md`, independently re-verified by the adapters' own tests.

## Test

```bash
pytest -q
ruff check .
```

Tests run against tiny committed fixtures in `data/fixtures/` (real excerpts of both datasets) — you don't need the full datasets downloaded to run the test suite.

## Reproducing the review results

See `reports/verification/review-readiness.md` for exact commands, environment, and the real metrics from the last verified run (FEMTO leave-one-bearing-out MAE, college walk-forward MAE, health-indicator comparison). `reports/verification/review-demo-script.md` walks through the same material as a live demo script.

## Methodology

- `docs/prd.md` — problem, goals, non-goals, explicit non-claims.
- `docs/data-contract.md` — canonical feature-row schema both adapters emit.
- `docs/architecture.md` — data flow, trust boundaries, why raw samples stay out of the database.
- `docs/dataset-audit.md` — real file inspection results (schemas, counts, hidden-RUL derivation).
- `docs/decisions.md` — every source conflict and bug found during development, with resolution and evidence, in date order (D1-D12). Read this if you want to know what actually went wrong and how it was caught.
- `docs/milestone.md` / `TODO.md` — per-milestone and per-task status, acceptance criteria, evidence pointers.

## Continuing development

Post-review work is scoped in `docs/milestone.md` (M5 stage classification, M6 optional CNN, M7 RAG/local-LLM, M9 final audit) and tracked task-by-task in `TODO.md`. `CLAUDE.md` documents the non-negotiable rules (no leakage, adapter separation, no fabricated labels/fault claims) that any new work must keep following.

## License and citation

Research/educational capstone code. FEMTO/PRONOSTIA data is the IEEE PHM 2012 Prognostic Challenge dataset — cite the challenge if you reuse it. College dataset is user-collected; cite this repository if you reuse it. No warranty; not validated for production or safety-critical use.
