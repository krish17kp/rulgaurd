# Production readiness (Goal 38)

Scope: the read-only FastAPI inference service (`src/bearing_pdm/api.py`, deployed via
`api/index.py`) and the Next.js frontend (`frontend/`), as wired together by `vercel.json`.
This is a documentation-only pass — it describes what the current code and config actually
do, not aspirations. Where something can only be confirmed with a live Vercel deployment
(which this environment has no account/token for), it is marked **unverified**.

This complements `docs/vercel-deployment.md` (build/route scaffolding) and
`docs/decisions.md` D11 (FEMTO-only model gate) rather than replacing them.

## Environment variables

| Variable | Read by | Default | Meaning |
|---|---|---|---|
| `ALLOWED_ORIGINS` | `src/bearing_pdm/api.py` (`_ALLOWED_ORIGINS`) | `http://localhost:3000` | Comma-separated list of origins allowed by CORS (`allow_origins`). No wildcard default — a production deployment must set this explicitly to the real frontend origin(s), e.g. `https://<frontend-domain>,http://localhost:3000`. |
| `LOG_LEVEL` | `src/bearing_pdm/api.py` (`logging.basicConfig`) | `INFO` | Python `logging` level name for the root logger. Only applied on first import in a process (the `if not logger.handlers` guard skips it on subsequent imports/reloads). |
| `NEXT_PUBLIC_API_BASE_URL` | `frontend/src/lib/api.ts` | `http://localhost:8000` | Base URL the frontend calls for every backend request (`/health`, `/predict/rul`, `/predict/hi`, `/models/info`, `/models/evaluation`, `/predictions/history`, `/dataset/inspect`). Must be set to the deployed backend's public URL (including the `/api` prefix Vercel routing expects — see below) in any non-local environment. A Next.js `NEXT_PUBLIC_*` variable is baked in at build time, not read at request time. |

No secrets/API keys are read by either the backend or the frontend — there is no
authentication, database, or third-party credential in this code path today.

`frontend/.env.example` documents the one frontend variable above; there is no backend
`.env.example` because `ALLOWED_ORIGINS`/`LOG_LEVEL` are the only two and both have safe
localhost/INFO defaults for local dev.

## Frontend/backend URL wiring

- Local dev: backend on `http://localhost:8000` (`uvicorn bearing_pdm.api:app`, unprefixed
  routes), frontend on `http://localhost:3000` calling `NEXT_PUBLIC_API_BASE_URL` (defaults
  to `http://localhost:8000`).
- Vercel: `vercel.json` rewrites `/api/(.*)` to the `api/index.py` function, which serves
  `vercel_app` — `src/bearing_pdm/api.py`'s `app` mounted under `/api` (so `/health` becomes
  `/api/health`, etc., matching how Vercel's Python runtime forwards the unstripped request
  path). In that topology `NEXT_PUBLIC_API_BASE_URL` should be the frontend's own origin with
  an `/api` suffix (e.g. `https://<frontend-domain>/api`) so the two are served from one
  Vercel project, or the backend's own separate deployed origin plus `/api` if deployed apart.
  **Unverified**: no live deployment has been run in this environment to confirm the exact
  resulting URL shape end-to-end.

## Model artifact location

- Backend reads cached joblib artifacts from `artifacts/models/` (`MODELS_DIR = REPO_ROOT /
  "artifacts" / "models"` in `src/bearing_pdm/api.py`), specifically `rul_extra_trees.joblib`,
  `rul_naive.joblib`, `reference_hi_model.joblib`, `stage_thresholds.joblib`, and
  `rul_selected_model.json`. Missing files degrade individual endpoints to `503`
  (`_load_joblib` returns `None`, never raises) rather than crashing the process; `/health`
  reports which of the two RUL models loaded.
- **`artifacts/models/*` is gitignored** (only `.gitkeep` is tracked) and Vercel builds from
  the Git repository, so a Vercel deployment as configured today has no model artifacts at
  build or cold-start time — `/health` would report `models_loaded: false` for both models and
  `/predict/rul`/`/predict/hi` would return `503`. This is an open blocker, not solved by this
  goal; see `docs/vercel-deployment.md`'s "Known, unresolved blocker" section for the two
  documented remediation options (external blob/object storage fetched at build/cold-start, or
  Git LFS if the project owner decides to change the current "never commit trained artifacts"
  rule).
- This backend/Vercel path is independent of the separate Streamlit Community Cloud
  deployment (`streamlit_app.py`), which solves the same "no local artifacts on the cloud
  platform" problem differently via a small tracked `deploy_data/` snapshot
  (`scripts/build_deploy_snapshot.py`, documented in `README.md`). That snapshot is not wired
  into `src/bearing_pdm/api.py` and does not cover it.

