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
- [x] `vercel.json` routing configured.
- [ ] Model artifacts reachable at runtime without committing them to Git.
- [ ] An actual `vercel deploy` (or `vercel dev`) run, verified against a live URL.
- [ ] CORS `ALLOWED_ORIGINS` set to the real deployed frontend origin, not `localhost:3000`.

## Running locally in the meantime

```bash
# Backend
cd /mnt/NewVolume/capstone/data/rlguard  # or this clone
~/.venvs/rulguard/bin/uvicorn bearing_pdm.api:app --reload --port 8000

# Frontend
cd frontend
cp .env.example .env.local
npm install
npm run dev
```
