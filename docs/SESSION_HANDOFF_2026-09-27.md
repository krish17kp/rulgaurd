# Session handoff — 2026-09-27/28 (M11: FastAPI + Next.js web app)

Everything below was done in one Claude Code session in `rulgaurd-public/`. Nothing was
pushed. Nothing was merged to `main`.

## 1. What the session was asked to do

The user pointed at `START_CAPSTONE_OVERNIGHT.md` (untracked, repo root) and told me to follow
it, with `goals.md`, `prompts.md`, `model.md` (also untracked). Those files direct replacing
the Streamlit dashboard with a Next.js frontend + FastAPI inference service on Vercel, using
an "overnight orchestrator" with Claude→Codex failover, worktrees, and mandatory Opus/"GPT-6
Astra" verification of every goal.

## 2. Conflicts I raised before starting, and the user's answers

- `.claude/rules/dashboard.md` (capstone root, local-only) forbids FastAPI/REST/JS frontends
  as scope creep. **User chose: pivot to Next.js + FastAPI + Vercel deliberately.**
- `prompts.md`/`model.md` name "Claude Opus 5" / "GPT-6 Astra" as verifiers; GPT-6 Astra does
  not exist here. **User chose: use the real Opus model (`opus` subagent).**
- Autonomy: user said take decisions myself, don't ask, keep going. I did, except where a
  real blocker existed (Vercel credentials, merge to main, new test toolchain).
- I did **not** edit `.claude/rules/dashboard.md` (it lives outside the repo, and my edit
  attempt targeted the wrong path). That rule file still says "no API/no JS frontend" and is
  now stale relative to this branch. Update it yourself or tell me to.

## 3. Branches and commits