## Startup / health checks

- `GET /health` — always returns `200` with `{"status": "ok", "models_loaded": {"rul_extra_trees": bool, "rul_naive": bool}}`. It does not fail the request if a model is missing; the caller must inspect `models_loaded`. Use this as the deployment health probe.
- `GET /models/info` — returns the selected-model record (`artifacts/models/rul_selected_model.json`, `null` if absent) plus each loaded model's feature columns (`null` if not loaded). Useful as a secondary readiness check that also confirms schema, not just presence.
- `GET /models/evaluation` — returns `503` if `reports/metrics/rul_evaluation.json` is missing, with a message naming the script (`scripts/evaluate_models.py`) that generates it. Not a liveness probe (it depends on a generated report, not just process health) but a useful "is this deployment fully provisioned" check.
- There is no separate `/ready` vs `/live` distinction, and no readiness gate that blocks traffic until models are loaded — the process starts and serves immediately; individual endpoints self-report or 503 per-request as above.

## Build / start commands

From `vercel.json` (the source of truth for the Vercel build):

```bash
# install (repo root, Vercel-invoked)
cd frontend && npm install

# build (repo root, Vercel-invoked)
cd frontend && npm run build      # -> frontend/.next (outputDirectory)

# backend function
# api/index.py, Python runtime "python3.12" (vercel.json), deps from api/requirements.txt
```

Local equivalents (`docs/vercel-deployment.md`, `frontend/package.json`):

```bash
# backend, from repo root
PYTHONPATH=src uvicorn bearing_pdm.api:app --reload --port 8000

# frontend
cd frontend
cp .env.example .env.local   # set NEXT_PUBLIC_API_BASE_URL
npm install
npm run build   # or: npm run dev
npm run start   # serves the production build from npm run build
```

`api/requirements.txt` (fastapi, pydantic, python-multipart, joblib, scikit-learn, numpy,
pandas) is deliberately a minimal subset of the root `requirements.txt`, sized for the
serverless function bundle — not the full dev environment (no streamlit/duckdb/matplotlib).

## CORS

Configured once, in `src/bearing_pdm/api.py`, via `CORSMiddleware`:

- `allow_origins`: `ALLOWED_ORIGINS` env var, comma-split, defaulting to
  `http://localhost:3000` only. No wildcard is ever used.
- `allow_methods`: `["GET", "POST"]` only.
- `allow_headers`: `["Content-Type"]` only.

A production deployment must set `ALLOWED_ORIGINS` to the real deployed frontend origin(s);
left at the default, a deployed frontend on a different origin would be blocked by the
browser's CORS check even though the API itself is reachable.

## Upload limits

Enforced in `src/bearing_pdm/api.py`, for `POST /dataset/inspect`:

- `MAX_UPLOAD_BYTES = 64 * 1024 * 1024` (64MB) — hard cap on the file `inspect_dataset` will
  read, checked as chunks (`UPLOAD_CHUNK_BYTES = 1MB` at a time) are written to a temp file;
  exceeding it returns `413` before the whole file is buffered.
- `_MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 2 * 1024 * 1024` — cap on the whole request body
  (file plus multipart overhead), enforced two ways so a request can't be buffered unbounded
  in either case:
  - `_log_requests` middleware rejects a request up front with `413` if its declared
    `Content-Length` header already exceeds this, before any body is read.
  - `_BodyLimitMiddleware` (pure-ASGI) counts bytes as they arrive and raises `413` once the
    running total passes this limit, covering chunked requests with no `Content-Length`.
- An empty upload (`0` bytes written) returns `422`, not `413`.

No limit is documented or enforced on the JSON bodies of `/predict/rul` or `/predict/hi`
beyond FastAPI/Starlette's own defaults — these are small, schema-bound payloads (feature
dict / feature rows), not arbitrary file uploads.

## Cleanup

- `POST /dataset/inspect` writes the uploaded file to a `tempfile.NamedTemporaryFile` that is
  closed (and thus deleted, on POSIX) via a `with` block once `profile_file` has read it —
  nothing persists on disk after the request.
- Prediction history (`GET /predictions/history`) is an in-memory `deque(maxlen=200)`
  (`_HISTORY_LIMIT`), self-trimming — the oldest entries are dropped automatically once 200
  entries have been recorded. It holds only request/result summaries (dataset id, feature
  counts, RUL/HI values), never raw sensor rows or uploaded filenames.
- Loaded models are cached in-process (`_MODEL_CACHE`, a plain module-level dict) for the
  life of the process; there is no explicit cache eviction, matching the fact that the model
  set is small and fixed.

## What is **not** yet done (blockers, not features)

