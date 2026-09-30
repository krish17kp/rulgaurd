# Production readiness (Goal 38)

Scope: the read-only FastAPI inference service (`src/bearing_pdm/api.py`, deployed via
`api/index.py`) and the Next.js frontend (`frontend/`), as wired together by `vercel.json`.
This is a documentation-only pass — it describes what the current code and config actually
do, not aspirations. Where something can only be confirmed with a live Vercel deployment
(which this environment has no account/token for), it is marked **unverified**.

This complements `docs/vercel-deployment.md` (build/route scaffolding), `docs/decisions.md`
D11 (FEMTO-only model gate), `docs/prediction-history.md` (the history store's full
contract), `docs/upload-lifecycle.md` (temp-file spooling/cleanup) and
`docs/feature-analysis.md` (the staged `/analyze/features` pipeline) rather than replacing
them.

## Environment variables

Rebuilt by grepping every `os.environ` read in `src/bearing_pdm/api.py`,
`src/bearing_pdm/history.py`, `api/index.py` and `vercel.json` (the latter two read none),
plus the one frontend build-time variable:

| Variable | Read by | Default | Meaning |
|---|---|---|---|
| `ALLOWED_ORIGINS` | `src/bearing_pdm/api.py` (`_ALLOWED_ORIGINS`) | `http://localhost:3000` | Comma-separated list of origins allowed by CORS (`allow_origins`). No wildcard default — a production deployment must set this explicitly to the real frontend origin(s), e.g. `https://<frontend-domain>,http://localhost:3000`. |
| `LOG_LEVEL` | `src/bearing_pdm/api.py` (`logging.basicConfig`) | `INFO` | Python `logging` level name for the root logger. Only applied on first import in a process (the `if not logger.handlers` guard skips it on subsequent imports/reloads). |
| `RULGUARD_HISTORY_DB` | `src/bearing_pdm/history.py` (`configured_history_store`) | unset | Path to a local SQLite file for the prediction-history store. When unset, `configured_history_store()` returns the in-memory `InMemoryHistoryStore` instead; when set, it returns a `SQLiteHistoryStore` at that path (parent directory must already exist — see `docs/prediction-history.md`). |
| `RULGUARD_HISTORY_LIMIT` | `src/bearing_pdm/history.py` (`configured_history_store`) | `200` | Number of most-recent prediction records retained by either history store (older rows are pruned). Must parse as a positive integer; applies regardless of which store is selected. |
| `NEXT_PUBLIC_API_BASE_URL` | `frontend/src/lib/api.ts` | `http://localhost:8000` | Base URL the frontend calls for every backend request (`/health`, `/predict/rul`, `/predict/hi`, `/models/info`, `/models/evaluation`, `/models/compatibility`, `/predictions/history`, `/dataset/inspect`, `/analyze/features`, `/analyze/rul`). Must be set to the deployed backend's public URL (including the `/api` prefix Vercel routing expects — see below) in any non-local environment. A Next.js `NEXT_PUBLIC_*` variable is baked in at build time, not read at request time. |

No API keys or third-party credentials are read by either the backend or the frontend, and
there is still no authentication on any route. There is now an optional local **database**:
`RULGUARD_HISTORY_DB` points the prediction-history store at a SQLite file instead of the
in-memory default — see "Prediction history storage" below.

`frontend/.env.example` documents the one frontend variable above; there is no backend
`.env.example` because all four backend variables have safe defaults for local dev
(`http://localhost:3000` CORS origin, `INFO` logging, in-memory history with a 200-row limit)
and none is required to run the service locally.

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

- `GET /health` — always returns `200`. Its body includes `status: "ok"`, a per-model
  `models_loaded` bool map (`rul_extra_trees`, `rul_naive`), a fuller `models` object keyed by
  `rul_extra_trees`/`reference_hi` (each with `loaded`, `version`, `feature_schema_version`
  content hashes — never file names or paths), a convenience `ready` bool
  (`rul_extra_trees.loaded and reference_hi.loaded`), and `api_version`. It does not fail the
  request if a model is missing; the caller must inspect `models_loaded`/`models`/`ready`. Use
  this as the deployment health probe.
