# Milestones (M0-M9)

Accelerated review track active (deadline 2026-07-25, today 2026-07-21). Full M0-M9 defined here; M0-M4 + minimal M8 are the review target, M5/M6/M7/M9 continue after.

## M0 - foundation audit (DONE 2026-07-21)
Purpose: verify repo/tooling/data facts before writing feature code.
Deliverables: this doc set, `docs/tooling-inventory.md`, `docs/dataset-audit.md`, folder skeleton, `.gitignore`.
Acceptance: datasets separated, archive roles confirmed against real files, no hidden-test leakage designed in, raw rows never planned for DuckDB.
Evidence: `artifacts/evidence/REVIEW-M0/`.

## M1 - dataset audit and adapters (IN_PROGRESS)
Task IDs: M1-T1 (college adapter), M1-T2 (FEMTO adapter), M1-T3 (parser tests on fixtures).
Model class: general (Sonnet).
Deliverables: `src/bearing_pdm/college.py`, `src/bearing_pdm/femto.py`, `tests/test_college.py`, `tests/test_femto.py`.
Acceptance: bounded-memory chunked reads; schema/delimiter auto-detection; chronological ordering from filenames/timestamps; missing temperature stays explicit; hidden-RUL derivation independently reproduced (already confirmed in `docs/dataset-audit.md`).
Verification: `pytest -q tests/test_college.py tests/test_femto.py`.
Evidence: `artifacts/evidence/REVIEW-M1/`.

## M2 - streaming feature pipeline and feature store
Task IDs: M2-T1 (time/freq/temp feature formulas + tests), M2-T2 (college windowing), M2-T3 (FEMTO acquisition features), M2-T4 (Parquet + DuckDB lineage).
Acceptance: no raw-window explosion, deterministic output, schema version + hashes recorded, zero-denominator/constant-signal tests pass.
Evidence: `artifacts/evidence/REVIEW-M2/`.

## M3 - health-indicator baselines
Task IDs: M3-T1 (transparent HI), M3-T2 (paper-inspired HI, train-fold-only PCA).
Acceptance: train-only fitting, monotonicity/trend evidence, no hidden-test use, one baseline selected or rejection documented.
Evidence: `artifacts/evidence/REVIEW-M3/`.

## M4 - RUL baselines and leakage-safe evaluation
Task IDs: M4-T1 (naive baseline), M4-T2 (tree-based baseline), M4-T3 (grouped FEMTO eval), M4-T4 (college walk-forward).
Acceptance: group/time splits only, no preprocessing leakage, per-bearing metrics, frozen final pipeline before any Full_Test_Set scoring.
Evidence: `artifacts/evidence/REVIEW-M4/`.

## M5 - degradation-stage classification (post-review)
Extra Trees reproduction baseline (30 estimators) + one modest comparison (e.g. 200 estimators), documented label policy, imbalance-aware metrics.

## M6 - optional 1D-CNN-over-HI experiment (post-review, only if M4 evidence justifies it)
One controlled config, one ablation, accept/reject decision vs. classical baseline.

## M7 - RAG and local report generation (post-review)
Ollama `llama3.1:8b` + `nomic-embed-text`, FAISS or NumPy fallback, citation-required retrieval, deterministic template fallback.

## M8 - Streamlit dashboard and PDF
Minimal version required for review (task IDs M8-T1..T4): dataset select, signal/FFT/HI/RUL panels, cached artifact loading, no page-load training.
Full version (post-review): PDF export polish, precomputed model-evaluation page details.
Evidence: `artifacts/evidence/REVIEW-M8/`.

## M9 - reproducibility and final capstone audit (post-review)
Clean-environment run-through, final Ponytail-style simplicity pass, final scientific audit, no stale docs.

## Stop conditions (any milestone)
Archive corruption, schema materially differs from `Description.txt`, units unknown affecting targets, Full_Test_Set RUL derivation mismatch, leakage detected, unsupported fault claim required, third failed implementation attempt, unsafe disk/memory.