- **No persistent artifact storage for the Vercel deployment.** As above:
  `artifacts/models/*` is gitignored, so a Vercel deployment from Git alone has no models to
  load. This blocks `/predict/rul`, `/predict/hi`, and the model-presence part of `/health`
  from ever succeeding on Vercel until artifact fetching (external storage or LFS, see above)
  is implemented — not attempted in this goal, which is docs-only.
- **No persistent prediction history on a serverless deployment.** `_prediction_history` is an
  in-memory ring buffer on one process. Vercel Python functions are stateless/short-lived and
  may run multiple concurrent or cold-started instances; `GET /predictions/history` on such a
  deployment would return whatever (possibly nothing) that particular instance has seen, not
  a durable cross-instance history. A real deployment needing durable history needs an
  external store (e.g. Vercel Postgres/KV) — not implemented, and not something this
  environment has credentials to set up.
- **No authentication or authorization** on any endpoint. Every route (`/predict/rul`,
  `/predict/hi`, `/dataset/inspect`, `/models/*`, `/predictions/history`) is open to any
  caller allowed in by CORS. There is no API key, session, or user concept anywhere in this
  code.
- **No rate limiting.** Nothing in `src/bearing_pdm/api.py` or `vercel.json` throttles request
  volume per client; the only protections against resource exhaustion are the fixed
  request/upload byte caps above, not a request-rate or per-client quota.
- **No database migrations.** There is no database in this code path (history is in-memory;
  features/metrics are files under `reports/`/`artifacts/`), so there is nothing to migrate.
  If a persistent store is added later for history, that would need its own migration story.
- **No live Vercel deployment has been run or verified in this environment** (no Vercel
  account/API token available here). Every claim above about Vercel's runtime behavior is
  based on reading `vercel.json`/`api/index.py`/the code and cross-referencing
  `docs/vercel-deployment.md`; anything stated as Vercel-specific behavior that is not backed
  by a local test is marked **unverified** and should be confirmed against a real deployment
  before relying on it operationally.

## Rollback

There is no automated rollback tooling in this repository (no CI/CD workflow files, no
deploy scripts beyond `vercel.json`'s build config). Manual rollback procedure:

1. **Vercel (frontend + `api/index.py` function)**: Vercel keeps prior deployments; from the
   Vercel dashboard/CLI, promote a previous known-good deployment to production instead of
   redeploying from a bad commit. **Unverified** — no Vercel access in this environment to
   confirm the exact dashboard/CLI steps for this project.
2. **Streamlit Community Cloud** (`streamlit_app.py`, separate deployment): re-run the deploy
   by pointing the app at an earlier commit/tag on `main`, or `git revert` the offending
   commit(s) on `main` and let Community Cloud auto-redeploy from the new head.
3. **Git-level rollback** (either deployment): `git revert <bad-commit>` and push, rather than
   `git reset --hard` on a shared branch — keeps history and lets both platforms redeploy from
   a clean forward commit. If model artifacts changed (`artifacts/models/*`, `deploy_data/*`),
   confirm `scripts/train_models.py` / `scripts/build_health.py` /
   `scripts/build_deploy_snapshot.py` are re-run against the reverted code before treating the
   rollback as complete, since those artifacts are generated, not derived automatically from
   `git revert`.

## Release checklist

- [ ] `pytest -q` passes from a clean checkout.
- [ ] `ruff check .` passes.
- [ ] `cd frontend && npm run build` and `npm run lint` pass.
- [ ] `ALLOWED_ORIGINS` is set to the real deployed frontend origin(s) — not left at the
      `http://localhost:3000` default.
- [ ] `NEXT_PUBLIC_API_BASE_URL` is set to the deployed backend's real, reachable URL
      (including the `/api` prefix if routed through `vercel.json`).
- [ ] `GET /health` on the deployed backend reports `models_loaded` all `true` — confirms the
      artifact-availability blocker above has actually been resolved for this deployment, not
      just documented.
- [ ] `GET /models/evaluation` returns real content (not `503`) — confirms
      `reports/metrics/rul_evaluation.json` shipped with this deployment.
- [ ] A smoke `POST /predict/rul` with `dataset_id="femto"` and a real feature row succeeds;
      a smoke `POST /predict/rul` with any other `dataset_id` returns `422` (confirms the
      FEMTO-only gate, D11, is still enforced).
- [ ] A smoke `POST /dataset/inspect` with a file over `MAX_UPLOAD_BYTES` returns `413`.
- [ ] No secrets, credentials, or private local paths are present in any tracked file being
      released (this doc included).
- [ ] `docs/vercel-deployment.md`'s "Known, unresolved blocker" checklist is re-checked — if
      still open, this is a Streamlit-only or local-only release, not a working Vercel release.
- [ ] Rollback target (previous known-good deployment/commit) identified and reachable before
      releasing, per the Rollback section above.
