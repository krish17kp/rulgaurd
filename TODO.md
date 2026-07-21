# TODO — canonical loop state

Accelerated review track. Deadline 2026-07-25. Today 2026-07-21.

| ID | Milestone | Task | Status | Deps | Model | Agent/skill | Worktree | Files allowed | Acceptance | Verify | Evidence | Updated | Commit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M0-T1 | M0 | Repo/tooling/data recovery audit | DONE | - | Sonnet | direct | main | docs/, TODO.md | Recovery report delivered, no destructive action, real data paths confirmed | manual review | this session transcript | 2026-07-21 | pending |
| M0-T2 | M0 | Dataset audit (college + FEMTO, real inspection) | DONE | M0-T1 | Sonnet | direct | main | docs/dataset-audit.md | Schemas/counts/hidden-RUL independently verified against command.md | see docs/dataset-audit.md | artifacts/evidence/REVIEW-M0/ | 2026-07-21 | pending |
| M0-T3 | M0 | Decisions log | DONE | M0-T1 | Sonnet | direct | main | docs/decisions.md | Every source conflict recorded with resolution | manual review | artifacts/evidence/REVIEW-M0/ | 2026-07-21 | pending |
| M0-T4 | M0 | Foundation doc set (CLAUDE.md, AGENTS.md, docs/*) | DONE | - | Sonnet | direct | main | CLAUDE.md, AGENTS.md, docs/*.md | All min-required M0 docs present and non-empty | manual review | artifacts/evidence/REVIEW-M0/ | 2026-07-21 | pending |
| M0-T5 | M0 | First local commit (foundation) | TODO | M0-T1..T4 | Haiku | direct | main | (commit only) | `git log` shows commit, no raw data staged | `git status`, `git log -1` | artifacts/evidence/REVIEW-M0/ | 2026-07-21 | - |
| M1-T1 | M1 | College adapter (`src/bearing_pdm/college.py`) | TODO | M0-T5 | Sonnet | direct | main | src/bearing_pdm/college.py, config.py | Chunked bounded-memory read, header detection, chronological ordering from filenames, 4-col validation | pytest tests/test_college.py | artifacts/evidence/REVIEW-M1/ | 2026-07-21 | - |
| M1-T2 | M1 | FEMTO adapter (`src/bearing_pdm/femto.py`) | TODO | M0-T5 | Sonnet | direct | main | src/bearing_pdm/femto.py | Acc (6-col) + temp (5-col, delimiter auto-detect) parsing, missing-temp explicit, learning/test/full-test roles distinguished | pytest tests/test_femto.py | artifacts/evidence/REVIEW-M1/ | 2026-07-21 | - |
| M1-T3 | M1 | Fixtures + parser tests | TODO | M1-T1, M1-T2 | Sonnet | direct | main | data/fixtures/, tests/test_college.py, tests/test_femto.py | Tiny committed real-data excerpts, tests pass | pytest -q | artifacts/evidence/REVIEW-M1/ | 2026-07-21 | - |
| M2-T1..T4 | M2 | Feature pipeline + Parquet/DuckDB store | TODO | M1-T3 | Sonnet | direct | main | src/bearing_pdm/features.py, storage.py | See docs/milestone.md | pytest -q | artifacts/evidence/REVIEW-M2/ | - | - |
| M3-T1,T2 | M3 | Health indicator (transparent + paper-inspired) | TODO | M2 | Sonnet | direct | main | src/bearing_pdm/health.py | See docs/milestone.md | pytest -q | artifacts/evidence/REVIEW-M3/ | - | - |
| M4-T1..T4 | M4 | RUL baselines, grouped/time-ordered eval | TODO | M3 | Sonnet | direct | main | src/bearing_pdm/modeling.py, evaluation.py | See docs/milestone.md | pytest -q, scripts/evaluate_models.py | artifacts/evidence/REVIEW-M4/ | - | - |
| M8-T1..T4 | M8 (minimal) | Streamlit dashboard | TODO | M4 | Sonnet | direct | main | src/bearing_pdm/dashboard.py, scripts/run_dashboard.py | See docs/milestone.md | streamlit run | artifacts/evidence/REVIEW-M8/ | - | - |
| M5-M7,M9 | post-review | Stage classification, optional CNN, RAG, final audit | DEFERRED_AFTER_REVIEW | - | - | - | - | - | - | - | - | - | - |

## Next task
M0-T5 (first local commit), then M1-T1/M1-T2 in parallel-safe order (different files, same worktree — no worktree isolation needed per command.md 6.4).
