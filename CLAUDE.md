# bearing_pdm - CLAUDE.md

Research capstone, not production. Estimate bearing RUL from vibration data; explain via evidence-grounded RAG. LLM never alters numeric predictions.

## Source of truth order
1. Actual raw files / reproducible inspection (see `docs/dataset-audit.md`)
2. Official dataset docs and archive structure
3. `context/Description.txt` (college data)
4. Primary papers (`context/*.pdf`)
5. Literature-review draft
6. Original prompt (`command.md` in the sibling data-collection-git repo)

## Non-negotiable rules
- FEMTO and college data stay in separate adapters (`femto.py`, `college.py`); normalize only at the feature-row contract (`docs/data-contract.md`).
- RUL regression is the primary task. Stage classification (Healthy/Warning/Critical/Failed) is secondary and is NOT physical fault diagnosis - never claim inner/outer-race/ball/lubrication fault without a labeled dataset.
- No leakage: GroupKFold/leave-one-bearing-out for FEMTO, time-ordered expanding-window for college. Fit scalers/PCA/feature-selection/thresholds on train fold only.
- `Validation_Set/Full_Test_Set` (hidden FEMTO continuation) is evaluated only after the pipeline is frozen. Never used to fit anything.
- College window default: 25,600 samples (~1s), 50% overlap - not 1024. FEMTO: use the full 2560-sample acquisition, don't subdivide.
- Never label all early windows with the 85degC/9 m/s^2 stop criteria (circular labeling).
- No exact BPFO/BPFI/BSF/FTF claims without verified bearing geometry.
- RAG/LLM explain measured facts + cite sources; never invent facts or override the numeric model.
- Raw sensor rows never enter DuckDB - only Parquet paths + hashes + lineage.

## Commands
```
python scripts/audit_data.py --config config/data_paths.toml
python scripts/build_features.py --dataset femto --config config/data_paths.toml
python scripts/build_features.py --dataset college --config config/data_paths.toml
python scripts/train_models.py --config config/data_paths.toml
python scripts/evaluate_models.py --config config/data_paths.toml
python scripts/run_dashboard.py
pytest -q
ruff check .
```

## Folder ownership
- `context/` - local-only reference (gitignored). Read-only.
- `config/data_paths.toml` - local, gitignored, real paths. Copy from `.example.toml`.
- `data/fixtures/` - tiny committed real-data excerpts for tests only.
- `data/interim/`, `data/processed/` - generated, gitignored.
- `artifacts/` - models, DuckDB, FAISS index (mostly gitignored).
- `reports/` - figures, metrics, PDF (gitignored contents).
- `src/bearing_pdm/` - package code.

## Task states
`TODO | IN_PROGRESS | DONE | BLOCKED_EXTERNAL | BLOCKED_TECHNICAL | DEFERRED | REJECTED`. "Done" requires evidence in `artifacts/evidence/<TASK-ID>/`, not an agent's say-so.

## Model routing
- Cheapest (Haiku-class): inventory, manifests, doc sync, TODO updates, commit messages.
- General (Sonnet-class): adapters, features, models, Streamlit, tests, debugging.
- Highest reasoning (Opus-class): leakage/methodology audits, hard bugs surviving 2 attempts, final scientific audit.

## Prohibited
Committing raw datasets/LFS objects/secrets/private absolute paths into git history. Modifying the sibling `data-collection-git` LFS repo's structure or history. Training on hidden Full_Test_Set before freeze. Pushing to GitHub (commit only, user pushes manually).

## Current milestone
Accelerated review track (deadline 2026-07-25): M0-M4 + minimal M8 all DONE (see `TODO.md` for commit SHAs, `artifacts/evidence/REVIEW-M*/` for evidence). Review-ready. Remaining before 2026-07-25: stabilization only (command.md section 26.4). Post-review: M5 (stage classification), M6 (optional CNN), M7 (RAG/LLM), full 129-file college run, M9 (final audit). See `docs/milestone.md`, `TODO.md`, `reports/verification/review-readiness.md`.
