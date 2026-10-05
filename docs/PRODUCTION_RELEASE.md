# Production release — 2026-10-05

## Final branch and head
`overnight/capstone/m12-final-integration`, local only. Not merged to `main`, not pushed.
Final commit at the time of this release: `485ec84` plus any doc-only commits immediately
after it in the same session.

## Deployment
- **Vercel project**: `rulguard` (org `krishparekh261-9292s-projects`).
- **Production URL**: **https://rulguard.vercel.app** — PRODUCTION_VERIFIED (see section 6).
- **Preview URLs**: ephemeral, one per `vercel deploy` (e.g.
  `https://rulguard-loowhlrvw-krishparekh261-9292s-projects.vercel.app`) — PREVIEW_VERIFIED.
- **Vercel Project Settings** (set via the Vercel REST API, not in git — record this so the
  project can be recreated or audited):
  - `rootDirectory = "frontend"`
  - `framework = "nextjs"`
  - `sourceFilesOutsideRootDirectory = true`
  - `buildCommand` / `outputDirectory` / `installCommand` = `null` (Next.js zero-config)

## Architecture as actually deployed (not as originally planned)
- `api/index.py` and `api/requirements.txt` live at `frontend/api/`, not the repo root — Vercel
  requires serverless function paths to resolve relative to the configured Root Directory.
