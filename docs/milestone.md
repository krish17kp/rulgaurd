# Milestones (M0-M9)

Accelerated review track (deadline 2026-07-25). Full M0-M9 defined here; M0-M4 + minimal M8 are the review target (all DONE, evidence under `artifacts/evidence/REVIEW-M*/`), M5/M6/M7/M9 continue after. Per-task status and commit SHAs: `TODO.md`.

## M0 - foundation audit (DONE 2026-07-21)
Purpose: verify repo/tooling/data facts before writing feature code.
Deliverables: this doc set, `docs/dataset-audit.md`, folder skeleton, `.gitignore`.
Acceptance: datasets separated, archive roles confirmed against real files, no hidden-test leakage designed in, raw rows never planned for DuckDB.
Evidence: `artifacts/evidence/REVIEW-M0/`.

## M1 - dataset audit and adapters (DONE 2026-07-21)
Task IDs: M1-T1 (college adapter), M1-T2 (FEMTO adapter), M1-T3 (parser tests on fixtures).
Model class: general (Sonnet).
Deliverables: `src/bearing_pdm/college.py`, `src/bearing_pdm/femto.py`, `tests/test_college.py`, `tests/test_femto.py`.
Acceptance: bounded-memory chunked reads; schema/delimiter auto-detection; chronological ordering from filenames/timestamps; missing temperature stays explicit; hidden-RUL derivation independently reproduced (already confirmed in `docs/dataset-audit.md`).
Verification: `pytest -q tests/test_college.py tests/test_femto.py`.
Evidence: `artifacts/evidence/REVIEW-M1/`.

## M2 - streaming feature pipeline and feature store (DONE 2026-07-21)
Task IDs: M2-T1 (time/freq/temp feature formulas + tests), M2-T2 (college windowing), M2-T3 (FEMTO acquisition features), M2-T4 (Parquet + DuckDB lineage).
Acceptance: no raw-window explosion, deterministic output, schema version + hashes recorded, zero-denominator/constant-signal tests pass.
Evidence: `artifacts/evidence/REVIEW-M2/`.

## M3 - health-indicator baselines (DONE 2026-07-21)
Task IDs: M3-T1 (transparent HI), M3-T2 (paper-inspired HI, train-fold-only PCA).
Acceptance: train-only fitting, monotonicity/trend evidence, no hidden-test use, one baseline selected or rejection documented.
Evidence: `artifacts/evidence/REVIEW-M3/`.

## M4 - RUL baselines and leakage-safe evaluation (DONE 2026-07-21)
Task IDs: M4-T1 (naive baseline), M4-T2 (tree-based baseline), M4-T3 (grouped FEMTO eval), M4-T4 (college walk-forward).
Acceptance: group/time splits only, no preprocessing leakage, per-bearing metrics, frozen final pipeline before any Full_Test_Set scoring.
Evidence: `artifacts/evidence/REVIEW-M4/`.

## M4b - FEMTO hidden-set (Full_Test_Set) scoring (DONE 2026-08-30)
The step M4 deliberately deferred: score the frozen pipeline on the 11 censored
test bearings, whose RUL it has never seen. This is the project's only genuinely
out-of-sample evaluation - everything before it was leave-one-bearing-out over
the same 6 learning bearings.
Deliverables: `scripts/score_hidden_set.py`, `evaluation.score_hidden_set` /
`summarize_hidden_set` / `phm2012_score`, `femto.derive_hidden_rul_seconds`,
`reports/metrics/hidden_set_evaluation.json`.
Acceptance: ground truth re-derived from the archives and cross-checked against
the official table before scoring; one prediction per bearing at the last
censored acquisition; official PHM2012 scoring function verified against primary
sources before use.
Result: ExtraTrees MAE **4,555 s** vs naive **5,204 s** (~1.14x better), PHM2012
score **0.068** vs 0.029. Beats the baseline out-of-sample, but absolute accuracy
is poor, the margin over naive is narrow, and 8/11 predictions err in the unsafe
(over-estimate) direction (naive over-estimates 4/11).
See `docs/decisions.md` D16 (result and diagnosis), D17 (Bearing1_4 ground-truth
conflict, and the verified scoring formula), and D20 (Review 2: the naive baseline
above was computed on a single-row frame with no history, collapsing its elapsed-time
term to 0 and understating naive's accuracy at MAE 9,459 s / a false 2.08x margin -
corrected here).

## M5 - degradation-stage classification (DONE 2026-08-30)
Purpose: turn the health indicator into an actionable severity band.
Blocked until 2026-08-30 by the HI defect in `docs/decisions.md` D18 - a severity band on an
indicator that was pinned at 1.0 for 88% of two bearings' lives would have been meaningless.

Deliverables: `src/bearing_pdm/health.py` reference HI (D18), `src/bearing_pdm/stages.py`
(HEALTHY / DEGRADING / CRITICAL), stage badge on the dashboard, `tests/test_stages.py`.
Label policy: `hi_warn` is a genuine fitted quantile of the training bearings' own healthy-window
HI (5th percentile). `hi_critical` (end-of-life median) is computed from data but is not an
independent fit in the same sense - the reference HI's fixed logistic steepness pins the
end-of-life score near a constant (~0.047) regardless of the training set, so `hi_critical`
clusters there across every leave-one-bearing-out fold (see `docs/decisions.md` D20). Plus a
5-acquisition persistence rule. `rul_seconds` is never used to fit a boundary - only
afterwards to score the result.
Acceptance: HI pinning at 1.0 is 0.00% on every learning bearing (was 47.5% mean); every
bearing reaches CRITICAL before failure under leave-one-bearing-out calibration; thresholds
fit on train only; `stage_label` stays out of the RUL feature matrix.
Evidence: `reports/metrics/health_indicator_comparison.json`, `docs/decisions.md` D18/D19.
Not claimed: a stage is a severity band, **not** a fault type. Warning lead time ranges from
14,740 s down to 120 s (Bearing3_1) because FEMTO degradation is flat-then-cliff - reported,
not hidden.

## M6 - optional 1D-CNN-over-HI experiment (post-review, only if M4 evidence justifies it)
One controlled config, one ablation, accept/reject decision vs. classical baseline.

## M7 - RAG and local report generation (post-review)
Ollama `llama3.1:8b` + `nomic-embed-text`, FAISS or NumPy fallback, citation-required retrieval, deterministic template fallback.

## M8 - Streamlit dashboard and PDF (minimal DONE 2026-07-21)
Minimal version required for review (task IDs M8-T1..T4): dataset select, signal/FFT/HI/RUL panels, cached artifact loading, no page-load training.
Full version (post-review): PDF export polish, precomputed model-evaluation page details.
Evidence: `artifacts/evidence/REVIEW-M8/`.

## M9 - reproducibility and final capstone audit (post-review)
Clean-environment run-through, final Ponytail-style simplicity pass, final scientific audit, no stale docs.

## Stop conditions (any milestone)
Archive corruption, schema materially differs from `Description.txt`, units unknown affecting targets, Full_Test_Set RUL derivation mismatch, leakage detected, unsupported fault claim required, third failed implementation attempt, unsafe disk/memory.