- `GET /models/info` — returns the selected-model record (`artifacts/models/rul_selected_model.json`, `null` if absent), each loaded model's feature columns (`null` if not loaded), the fixed `supported_datasets: ["femto"]` list, and a note that other adapters are not gated behind a compatible model. Useful as a secondary readiness check that also confirms schema, not just presence.
- `GET /models/evaluation` — returns `503` if `reports/metrics/rul_evaluation.json` is missing, with a message naming the script (`scripts/evaluate_models.py`) that generates it. Not a liveness probe (it depends on a generated report, not just process health) but a useful "is this deployment fully provisioned" check.
- `POST /models/compatibility` — JSON-only metadata check (`dataset_id`, `feature_names`, optional `sampling_rate_hz`; no file upload). Returns `503 MODEL_UNAVAILABLE` if the selected RUL model's metadata can't be loaded, otherwise reports one of `FULLY_SUPPORTED`/`ADAPTER_REQUIRED`/`RETRAIN_REQUIRED`/`UNSUPPORTED`/`INVALID_INPUT` (see `docs/dataset-compatibility.md`). Not itself a readiness probe, but its `503` path shares the same failure mode as `/predict/rul`'s model-load gate.
- There is no separate `/ready` vs `/live` distinction, and no readiness gate that blocks traffic until models are loaded — the process starts and serves immediately; individual endpoints self-report or 503 per-request as above (`/health`'s `ready` field is informational only, not enforced).

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

## API surface

The full current route list (`grep '@app.get\|@app.post' src/bearing_pdm/api.py`):

`GET /health`, `GET /models/evaluation`, `GET /models/info`, `POST /predict/rul`,
`POST /predict/hi`, `POST /models/compatibility`, `GET /predictions/history`,
`POST /dataset/inspect`, `POST /analyze/features`, `POST /analyze/rul`.

Every route is open to any caller allowed in by CORS — there is no API key, session, or user
concept anywhere in this code (see "What is not yet done" below).

`POST /analyze/features` and `POST /analyze/rul` are newer additions (Goal 26) beyond the
original `/predict/*` and `/dataset/inspect` set:

- **`POST /analyze/features`** — runs the full **upload -> dataset detection -> validation ->
  preprocessing -> feature extraction** pipeline (`docs/feature-analysis.md`) on one uploaded
  channel and returns per-window signal features plus an explicit `stages` array. It computes
  no health indicator, stage or RUL and loads no cached model, so D11's FEMTO-only gate is
  never involved. Its `upload` stage reuses exactly the same spooling code as
  `/dataset/inspect`: the same `MAX_UPLOAD_BYTES` (64MB) cap, the same `UPLOAD_CHUNK_BYTES`
  (1MB) chunked read with a binary/text-head sniff, and the same
  `tempfile.NamedTemporaryFile`-backed temp file, closed (and thus deleted) in a `finally`
  block on every exit path including cancellation — see `docs/upload-lifecycle.md`'s
  `cleanup_state` (`not_created`/`pending`/`deleted`/`failed`) tracking. `window_samples`
  (default 2560, the FEMTO 0.1s-at-25.6kHz acquisition length) and `overlap_samples` (default
  0) bound the per-request compute; the response is additionally capped at 200 returned
  windows (`truncated`/`truncation_note` report if the total exceeds that).
- **`POST /analyze/rul`** — the same staged pipeline run once per vibration axis on a single
  uploaded file (so still one 64MB-capped upload, spooled through one shared temp file that is
  deleted after both axes are analyzed), followed by model compatibility, health-indicator and
  prediction stages (`RUL_ANALYZE_STAGES`), producing a final RUL estimate. `dataset_id`,
  `units`, and `preprocessing_version` are caller-asserted query parameters, never inferred
  from the file; the endpoint never fits or fills a missing feature, and a failure in any
  stage still reports `prediction_produced: false` with `rul_seconds`/`rul_hours` as `null`.

`POST /models/compatibility` takes no file upload at all — it is a JSON body
(`dataset_id`, `feature_names`, optional `sampling_rate_hz`) describing a dataset's schema, so
none of the upload/size limits below apply to it; only the request-body size limits noted
under "Upload limits" apply.

## Upload limits

Enforced in `src/bearing_pdm/api.py` for every multipart-upload route —
`POST /dataset/inspect`, `POST /analyze/features`, and `POST /analyze/rul` — via the shared
`_temporary_upload`/`_spool_upload` helpers:

- `MAX_UPLOAD_BYTES = 64 * 1024 * 1024` (64MB) — hard cap on the file that will be read,
  checked as chunks (`UPLOAD_CHUNK_BYTES = 1MB` at a time) are written to a temp file;
  exceeding it returns `413` before the whole file is buffered. `/analyze/rul` reads the same
  uploaded file once but analyzes it per vibration axis, so the 64MB cap still applies to one
  upload, not per axis.
- `_MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 2 * 1024 * 1024` — cap on the whole request body
  (file plus multipart overhead), enforced two ways so a request can't be buffered unbounded
  in either case:
  - `_log_requests` middleware rejects a request up front with `413` if its declared
    `Content-Length` header already exceeds this, before any body is read.
  - `_BodyLimitMiddleware` (pure-ASGI) counts bytes as they arrive and raises `413` once the
    running total passes this limit, covering chunked requests with no `Content-Length`.
- An empty upload (`0` bytes written) returns `422`, not `413`.

No limit is documented or enforced on the JSON bodies of `/predict/rul`, `/predict/hi`, or
`/models/compatibility` beyond FastAPI/Starlette's own defaults — these are small,
schema-bound payloads (feature dict / feature rows / feature names), not arbitrary file
uploads.

## Cleanup

- `POST /dataset/inspect`, `POST /analyze/features`, and `POST /analyze/rul` all write their
  upload to one `tempfile.NamedTemporaryFile` per request (the shared `_temporary_upload`
  context manager), closed — and thus deleted, on POSIX — in a `finally` block on every exit
  path (success, validation rejection, parsing failure, client disconnect, cancellation, or a
  body/file size `413`). Nothing persists on disk after the request; see
  `docs/upload-lifecycle.md` for the full per-route cleanup-state tracking.
- Prediction history (`GET /predictions/history`) is bounded and self-trimming, but is no
  longer only an in-memory structure — see "Prediction history storage" below. It holds only
  request/result summaries (dataset id, feature counts, RUL/HI values, hashes), never raw
  sensor rows or uploaded filenames.
- Loaded models are cached in-process (`_MODEL_CACHE`, a plain module-level dict) for the
  life of the process; there is no explicit cache eviction, matching the fact that the model
  set is small and fixed.

## Prediction history storage

`src/bearing_pdm/history.py` defines two interchangeable stores behind one `HistoryStore`
protocol (`append`/`recent`/`limit`), selected once at import time by
`configured_history_store()`:

- **`InMemoryHistoryStore`** (the default, used whenever `RULGUARD_HISTORY_DB` is unset) — a
  process-local `collections.deque(maxlen=RULGUARD_HISTORY_LIMIT)`, guarded by a `Lock`.
  Records live only as long as the process does and are not shared across instances.
- **`SQLiteHistoryStore`** (used when `RULGUARD_HISTORY_DB` is set to a file path) — a single
  `prediction_history` table (WAL mode, one connection per operation, insert+prune in one
  transaction, 30s lock timeout), retaining only the most recent `RULGUARD_HISTORY_LIMIT` rows.
  Multiple worker processes can share one SQLite file as long as they're configured with the
  same limit; see `docs/prediction-history.md` for the full column/record contract.

Either way, **serverless storage is still ephemeral unless `RULGUARD_HISTORY_DB` points at a
durable path**: a Vercel Python function's local filesystem does not persist or share state
across cold starts or concurrent instances, so pointing `RULGUARD_HISTORY_DB` at a path inside
the function's own ephemeral filesystem does not solve durability — it needs to point at a
mounted/durable volume outside the function's per-invocation storage, which this repository
does not provision. Without that, a Vercel deployment's `GET /predictions/history` behaves the
same as the in-memory default: whatever (possibly nothing) that particular instance has seen,
not a durable cross-instance history.

## What is **not** yet done (blockers, not features)

- **No persistent artifact storage for the Vercel deployment.** As above:
  `artifacts/models/*` is gitignored, so a Vercel deployment from Git alone has no models to
  load. This blocks `/predict/rul`, `/predict/hi`, and the model-presence part of `/health`
  from ever succeeding on Vercel until artifact fetching (external storage or LFS, see above)
  is implemented — not attempted in this goal, which is docs-only.
- **No durable prediction history on a serverless deployment unless a durable
  `RULGUARD_HISTORY_DB` path is provisioned.** The default `InMemoryHistoryStore` is a ring
  buffer on one process; even the optional `SQLiteHistoryStore` does not help on Vercel unless
  its path is on storage that survives cold starts and is shared across instances (Vercel's
  Python functions are stateless/short-lived), which this repository does not provision. A
  real deployment needing durable, cross-instance history needs an external store (e.g. Vercel
  Postgres/KV, or a SQLite file on a mounted durable volume) — not implemented, and not
  something this environment has credentials to set up.
- **No authentication or authorization** on any endpoint. Every route (`/predict/rul`,
  `/predict/hi`, `/dataset/inspect`, `/analyze/features`, `/analyze/rul`, `/models/*`,
  `/predictions/history`) is open to any caller allowed in by CORS. There is no API key,
  session, or user concept anywhere in this code.
- **No rate limiting.** Nothing in `src/bearing_pdm/api.py` or `vercel.json` throttles request
  volume per client; the only protections against resource exhaustion are the fixed
  request/upload byte caps above, not a request-rate or per-client quota.
- **No database migrations.** The only database in this code path is the optional
  `RULGUARD_HISTORY_DB` SQLite file, which creates its own table on first connect
  (`CREATE TABLE IF NOT EXISTS`) and has no separate schema-versioning or migration story; if
  its schema ever needs to change, that would need one to be added. Everything else
  (features/metrics) is files under `reports/`/`artifacts/`, so there is nothing else to
  migrate.
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
   `git revert`. If `RULGUARD_HISTORY_DB` is configured, its SQLite file is independent of the
   code revert and is not rolled back by it.

## Release checklist

- [ ] `pytest -q` passes from a clean checkout.
- [ ] `ruff check .` passes.
- [ ] `cd frontend && npm run build` and `npm run lint` pass.
- [ ] `ALLOWED_ORIGINS` is set to the real deployed frontend origin(s) — not left at the
      `http://localhost:3000` default.
- [ ] `NEXT_PUBLIC_API_BASE_URL` is set to the deployed backend's real, reachable URL
      (including the `/api` prefix if routed through `vercel.json`).
- [ ] If durable prediction history is required, `RULGUARD_HISTORY_DB` points at a path on
      storage that actually survives cold starts and is shared across instances in this
      deployment — not left unset (in-memory) and not pointed at ephemeral function storage.
- [ ] `GET /health` on the deployed backend reports `models_loaded`/`ready` all `true` —
      confirms the artifact-availability blocker above has actually been resolved for this
      deployment, not just documented.
- [ ] `GET /models/evaluation` returns real content (not `503`) — confirms
      `reports/metrics/rul_evaluation.json` shipped with this deployment.
- [ ] A smoke `POST /predict/rul` with `dataset_id="femto"` and a real feature row succeeds;
      a smoke `POST /predict/rul` with any other `dataset_id` returns `422` (confirms the
      FEMTO-only gate, D11, is still enforced).
- [ ] A smoke `POST /dataset/inspect` with a file over `MAX_UPLOAD_BYTES` returns `413`; the
      same check holds for `POST /analyze/features` and `POST /analyze/rul` (shared limit).
- [ ] No secrets, credentials, or private local paths are present in any tracked file being
      released (this doc included).
- [ ] `docs/vercel-deployment.md`'s "Known, unresolved blocker" checklist is re-checked — if
      still open, this is a Streamlit-only or local-only release, not a working Vercel release.
- [ ] Rollback target (previous known-good deployment/commit) identified and reachable before
      releasing, per the Rollback section above.
