# PRD - bearing_pdm

## Problem
Rolling-bearing failure is a leading cause of unplanned rotating-machinery downtime. This capstone estimates degradation state and Remaining Useful Life (RUL) from vibration (+ temperature where available) and explains predictions with cited evidence.

## Users
- Student researchers (this capstone).
- Faculty evaluators (review 2026-07-25).
- Maintenance engineers (illustrative persona for the dashboard/report UX, not a validated deployment).

## Decisions supported
Whether a bearing trajectory is degrading, roughly how much life remains, and what evidence supports that estimate - for academic evaluation, not field deployment.

## Goals
- Leakage-safe RUL regression on FEMTO (grouped/leave-one-bearing-out) and the college run (time-ordered walk-forward).
- Transparent + paper-inspired health indicators, compared quantitatively.
- Secondary degradation-stage classifier, clearly separated from fault diagnosis.
- Evidence-grounded RAG + local LLM (Ollama) report layer with deterministic fallback.
- Streamlit dashboard demonstrating the full path end to end.

## Non-goals
- Production deployment, real-time industrial integration, safety certification.
- Physical fault-type diagnosis (inner/outer race, ball, lubrication) without labeled data.
- Cross-bearing generalization claims from the single college trajectory.

## Functional requirements
- FR1 Discover and parse FEMTO acceleration (2560x6, no header) and temperature (600ish x5, comma or semicolon) files per bearing/condition.
- FR2 Discover and parse 129 college hourly CSVs (headerless, 4 cols, ~2,000,001 rows) in bounded-memory chunks.
- FR3 Extract time/frequency/temperature features per acquisition (FEMTO) or per 25,600-sample/50%-overlap window (college).
- FR4 Build and compare transparent + paper-inspired health indicators, training-fold-only fitted.
- FR5 Train and evaluate >=1 baseline RUL regressor with grouped/time-ordered splits; report MAE/RMSE per bearing.
- FR6 Train and evaluate a degradation-stage classifier with documented label policy.
- FR7 Retrieve cited evidence from traceable sources and generate a report (Ollama or deterministic template) that never changes the numeric RUL.
- FR8 Streamlit dashboard: dataset select, raw signal, FFT, features, HI, RUL, metrics, evidence, report, PDF download.

## Non-functional requirements
- Bounded memory: never load a full 143MB college CSV or the full FEMTO archive tree at once.
- Deterministic: fixed seeds, versioned feature schema, reproducible metrics.
- Local-first: no cloud dependency required for the review build.
- Graceful degradation: dashboard works without Ollama/FAISS.

## Scientific-validity requirements
No random window/acquisition splitting across train/test within a trajectory. No fitting on the hidden `Full_Test_Set`. No manufactured labels from the same stop-criteria used as the prediction target. All bearing-frequency claims gated on verified geometry (currently NOT verified - ball count/diameter/pitch/contact angle absent from `Description.txt` for the college bearing beyond model number NSK 6205).

## User stories
- As a faculty evaluator, I select a bearing sample and see its predicted RUL with supporting metrics, without waiting for training.
- As a student, I can rerun `pytest` and every feature formula test passes on tiny committed fixtures.

## MVP scope (accelerated review track, due 2026-07-25)
M0 foundation -> M1 adapters -> M2 features -> M3 health indicator -> M4 RUL baseline -> minimal M8 dashboard. See `docs/milestone.md`.

## Optional research scope (post-review)
M5 stage classification polish, M6 1D-CNN-over-HI experiment, M7 full RAG, M9 final audit/reproducibility pass.

## Success metrics
- FEMTO: naive baseline beaten by >=1 tree-based model on grouped MAE.
- College: walk-forward MAE trend improves over the naive linear-life baseline on at least one held-out late segment.
- All committed feature-formula and parser tests pass on fixtures.
- Dashboard starts, loads cached artifacts, renders all required panels without training on page load.

## Limitations
Single college bearing = one trajectory, no cross-bearing generalization. FEMTO stage labels are training-derived (partially circular if reused as classifier features - documented per case). Hidden `Full_Test_Set` RULs independently re-derived and matched command.md's expected table (see `docs/dataset-audit.md`) but that table itself is not a primary source - treat as a cross-check, not ground truth on its own.

## Privacy
No personal data. College-bearing data has no PII. Absolute local paths must never be committed (see `.gitignore`, `config/data_paths.toml`).

## Licensing
FEMTO/PRONOSTIA: IEEE PHM 2012 Challenge dataset, cite per `context/` papers; archives published in `datasets/femto/` under the challenge's original terms. College dataset: user-collected, published in `datasets/college/` via Git LFS in this repo (see `docs/decisions.md` D12 for the repo consolidation).

## Risks
See `docs/risk-register.md` (to be expanded post-review). Data drive is tight (~19-21GB free after publishing both datasets via LFS + restoring the college working-tree checkout) - avoid further large local duplicates. Redundant local (non-repo) copies of both datasets still exist outside this repo at `D:/capstone/data/`; left untouched per the no-delete policy, not part of this repo.

## Acceptance criteria
Each milestone's own gate in `docs/milestone.md`.

## Explicit non-claims
No guaranteed physical root-cause diagnosis. No production safety certification. No cross-bearing validation from the single college run. No LLM-generated numeric prediction. No real-time industrial deployment.
