# Vercel deployment (Goal 3/Vercel-only goals)

## What's in place

- `frontend/` — Next.js 16 app (App Router, TypeScript, Tailwind). `npm run build` and
  `npm run lint` pass. Calls the inference service only through `src/lib/api.ts`; no
  prediction logic runs in the browser.
- `api/index.py` — re-exports `bearing_pdm.api.app` (the FastAPI service in
  `src/bearing_pdm/api.py`) so Vercel's Python runtime can serve it as a function.
- `api/requirements.txt` — minimal deps for that function (fastapi, pydantic, joblib,
  scikit-learn, numpy, pandas) — deliberately not the full dev `requirements.txt`
  (streamlit/duckdb/matplotlib/etc. would bloat the serverless bundle for no reason).
- `vercel.json` — builds the frontend, routes `/api/*` to the Python function.
- `frontend/src/app/blob-upload/route.ts` + `frontend/src/lib/blobUpload.ts` — direct-to-
  storage upload (browser -> Vercel Blob) for any raw dataset upload at or above 4MB, so it
  never has to fit inside a serverless function's ~4.5MB request-body limit. Deliberately
  **not** under `/api/` — `vercel.json` rewrites `/api/(.*)` to the Python function, which has
  no such route; an independent review caught that the first version of this route lived at
  `/api/blob-upload` and would have 404'd in production despite working in local dev. The
  backend then downloads the resulting Blob object itself, in bounded chunks
  (`_stream_blob_to_tempfile` in `src/bearing_pdm/api.py`), through the
  `/predict/rul/femto-acquisition/blob` and `/dataset/inspect/blob` endpoints, and always
  deletes the blob afterward — including when the download itself fails (413/404/502), not
  only when processing does (also an independent-review finding; the first version left
  oversized/missing/interrupted blobs behind forever). Requires `BLOB_READ_WRITE_TOKEN` (see
  `frontend/.env.example`) — Vercel sets this automatically once a Blob store is connected to
  the project; this environment has no Vercel account, so that connection has not been
  made/verified. The route and the backend both also accept `BLOB_STORE_HOSTNAME` /
  `ALLOWED_ORIGINS` to pin validation to this project's own store and origin rather than
  any `*.blob.vercel-storage.com` object (every Vercel customer's store matches that suffix) —
  set these once a real store/domain exists.

## Known, unresolved blocker before this can actually deploy

**`artifacts/models/*.joblib` is gitignored** (`security.md`/`git.md`: never commit
`artifacts/models/*`), and Vercel builds from the Git repository. That means a real
Vercel deployment today would have no model to load — `/health` would report
`models_loaded: false` and `/predict/rul` would return 503, honestly, but the service
would be useless.

This needs one of, before Goal 3's Vercel deployment can be verified as actually working:

1. Fetch the joblib artifacts from external storage (Vercel Blob, S3, a GitHub Release
   asset) at build time or cold start, keeping them out of Git — the correct fix, since
   it doesn't touch the "never commit trained artifacts" rule.
2. Use Git LFS the same way `datasets/` already does, if the project owner decides a
   trained artifact is an acceptable LFS object (this would require updating
   `security.md`/`git.md`, which currently forbid it — not something to change
   unilaterally).

Neither is implemented here. **I have no Vercel account/API token in this environment**,
so I cannot run an actual `vercel deploy` to verify any of this end-to-end even once the
artifact-loading gap is closed — that step needs your credentials and your explicit
go-ahead, per this project's "never push/deploy without asking" policy.

## What "done" looks like for this goal

- [x] Next.js frontend builds cleanly (`npm run build`, `npm run lint`).
- [x] FastAPI backend importable as a Vercel Python function (`api/index.py`).
- [x] `vercel.json` routing configured (`vercel_app` in `src/bearing_pdm/api.py` mounts the
      real app under `/api`, matching how Vercel's Python runtime forwards the unstripped
      request path - flagged by review as a real bug in the first version of this scaffold).
- [ ] Model artifacts reachable at runtime without committing them to Git.
- [ ] An actual `vercel deploy` (or `vercel dev`) run, verified against a live URL.
- [ ] CORS `ALLOWED_ORIGINS` set to the real deployed frontend origin, not `localhost:3000`.
- [ ] **Blocked, needs your credentials:** connecting a real Vercel Blob store to the project
      (`vercel blob store add` / dashboard), setting `BLOB_READ_WRITE_TOKEN`, and setting
      `BLOB_STORE_HOSTNAME` (both frontend and backend env) to that store's exact hostname so
      validation is pinned to this project's own store, not any Vercel customer's. The code
      path is implemented and tested locally against a mocked Blob response
      (`tests/test_api_blob.py`); it has not been exercised against a real Blob store because
      no Vercel account/token is available in this environment.

## Running locally in the meantime

```bash
# Backend - run from the repository root, with src/ on PYTHONPATH
PYTHONPATH=src uvicorn bearing_pdm.api:app --reload --port 8000

# Frontend
cd frontend
cp .env.example .env.local
npm install
npm run dev
```
