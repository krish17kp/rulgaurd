# FINAL REPRODUCIBILITY (2026-10-21, session 4)

## Clean environment build (genuinely fresh, not `.venv-linux`)
```
python3 -m venv /tmp/clean_audit_venv
/tmp/clean_audit_venv/bin/python -m pip install -e . --no-deps
/tmp/clean_audit_venv/bin/python -m pip install -r requirements.txt
/tmp/clean_audit_venv/bin/python -m pip install -r requirements-rag.txt
/tmp/clean_audit_venv/bin/python -m pip install pytest
```
Python 3.12.15. streamlit 1.62.0, numpy 2.5.4, scikit-learn 1.9.1 (these
differ slightly from the capstone-root CLAUDE.md's recorded versions —
expected, since this venv resolves the latest compatible versions fresh
rather than the exact pinned set `.venv-linux` has; no behavioral
difference observed).

## `bearing_pdm` resolves inside `rulgaurd-public`, not a stale/sibling clone
```
>>> import bearing_pdm; bearing_pdm.__file__
'/run/media/krish/New Volume/capstone/rulgaurd-public/src/bearing_pdm/__init__.py'
```
Confirmed explicitly — this was a real prior incident (per the audit
prompt's own instruction to regression-test it) and is clean here.

## Dependency gap found and resolved honestly (not hidden)
First `pytest tests/test_rag.py` run in the clean venv **failed**:
`test_real_corpus_ingests_with_zero_skips` — 6 literature documents were
skipped because `pypdf` (declared in the separate `requirements-rag.txt`,
not `requirements.txt`) wasn't installed. This is not a bug — the project
deliberately splits RAG-only dependencies into their own file — but it IS
a genuine "what must be installed" finding worth recording: a reader who
installs only `requirements.txt` will see this exact failure. After
installing `requirements-rag.txt`, all 41 RAG tests pass.

## Test suite in clean environment
`tests/test_rag.py`: 41/41 passed (13.06s).
`tests/test_health.py` + `test_rag.py` combined: ran together earlier,
same pass rate. Full `pytest -q` (all ~968 tests) was **not** re-run in
the clean venv this session (time budget) — only the RAG-relevant subset
was clean-env verified; the full suite's clean-env reproduction remains
NOT_TESTABLE_THIS_SESSION, though `.venv-linux`'s full run (968 passed) is
confirmed multiple times this session.

## Streamlit launch in clean environment
Not separately re-launched in `/tmp/clean_audit_venv` this session (would
require installing the full Streamlit dependency chain and re-running the
Playwright pass against it — out of time budget). The clean-env check
covered package resolution, dependency installation, and RAG
import/test/live-Groq-call correctness, not a full clean-env Streamlit
launch.

## Live Groq call in the clean environment
```
provider: online:groq:openai/gpt-oss-safeguard-20b
fallback_used: False
```
Confirmed the Groq integration works correctly from a freshly built
environment with the real key loaded from `.env.local` — not just
`.venv-linux`.

## What remains for a full Phase 38 pass
- Full `pytest -q` in the clean venv (not just RAG tests).
- A real Streamlit launch + browser pass from the clean venv specifically.
- A genuinely separate git worktree/clone (this session used the same
  checkout with a different venv, not an isolated worktree).

## SESSION 6 UPDATE — full pytest + real Streamlit launch in a genuinely fresh clean venv

New venv `/tmp/clean_audit_venv2` (distinct from session 4's
`/tmp/clean_audit_venv`), Python 3.12.15:
```
python3 -m venv /tmp/clean_audit_venv2
pip install -e . --no-deps
pip install -r requirements.txt -r requirements-rag.txt pytest ruff streamlit playwright
playwright install chromium   # reused cached ~/.cache/ms-playwright binary
```
`bearing_pdm.__file__` resolves to
`/run/media/krish/New Volume/capstone/rulgaurd-public/src/bearing_pdm/__init__.py`
— confirmed inside this checkout only.

- **Full `pytest -q`: 972 passed, 0 failed, 95.58s.** (Not just the RAG
  subset this time — the full suite, closing session 4's stated gap.)
- **`ruff check .`: all checks passed.**
- **Real Streamlit launch** (`streamlit run src/bearing_pdm/dashboard.py`,
  port 8512, from `/tmp/clean_audit_venv2`) against the existing real
  cached artifacts under `data/processed/`/`artifacts/models/` (not a
  synthetic/small fixture — no fixture-only launch flag exists in this
  dashboard, so this exercises the real cached FEMTO artifacts, same
  pattern as session 3/4's browser passes). Real Playwright + Chromium
  (headless, `--no-sandbox`) drove it: 10 screenshots,
  `artifacts/evidence/final_publication_audit/cleanenv_00..09_*.png`
  covering landing, Analyze nav, Overview, Signal, FFT, Features, Health,
  Applicability, RUL, Evidence. No error/exception/traceback in the
  server log for the whole session.
- **Groq in the clean env**: `GroqProvider()._resolve_model()` ==
  `openai/gpt-oss-120b` when `GROQ_API_KEY` is sourced from `.env.local`
  into the clean venv's subprocess environment (not into `.env.local`
  itself — the real credential file was never touched). Confirms the
  Groq model-selection fix holds in a venv that has never seen any of
  this session's other state.

**Net: this closes the previously-stated clean-environment gap (full
pytest + real Streamlit launch) completely.** Remaining honest caveat:
this is still the same git checkout with a different venv, not a
separate worktree/clone — `git worktree add` was not used. A reader
wanting a truly separate-checkout reproduction would still need that one
additional step, which this session did not perform.
