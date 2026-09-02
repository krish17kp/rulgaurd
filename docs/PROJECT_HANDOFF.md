# Project Handoff — RULGuard

Source-of-truth order: real files/artifacts > `docs/milestone.md` / `TODO.md` / `docs/decisions.md` > this doc > `command.md` (original prompt). Where this document and an older doc disagree, trust the former.

## Repository duplication — read this first

Two copies of this project exist on disk:
- **`data/rlguard/` (this repo) — canonical.** Full git history, real datasets checked out (`datasets/college/`, `datasets/femto/*.zip`), trained model artifacts, processed Parquet, DuckDB metadata, `deliverables/review/` presentation materials. All active development happens here.
- **`rulgaurd-public/` (sibling top-level folder) — derived export.** Single-commit, code-only, no-dataset snapshot generated via `git archive` (`docs/decisions.md` D12) for GitHub publishing under the free LFS quota. Regenerate deliberately when ready to publish; never hand-edit it to "catch up."

## Technology stack

Python >=3.11. Core libs: numpy, pandas, scipy, scikit-learn, pyarrow, duckdb, joblib, matplotlib, plotly, streamlit, py7zr, reportlab (`requirements.txt`); pytest + ruff for dev/test. Optional, M7-only, not installed: faiss-cpu, ollama (`requirements-rag.txt`). Storage: Parquet (features) + DuckDB (metadata/lineage only) + joblib (models) + flat JSON under `reports/metrics/`. Frontend: Streamlit only, no API server. No CI/CD, no containers.

## Architecture

```
datasets/femto/*.zip (extracted locally) --> femto.py   --\
datasets/college/*.csv (Git LFS)         --> college.py --> canonical feature-row contract (docs/data-contract.md, v1)
                                                              |
                                                   Parquet feature store (data/processed/)
                                                              |
                                            DuckDB metadata/lineage (artifacts/metadata.duckdb)
                                                              |
                          health.py (transparent + PCA + reference HI) --> modeling.py (naive + ExtraTrees RUL)
                                                              |
                                     stages.py (HEALTHY/DEGRADING/CRITICAL severity band)
                                                              |
                                        evaluation.py (leave-one-bearing-out / walk-forward / hidden-set)
                                                              |
                                 dashboard.py (Streamlit: signal/FFT/HI/RUL/stage/metrics/limits tabs)
                                                              |
                                                    [deferred] FAISS retrieval --> Ollama/template report (M7)
```
Source: `docs/architecture.md`, `docs/database-structure.md`.

## DONE

- **M0-M4 + minimal M8** (review-day, 2026-07-25): foundation docs, both adapters, feature pipeline, health-indicator baselines, RUL baselines with leakage-safe evaluation, Streamlit dashboard. Evidence: `artifacts/evidence/REVIEW-M{0,1,2,3,4,8}/`.
- **M4b** (2026-08-30): FEMTO hidden-set (`Full_Test_Set`) scoring — the project's only genuinely out-of-sample result. ExtraTrees MAE 4,555s vs. naive 5,204s (naive's earlier "9,459s" framing was itself a bug, corrected per D20), PHM2012 score 0.068 vs. 0.029. `docs/decisions.md` D16/D17/D20.
- **M5** (2026-08-30): degradation-stage classification (HEALTHY/DEGRADING/CRITICAL), gated behind fixing a health-indicator defect that pinned 47.5% of learning acquisitions at HI=1.0. `docs/decisions.md` D18/D19.
- Windows -> Linux migration issues (persisted-path separators, ruff version drift): fixed. `docs/decisions.md` D13/D14.

## CURRENT (known, real limitations — not silently missing)

- College feature extraction still uses a 1-in-5 file sample (26/129 files), not the full run.
- College naive RUL baseline is a mathematical identity (MAE=0.0 on the review-scope evaluation) — never quote it as a real result (D10).
- FEMTO-fit HI/RUL models are never applied to college data — the dashboard gates on `dataset_id` and shows a mismatch message instead of a wrong number (D11).
- No physical fault-type diagnosis anywhere; stage labels are a severity band, not a fault type.
- DuckDB schema is ~50% materialized (`schema_version`, `datasets`, `bearing_runs`, `acquisitions`, `feature_batches` exist; `model_runs`, `evaluation_metrics`, `predictions`, `knowledge_documents`, `retrieval_events`, `generated_reports` are designed in `docs/database-schema.md` but not created — metrics live as JSON instead).
- `context/` (local-only, gitignored reference material) previously duplicated ~19GB of raw data already published in `datasets/` — cleared during the 2026-09-01 repo cleanup pass; `datasets/` remains the sole canonical raw-data location.

## NEXT (deliberately deferred, in the order that unblocks the most)

1. Full 129-file college run (currently 1-in-5 sampled) — re-run `build_features.py --dataset college` without `--sample-stride` if pursued.
2. **M6** — optional 1D-CNN-over-HI comparison against the classical baseline, one controlled config + ablation, only if M4/M4b evidence justifies it. Not a replacement for ExtraTrees.
3. **M7** — RAG/local-LLM report generation (Ollama + FAISS or NumPy fallback). Not installed on this machine.
4. **M9** — final reproducibility/scientific audit, clean-environment run-through, final simplicity pass.
5. Decide whether `rulgaurd-public/` needs a fresh `git archive` regeneration to catch up to this repo's current state.

## Uncertainties that can't be resolved from the repo alone

- Whether the user wants to resume M6-M9, or the review-MVP + M4b/M5 is the finish line for grading purposes.
- Whether Ollama is installed on this machine (capstone-root `CLAUDE.md` says no, as of its last verification).
