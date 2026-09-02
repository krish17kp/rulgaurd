# RULGuard (bearing_pdm package) - CLAUDE.md

Research capstone, not production. Estimate bearing RUL from vibration data; explain via evidence-grounded RAG. LLM never alters numeric predictions.

## Canonical repo notice
This directory (`data/rlguard`) is the **canonical private working repo** — full git history, real datasets checked out, trained artifacts present. A second, unrelated-history copy exists at `../../rulgaurd-public` (repo root's `rulgaurd-public/`): a single-commit, code-only, no-dataset export generated from this repo via `git archive` for public GitHub distribution (see `docs/decisions.md` D12). Do not confuse the two — treat this repo as source of truth and only regenerate the public export deliberately.

## Environment
The Windows -> Linux migration (2026-08-03) is complete: dependencies installed, `git`/`git-lfs` working, FEMTO archives extracted, paths repointed. `docs/decisions.md` D13 covers the path-separator bug the migration caused (persisted `D:/...`-style paths breaking every reader on Linux) and its fix. See the capstone-root `CLAUDE.md` (`/mnt/NewVolume/capstone/CLAUDE.md`) for the verified interpreter path and installed package versions.

## Source of truth order
1. Actual raw files / reproducible inspection (see `docs/dataset-audit.md`)
2. Official dataset docs and archive structure
3. `context/Description.txt` (college data)
4. Primary papers (`context/*.pdf`)
5. Literature-review draft
6. Original prompt (`command.md`, this repo)

## Non-negotiable rules
- FEMTO and college data stay in separate adapters (`femto.py`, `college.py`); normalize only at the feature-row contract (`docs/data-contract.md`).
- RUL regression (naive baseline + `ExtraTreesRegressor`, the selected primary model) is the current scientific direction. **Do not replace it with an LSTM or any deep-learning model** because the data is time-series-shaped and small per bearing. A CNN comparison (M6) stays a deliberately deferred, opt-in experiment with a stated hypothesis — never an automatic substitution.
- Degradation-stage classification (HEALTHY/DEGRADING/CRITICAL, `stages.py`, M5, done) is a severity band on the health indicator, secondary to RUL, and is NOT physical fault diagnosis — never claim inner/outer-race/ball/lubrication fault without a labeled dataset.
- No leakage: GroupKFold/leave-one-bearing-out for FEMTO, time-ordered expanding-window for college. Fit scalers/PCA/feature-selection/thresholds on train fold only.
- `Validation_Set/Full_Test_Set` (hidden FEMTO continuation) has been scored (M4b, done — `docs/decisions.md` D16/D17/D20). It stays frozen; never refit anything against it now that the result is reported.
- College window default: 25,600 samples (~1s), 50% overlap - not 1024. FEMTO: use the full 2560-sample acquisition, don't subdivide.
- Never label all early windows with the 85degC/9 m/s^2 stop criteria (circular labeling).
- No exact BPFO/BPFI/BSF/FTF claims without verified bearing geometry.
- RAG/LLM explain measured facts + cite sources; never invent facts or override the numeric model.
- Raw sensor rows never enter DuckDB - only Parquet paths + hashes + lineage.

## Health indicator
Three variants exist for scientific comparison, all fit on FEMTO `Learning_set` only: `TransparentHIBaseline`, `PcaHIModel`, and `ReferenceHIModel` (the one degradation stages are calibrated against — it replaced an earlier version that pinned at HI=1.0 for 47.5% of learning acquisitions, D18/D19). See `reports/metrics/health_indicator_comparison.json` for the real comparison numbers.

## Commands
```
# audit_data.py deferred (M0/M1 audit was done by direct inspection, see docs/dataset-audit.md)
python scripts/build_features.py --dataset femto --config config/data_paths.toml
python scripts/build_features.py --dataset college --config config/data_paths.toml --sample-stride 5
python scripts/build_health.py --config config/data_paths.toml
python scripts/train_models.py --config config/data_paths.toml
python scripts/evaluate_models.py --config config/data_paths.toml
python scripts/score_hidden_set.py --config config/data_paths.toml   # post-freeze only, FEMTO hidden set
python scripts/run_dashboard.py
pytest -q
ruff check .
```
Requires `pip install -e . --no-deps && pip install -r requirements.txt` first (see capstone-root `CLAUDE.md` for the verified venv path).

## Folder ownership
- `datasets/college/` - 129 college CSVs, published via Git LFS.
- `datasets/femto/` - FEMTO raw archives (Training/Test/Validation .zip), published via Git LFS. Extract locally (gitignored, not committed) to run the pipeline.
- `context/` - local-only reference (gitignored), read-only. Its ~19GB raw-data subfolders that duplicated `datasets/` byte-for-byte were cleared during the 2026-09-01 repo cleanup pass; `datasets/` is the sole canonical raw-data location now.
- `config/data_paths.toml` - local, gitignored, real paths. Copy from `.example.toml`.
- `data/fixtures/` - tiny committed real-data excerpts for tests only.
- `data/interim/`, `data/processed/` - generated, gitignored.
- `artifacts/` - models (`.joblib`), DuckDB (`metadata.duckdb`), FAISS index (M7, not yet created).
- `reports/` - figures, metrics, PDF.
- `deliverables/review/` - review-day presentation materials (slides, study PDFs, diagrams) — not app code.
- `src/bearing_pdm/` - package code.

## Task states
`TODO | IN_PROGRESS | DONE | BLOCKED_EXTERNAL | BLOCKED_TECHNICAL | DEFERRED | REJECTED`. "Done" requires evidence in `artifacts/evidence/<TASK-ID>/` or a metrics file under `reports/metrics/`, not an agent's say-so.

## Model routing
- Cheapest (Haiku-class): inventory, manifests, doc sync, TODO updates, commit messages.
- General (Sonnet-class): adapters, features, models, Streamlit, tests, debugging.
- Highest reasoning (Opus-class): leakage/methodology audits, hard bugs surviving 2 attempts, final scientific audit.

## Prohibited
Committing secrets/private absolute paths into git history. Committing extracted FEMTO folders or raw high-frequency samples (only the archives in `datasets/femto/` and the LFS-tracked `datasets/college/` CSVs are published). Refitting anything against `Full_Test_Set` now that it's scored (M4b, done). Pushing to GitHub (commit only, user pushes manually).

## Current milestone
M0-M4, M4b, minimal M8, and M5 are **DONE** — see `docs/milestone.md` for acceptance criteria/evidence and `TODO.md` for per-task status; both are kept current and take precedence over this file if they ever disagree. M4b (FEMTO hidden-set/`Full_Test_Set` scoring) and M5 (degradation-stage classification) shipped 2026-08-30, after the review-day (2026-07-25) M0-M4/M8 milestones. **M6 (optional CNN), M7 (RAG/LLM), and M9 (final audit) remain deliberately deferred — no work has started on them.** See `docs/decisions.md` D13-D20 for what was found and fixed getting M4b/M5 done (path-separator bug, ruff version drift, hidden-set scoring bugs, HI pinning defect).
