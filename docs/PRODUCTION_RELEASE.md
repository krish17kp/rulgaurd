# Production release — 2026-10-05

## FINAL STATUS: PRODUCTION_VERIFIED_WITH_LIMITATIONS

The `/tmp` ENOSPC fix (commits `0f783b9`..`1adf967`) was verified on a preview deployment,
then promoted to production and re-verified there directly (this section). See
"Production re-verification (post `/tmp` fix promotion)" below for the full checklist and
evidence. Remaining limitations, none upgraded to PASS: rendered-browser E2E not completed,
exhaustive concurrency stress test not completed, external security scanner not run.

## Final branch and head
`overnight/capstone/m12-final-integration`, local only. Not merged to `main`, not pushed.
Final commit at the time of this release: `1cb9aa8` (this doc commit) plus the six fix
commits before it in the same session (`0f783b9`..`1adf967`).

## Deployment
- **Vercel project**: `rulguard` (org `krishparekh261-9292s-projects`).
- **Production URL**: **https://rulguard.vercel.app** — PRODUCTION_VERIFIED, re-deployed and
  re-verified 2026-10-05 with the `/tmp` fix live (deployment `dpl_5xEs3e4s2KFHHq2MNYcxzZb2j4jo`).
- **Preview URLs**: ephemeral, one per `vercel deploy` (e.g.
  `https://rulguard-loowhlrvw-krishparekh261-9292s-projects.vercel.app`,
  `https://rulguard-q9czcmhnq-krishparekh261-9292s-projects.vercel.app` — the `/tmp`-fix
  preview, superseded by the production promotion above) — PREVIEW_VERIFIED.
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

**Memory mitigation, NOT_VERIFIED live (2026-10-05):** `_load_bundle` (`api.py`) now trims
`cross_domain_bundle.joblib`'s cached in-process object to only the `raw_seconds` entry
immediately after load — the bundle also carries a second full fitted `sn_fraction_multi`
model plus `hi_model`/`stage_thresholds`/`hi_name`, none of which the API ever reads. Measured
locally against the real 219MB artifact: steady-state process RSS after load drops from
639.9MB to 431.8MB (~33%). This alone does not touch the `/tmp` *disk* ENOSPC below (the
downloaded joblib files, not Python object memory) — see the disk fix that follows.

**Disk root-cause fix, NOT_VERIFIED live (2026-10-05):** `_load_joblib` (`api.py`) now deletes
an artifact's *downloaded cache copy* (under `ARTIFACT_CACHE_DIR`/`/tmp`, never the repo-local
`artifacts/models/` dev checkout) immediately after `joblib.load()` succeeds. The deserialized
model already lives in `_MODEL_CACHE` for the rest of the process's life — `_load_joblib`'s own
cache-hit fast path means the file is never read again — so the on-disk copy was pure dead
weight, and is the actual mechanism behind the `[Errno 28] No space left on device` above:
`rul_extra_trees.joblib` (108MB) + `cross_domain_bundle.joblib` (219MB) both being downloaded
and left on disk sums to 327MB, which the confirmed-live failure shows exceeded the Hobby
tier's `/tmp` budget. **Proved locally against the real artifact bytes**, not a synthetic
fixture: loading both real models sequentially through `_load_joblib` (mocked HTTP transport
serving the actual files, real sha256 verification, real `joblib.load`) now leaves the download
cache directory at 0MB after each load, instead of accumulating to 327MB — see commit
`a87cad7`. Both new regression tests pass; full suite (751 tests) and ruff pass.

**LIVE-VERIFIED ON PREVIEW (2026-10-05, not yet production):** deployed this branch to a Vercel
Hobby-tier preview (`rulguard-q9czcmhnq-krishparekh261-9292s-projects.vercel.app`, `target: null`,
never promoted). Reproduced the documented failure first against **unfixed production**
(`rulguard.vercel.app`) with the exact same request: `applicability_level: null`,
`"cross_domain_bundle.joblib missing or unreadable"`. The identical request against the fixed
preview:
- Cold start, first `/predict/rul` call: `vercel logs` shows
  `GET .../models/cross_domain_bundle.joblib "HTTP/1.1 200 OK"` followed by
  `status=200 ... compatibility=FULLY_SUPPORTED` (`duration_ms=8505.6` — the one-time
  download+verify+load cost). **No `ENOSPC` anywhere in the logs.**
- Response: `compatibility=FULLY_SUPPORTED`, `applicability_level=HIGH`, full `reliability`
  block populated (conformal interval, tree disagreement, applicability detail) — all
  previously `None`/unavailable on production for this same input.
- LOW-applicability suppression (the other half of this limitation, also previously
  NOT_VERIFIED): a deliberately shifted feature row correctly returned `compatibility=
  RETRAIN_REQUIRED`, `code=APPLICABILITY_LOW`, shift ratio 15.56x — confirming the suppression
  path itself (not just the loading) now runs for real.
- 3 repeat identical requests: `rul_seconds` bit-identical each time, `duration_ms` ~48-50
  (warm `_MODEL_CACHE` reuse, no re-download) — confirms both cold and warm paths work.
- Invalid input (`dataset_id="college"`): clean `422 UNSUPPORTED_DATASET`, no traceback.
- All 5 frontend routes (`/`, `/upload`, `/predict`, `/degradation`, `/evaluation`): `200`.