- `frontend/package.json`'s `prebuild` npm script (runs automatically before `next build`)
  copies `../src/bearing_pdm` to `frontend/api/bearing_pdm` fresh on every build, stripping any
  stale `__pycache__`. That copy is gitignored and never hand-edited; `src/bearing_pdm` remains
  the one canonical source. Two other mechanisms were tried and abandoned because they hit
  undiagnoseable platform errors: `includeFiles` with a `../` glob (consistent opaque "internal
  Vercel error" at the deploy-outputs step, 5 attempts), and a local-path pip/uv install
  (`uv sync`'s strict project-name validation rejected it).
- `artifacts/models/manifest.json` is not vendored into the function at all (it lives outside
  `src/`). `src/bearing_pdm/artifacts.py`'s `load_manifest()` reads it from the
  `ARTIFACT_MANIFEST_JSON` environment variable instead (checksums/sizes/URLs only, never a
  binary — not a secret, set directly via `vercel env add`).

## Environment variables (no secret values below)
| Variable | Classification | Environments set | Purpose |
|---|---|---|---|
| `BLOB_READ_WRITE_TOKEN` | SECRET (auto-provisioned by `vercel blob create-store`) | Production, Preview, Development | Vercel Blob read/write access for the connected store. |
| `BLOB_STORE_HOSTNAME` | PUBLIC (a hostname, not a credential, but stored as Secret-type by default) | Production, Preview, Development | Pins blob validation to this project's own store (`ctu3kekak2ukxspd.public.blob.vercel-storage.com`), not any Vercel customer's. |
| `ALLOWED_ORIGINS` | PUBLIC | Production (`https://rulguard.vercel.app`), Preview | CORS allowlist; same-origin frontend calls don't need it, but it's set for any cross-origin caller. |
| `NEXT_PUBLIC_API_BASE_URL` | PUBLIC (baked into the frontend build) | Production, Preview | `/api` — the backend is same-domain via the `/api/*` rewrite, not a separate host. |
| `ARTIFACT_MANIFEST_JSON` | DERIVED (generated from the committed `artifacts/models/manifest.json`, not independently authored) | Production, Preview, Development | The manifest's JSON text, since the file itself isn't vendored into the function (see above). Checksums/sizes/URLs only. |

## Model artifact hosting
All 8 entries in `artifacts/models/manifest.json` have real `source_url`s pointing at a real,
newly-created **public** Vercel Blob store (project "rulguard", store `store_cTU3KEkAk2ukXsPd`,
hostname `ctu3kekak2ukxspd.public.blob.vercel-storage.com`). Every file's sha256/size was
verified against the local file before upload (`sha256sum`) and the manifest's checksums were
confirmed correct by that comparison, not assumed. **Real artifact retrieval was verified live**
in production: `GET /api/health` shows `rul_extra_trees`/`reference_hi` loaded with their real
sha256 versions, fetched from the real Blob store at cold start (confirmed via `vercel logs`
showing the actual `GET https://ctu3kekak2ukxspd.public.blob.vercel-storage.com/models/...`
requests, not a local file).

**Known limitation, confirmed live, not engineered around:** fetching `cross_domain_bundle.joblib`
(219MB, the applicability/OOD model) into a warm instance's `/tmp` that already cached
`rul_extra_trees.joblib` (108MB) from an earlier request exceeds the Hobby-tier Fluid Compute
function's ephemeral disk — `[Errno 28] No space left on device`, confirmed via `vercel logs`.
Raising the function's configured `memory` in `vercel.json` was tried and rejected by the
platform itself ("Provided `memory` setting in `vercel.json` is ignored on Active CPU billing"),
confirming this isn't a free config fix. **The system fails closed correctly in this case**:
`ensure_artifact` returns `None`, and the M2 production-policy fix reports
`compatibility=RETRAIN_REQUIRED` with an honest "could not be assessed" reason — never a
fabricated applicability result. This is documented as an accepted limitation of the free tier,
not silently hidden.

**Partial mitigation, NOT_VERIFIED live (2026-10-05):** `_load_bundle` (`api.py`) now trims
`cross_domain_bundle.joblib`'s cached in-process object to only the `raw_seconds` entry
immediately after load — the bundle also carries a second full fitted `sn_fraction_multi`
model plus `hi_model`/`stage_thresholds`/`hi_name`, none of which the API ever reads. Measured
locally against the real 219MB artifact: steady-state process RSS after load drops from
639.9MB to 431.8MB (~33%). **This does not touch the documented root cause above** — the
`ENOSPC` is `/tmp` *disk* space from the downloaded joblib files themselves (108MB +
219MB on disk, unchanged by this fix, since `ensure_artifact` writes the whole file to
`/tmp` before `joblib.load` ever runs), not Python object memory. The fix is a genuine,
tested reduction in what stays resident in RAM afterward, which may still help if memory
(not disk) is the actual binding constraint on a given Hobby-tier instance, but it was not
re-verified against the live deployment in this session — no access to the production
Vercel account/logs was available here. Re-run the same `vercel logs` live check documented
above after deploying this change before upgrading this line to PRODUCTION_VERIFIED.

## Live verification performed (PRODUCTION, not just preview)
All of the following were run against **https://rulguard.vercel.app** directly in this session:

| Check | Result |
|---|---|
| `/` loads over HTTPS | 200 — PRODUCTION_VERIFIED |
| `/upload` loads | 200 — PRODUCTION_VERIFIED |
| `/api/health` | real JSON, real model checksums — PRODUCTION_VERIFIED |
| Raw FEMTO CSV -> `/api/predict/rul/femto-acquisition` | `rul_seconds=28020.0`, matches the known trusted local value for this fixture — PRODUCTION_VERIFIED |
| Real direct Blob upload -> `/api/predict/rul/femto-acquisition/blob` | identical result; blob confirmed deleted after (`vercel blob list`) — PRODUCTION_VERIFIED |
| H1 attack (a `models/...` URL as `blob_url`) | rejected with `INVALID_BLOB_URL`; model confirmed still loaded afterward via `/api/health` — PRODUCTION_VERIFIED |
| Invalid `declared_sampling_rate_hz=-5` on `/api/dataset/inspect` | 422 — PRODUCTION_VERIFIED |
| Unsupported `dataset_id=college` on `/api/predict/rul` | 422, `UNSUPPORTED_DATASET` — PRODUCTION_VERIFIED |
| LOW-applicability suppression | NOT_VERIFIED on this deployment - `cross_domain_bundle.joblib` can't be loaded on the Hobby tier due to the `/tmp` limit above, so applicability is always `None` here, not `LOW`. The suppression code path itself was independently reviewed and traced in source (`api.py:1326-1335`), but not exercised live. |

## Independent pre-production review
A second opus-model reviewer, given the actual deployed configuration and the live verification
results above, found **1 HIGH, 4 MEDIUM, several LOW**:
- **H1 (fixed, then re-verified after finding a bug in the first fix):** `_validate_blob_url`
  didn't check the URL *path*, only the hostname - an unauthenticated request could pass a real
  model artifact's URL (published in the now-public `manifest.json`) to either blob route and
  have it deleted via the existing `finally: _delete_blob(...)`. First fix attempt placed the new
  check unreachably (after the pinned-hostname branch's early `return`, which is the branch every
  real deployment takes since `BLOB_STORE_HOSTNAME` is always set) - caught by re-running the
  exact attack against the live preview after "fixing" it and watching it still delete the model.
  Second fix moved the check before that `return`; re-verified live against preview, then again
  against production (see table above) - confirmed genuinely blocked both times.
- **M1 (partially addressed):** stale docs describing the pre-deployment-debugging layout
  (`api/` at repo root, root `vercel.json`, `BLOCKED_EXTERNAL`). `TODO.md`'s M11-T3 row and this
  document are now current; `docs/vercel-deployment.md`/`docs/production-readiness.md` still
  describe the old layout in places and should be corrected in a follow-up documentation pass -
  not done in this release to avoid further scope creep this late in the run.
- **M2 (accepted limitation, not fixed):** `/api/models/evaluation` and `reliability.held_out_error`
  are unavailable in production because `REPO_ROOT`-relative paths in the vendored
  `bearing_pdm` copy don't resolve to `reports/metrics/` (which also isn't vendored). This fails
  closed (503 / "unavailable", never a fabricated number) and is a real but non-critical gap -
  the frontend doesn't currently call this endpoint.
- **M3 (accepted, documented):** `ARTIFACT_MANIFEST_JSON` could drift from the committed
  `manifest.json` after a retrain if the env var isn't updated in lockstep. No code change made;
  this is an operational discipline note for whoever retrains the models next.
- **M4 (accepted, pre-existing):** `frontend/api/requirements.txt`'s scientific dependencies
  (scikit-learn, numpy, pandas, joblib) are unpinned, so a future redeploy could pull a newer
  version than the one the `.joblib` artifacts were pickled with. Predates this session; not
  changed here to avoid an unreviewed pin choice under time pressure.
- **LOW/FALSE_POSITIVE items**: no secrets found in any tracked file (confirmed via `git grep`);
  CORS is not permissive; the M2 fail-closed applicability fix is still correctly wired; the
  vendored-copy mechanism is not vulnerable to staleness (fresh `rm -rf` + `cp` every build).

## Backend / frontend final counts
- `pytest -q`: **748 passed, 0 skipped, 0 failed**.
- `ruff check .`: clean.
- Frontend `npm test -- --run`: **16 passed**.
- Frontend `npm run lint`: clean.
- Frontend `npm run build`: clean (Next.js 16.3.6, Turbopack, 7 routes).

## Security / privacy
- No secret committed to git (checked: `.vercel/`, `.env*` are gitignored and were never
  tracked; `vercel env add` was used for every credential; `ARTIFACT_MANIFEST_JSON` and
  `BLOB_STORE_HOSTNAME` hold no secret material).
- `_delete_blob` never logs the blob URL or token (pre-existing, re-confirmed).
- H1 (above) was the one real finding and is fixed and re-verified.
- CORS has no wildcard; `ALLOWED_ORIGINS` is set to the real production origin.

## Known remaining limitations
1. Applicability/OOD gate (`cross_domain_bundle.joblib`) cannot be exercised on the Hobby tier
   due to `/tmp` capacity when a smaller model is already warm-cached - documented, not hidden.
2. `/api/models/evaluation` and `reliability.held_out_error` are unavailable in production
   (M2 above) - `reports/metrics/` isn't vendored into the function.
3. Scientific dependencies in `frontend/api/requirements.txt` are unpinned (M4 above).
4. `docs/vercel-deployment.md`/`docs/production-readiness.md` still describe the
   pre-deployment-debugging architecture in places (M1 above) - not fully corrected in this
   release.
5. No auth, no rate limiting, no durable (cross-instance) prediction history - all pre-existing,
   documented elsewhere (`docs/milestone.md`'s M11 section).
6. `ARTIFACT_MANIFEST_JSON` must be updated by hand alongside any future model retrain.

## Not done by design
- No merge to `main`.
- No force push; nothing pushed to any remote at all.
- No paid plan upgrade - confirmed via the Vercel API that this account remains on the Hobby
  plan throughout. The one place a paid-tier question could have arisen (raising function
  memory) was tried as a free config value, rejected by the platform itself as a no-op under
  this project's billing model, and reverted - no billing action was taken.