Branch chain (all local, off `cross-dataset` HEAD `cc30e88`, not `main`'s tip):
`overnight/capstone/goal-01-fastapi-backend` (tip `414fa07`) →
`overnight/capstone/goal-02-nextjs-frontend` (tip `074bd54`, current checkout).

| SHA | What |
|---|---|
| a36d63c | FastAPI service: /health, /models/info, /predict/rul; FEMTO-only gate (D11) |
| 414fa07 | Fix: reject >50% missing features; 503 test; test docstring |
| 195c2a2 | Next.js frontend scaffold (/ and /predict), CORS, `vercel.json`, `api/index.py`, `docs/vercel-deployment.md` |
| 4b1fc4a | POST /dataset/inspect; fix Vercel `/api` prefix bug (`vercel_app` mount); remove private path from doc |
| c1ba3ec | Frontend /upload page |
| 5cce4a4 | Fix fail-open `_classify` (numeric/constant/NaN checks); add POST /predict/hi; `docs/dataset-compatibility.md` |
| b7ba1f7 | Frontend /degradation page |
| eae1141 | Fix inf-value fail-open; min-rows guard on /predict/hi; GET /predictions/history (in-memory) |
| 21d071a | Reject constant reference window + non-finite values; fix duplicated `@skipif` |
| 7868a28 | Scale-relative degenerate-window check (uses `reference_model.scales`, ≥2 varying features); GET /models/evaluation + /evaluation page |
| fd58ecf | Request logging middleware, `X-Request-ID` |
| 0421469 | Shared `SiteNav` in layout (other pages were dead ends) |
| 778631d | Reject oversized `Content-Length` (413) before body is read |
| b14ffbb | Review nits (import placement, comment) |
| 30f74a3 | `tests/test_api_e2e.py`: real FEMTO CSV → `features.py` → live `/predict/rul` |
| c567ec5 | e2e follow-ups: RUL sanity bound (0–7 days); un-gate distinct-fixtures test |
| 074bd54 | Sync `docs/milestone.md` (new M11 section) and `TODO.md` (M11 rows) |

## 4. State at handoff

- `pytest -q`: **233 passed**. `ruff check .`: clean. Frontend `npm run build` and
  `npm run lint`: clean (last run at commit 0421469; frontend unchanged since).
- Working tree: only the 4 pre-existing untracked files (`START_CAPSTONE_OVERNIGHT.md`,
  `goals.md`, `model.md`, `prompts.md`) plus this handoff doc.
- Streamlit `dashboard.py` and all M0–M10 code/tests are untouched.

## 5. Verification process (be aware of its limits)

Every substantive commit was reviewed by a separate `opus` subagent I spawned, which read
the diff, re-ran probes, and ran pytest/ruff/npm. Several commits FAILed first and needed
2–4 fix cycles; the defects found were real (fail-open classifiers, HI scored HEALTHY on
constant/short/jittery input, Vercel path bug, dead-end nav, duplicated skipif). Reviewer
reports are model output, not human review. The e2e test's RUL sanity bound is loose on
purpose; Bearing1_1 is a training bearing, so its ~28,020 s value is in-sample, not evidence.
Final commits `c567ec5` and `074bd54` (test tweak, docs) were not re-reviewed.

## 6. What is NOT done

- **No Vercel deployment.** No credentials here. `vercel.json`/`api/index.py` are untested on
  real Vercel.
- **Model artifacts can't be served in prod:** `artifacts/models/*.joblib` are gitignored by
  project policy. Needs external storage (Blob/S3/GitHub Release) or an explicit policy
  change. Without them `/health` reports models not loaded and predict endpoints 503.
- `/predict/rul` and `/predict/hi` take **pre-extracted feature rows**, not raw CSVs.
  `/dataset/inspect` only classifies file structure (column-name level); it does not run
  `applicability.py`, does not guess sampling rate/units, and `RETRAIN_REQUIRED` is not
  produced as a distinct state (both fold into `ADAPTER_REQUIRED`).
- No raw-upload → features → RUL pipeline over HTTP, no chunked upload beyond the 64 MB
  inspect cap (chunked bodies without Content-Length are still buffered by Starlette before
  the in-handler limit fires), no persistent prediction history (in-memory ring buffer of
  200, resets on restart / not shared across serverless instances), no auth, no rate
  limiting, no request timeouts.
- No frontend automated tests (would need Vitest/Playwright — a new dependency, not added).
- No Claude→Codex watchdog/failover system; no worktree orchestration (I used sequential
  branches instead).
- Streamlit not removed; parity with it is not established.
- `.claude/rules/dashboard.md` and the capstone-root `CLAUDE.md` now contradict this branch.

## 7. Gotchas for the next person

- `~/.venvs/rulguard`'s editable `bearing_pdm` install points at `data/rlguard/src`, **not**
  this clone. `pytest` works (pyproject `pythonpath=["src"]`). Plain `python`/`uvicorn` from
  here needs `PYTHONPATH=src`, otherwise it imports the other repo (no `api.py` there).
- `data/rlguard` (on `main`, has uncommitted edits) and `rulgaurd-public` (on `cross-dataset`
  lineage) have diverged; the root CLAUDE.md's "byte-identical clones" claim is stale.
- `next dev` regenerates `frontend/AGENTS.md`/`CLAUDE.md` on every start; I set
  `agentRules: false` in `next.config.ts` and deleted them. Don't commit them.
- New deps added to `requirements.txt`: `fastapi`, `uvicorn[standard]`, `httpx`,
  `python-multipart`. `api/requirements.txt` is the minimal Vercel function set.
- sklearn version warnings on unpickling the models (1.9.0 → 1.9.1) are pre-existing.
- Bash tool hit transient `EDQUOT` errors twice while subagents were running; they cleared
  on their own. Disks were not full (root 11%).
- `START_CAPSTONE_OVERNIGHT.md` and siblings remain untracked; they contain instructions
  (Vercel-only, no Railway/Render, nonexistent verifier models) I did not fully follow.

## 8. Run it locally

```bash
cd rulgaurd-public
PYTHONPATH=src ~/.venvs/rulguard/bin/python -m uvicorn bearing_pdm.api:app --port 8000
cd frontend && cp .env.example .env.local && npm install && npm run dev   # http://localhost:3000
~/.venvs/rulguard/bin/python -m pytest -q && ~/.venvs/rulguard/bin/python -m ruff check .
```
Set `ALLOWED_ORIGINS` for any non-localhost frontend origin (CORS defaults to
`http://localhost:3000`, no wildcard).

## 9. Suggested next steps (need your call)

1. Decide whether to merge the branch to `main` (and reconcile with `data/rlguard`).
2. Update or retire `.claude/rules/dashboard.md` and root `CLAUDE.md` to match the new
   architecture.
3. For a real deploy: Vercel access + an artifact-storage decision, then run and verify.
4. Optional: frontend tests (Vitest/Playwright), raw-CSV→features→RUL endpoint, persistent
   history store.