**Remaining gap:** this is PREVIEW_VERIFIED, not PRODUCTION_VERIFIED — the preview was not
promoted to production per standing instruction ("do not deploy to production"). The one
still-unexplained live finding: production's `/tmp` pressure also includes the Python runtime
installing its own dependency venv at `/tmp/_vc_deps` (~70MB: scipy/numpy/sklearn/pandas) on
every cold start, visible in both the before and after logs — this fix's gain was apparently
enough to clear the combined budget regardless, since the preview succeeded on its own cold
start with that same overhead present, but it remains a secondary factor worth knowing about
if `/tmp` pressure ever returns after other changes.

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
| LOW-applicability suppression | Historically NOT_VERIFIED on production before the `/tmp` fix. **Now PRODUCTION_VERIFIED** — see the section immediately below; the fix was promoted and re-checked directly against `rulguard.vercel.app`. |

## Production re-verification (post `/tmp` fix promotion, 2026-10-05)

The `/tmp` ENOSPC fix was verified on a preview first (see the OOD section above), then
promoted to production with explicit approval and re-verified directly against
**https://rulguard.vercel.app** (deployment `dpl_5xEs3e4s2KFHHq2MNYcxzZb2j4jo`, `target:
production`). Every item below is a real request/response against the live production API or
real `vercel logs` output, not a local test:

| # | Check | Result |
|---|---|---|
| 1 | `/api/health` + model artifact loading | `rul_extra_trees`/`reference_hi` loaded, same sha256 versions as before this deploy — PRODUCTION_VERIFIED |
| 2 | Trusted FEMTO RUL prediction | Raw CSV fixture (`data/fixtures/femto/Bearing1_1/acc_00001.csv`) -> `/api/predict/rul/femto-acquisition` -> `rul_seconds=28020.0`, exact match to the known trusted value — PRODUCTION_VERIFIED |
| 3 | In-domain applicability | Training-median feature row -> `compatibility=FULLY_SUPPORTED`, `applicability_level=HIGH`, `shift_ratio=0.30` — PRODUCTION_VERIFIED |
| 4 | Shifted-input applicability | Deliberately shifted feature row -> `compatibility=RETRAIN_REQUIRED`, `code=APPLICABILITY_LOW`, shift ratio 15.56x — PRODUCTION_VERIFIED |
| 5 | Cold start / warm start | `vercel logs`: cold `/api/health` call installs the runtime venv and downloads all artifacts (`duration_ms=4144.2`); first `/predict/rul/femto-acquisition` call downloads `cross_domain_bundle.joblib` fresh (`duration_ms=10630.4`, `HTTP/1.1 200 OK`, no ENOSPC); every subsequent `/predict/rul` call in the same window reuses the warm cache (`duration_ms` 48-51) — PRODUCTION_VERIFIED |
| 6 | Valid / invalid / repeated requests | 3x identical in-domain request -> bit-identical `rul_seconds=18466.3` each time; invalid `dataset_id=college` -> clean `422 UNSUPPORTED_DATASET` — PRODUCTION_VERIFIED |
| 7 | `/tmp`/artifact cleanup | `vercel logs` on the raw-upload path shows `cleanup_state=deleted` on the same request that downloaded `cross_domain_bundle.joblib`; no accumulation across the session's calls — PRODUCTION_VERIFIED |
| 8 | Model-artifact security regression (H1) | POST a `models/rul_extra_trees.joblib` blob URL to `/api/predict/rul/femto-acquisition/blob` -> `422 INVALID_BLOB_URL`; `/api/health` immediately after confirms `rul_extra_trees` still loaded — PRODUCTION_VERIFIED |
| 9 | Frontend smoke test | `/`, `/upload`, `/predict`, `/degradation`, `/evaluation` all `200` — PRODUCTION_VERIFIED |
| 10 | Logs: exceptions/tracebacks/ENOSPC/checksum failures/unexpected 5xx | None found in the full session's `vercel logs` output - every status code is `200` or an expected `422`; the only warnings present are the pre-existing, harmless sklearn `InconsistentVersionWarning` and joblib serial-mode notices (unrelated, present before this session too) — PRODUCTION_VERIFIED |

**Not upgraded to PASS by this re-verification** (same limitations as the preview pass):
rendered-browser E2E (Vercel SSO deployment-protection wall was not bypassed for a real
browser session), exhaustive concurrency stress test (only the one targeted race-reproduction
test from this session was re-run, not a broad stress suite), external security scanner (none
run). These remain explicitly NOT_VERIFIED / PARTIALLY VERIFIED, not PASS.

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
- `pytest -q`: **754 passed, 0 skipped, 0 failed** (748 at the start of this session + 6 new
  regression tests: bundle-trimming, cache-deletion, concurrency race fix, non-finite-output
  guard, determinism, local-dev-file-never-deleted).
- `ruff check .`: clean.
- Frontend `npm test -- --run`: **16 passed**.
- Frontend `npm run lint` / `tsc --noEmit`: clean.
- Frontend `npm run build`: clean (Next.js 16.3.6, Turbopack, 7 routes).

## Security / privacy
- No secret committed to git (checked: `.vercel/`, `.env*` are gitignored and were never
  tracked; `vercel env add` was used for every credential; `ARTIFACT_MANIFEST_JSON` and
  `BLOB_STORE_HOSTNAME` hold no secret material).
- `_delete_blob` never logs the blob URL or token (pre-existing, re-confirmed).
- H1 (above) was the one real finding and is fixed and re-verified.
- CORS has no wildcard; `ALLOWED_ORIGINS` is set to the real production origin.

## Known remaining limitations
1. ~~Applicability/OOD gate (`cross_domain_bundle.joblib`) cannot be exercised on the Hobby tier
   due to `/tmp` capacity~~ **RESOLVED 2026-10-05** - see "Production re-verification" above.
   Fixed by deleting an artifact's downloaded cache copy immediately after loading it into
   memory (commit `a87cad7`), verified live on both preview and production.
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
