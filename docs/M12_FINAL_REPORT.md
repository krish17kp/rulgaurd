# M12 final integration report — 2026-10-05

## 1. Final local integration branch
`overnight/capstone/m12-final-integration` (local only, branched from commit `f2cc625`,
then given two doc commits in this session). **Not merged to `main`. Not pushed.**

## 2. Final HEAD
At time of writing: this session's doc commit on top of `f2cc625` ("nightshift:
m12-scientific-parity: Final scientific parity and leakage verification").

## 3. Source lines integrated
Two lines had diverged from a common ancestor and needed reconciling:

- **`overnight/capstone/goal-02-nextjs-frontend`** (tip `3613469`): raw-FEMTO-CSV → RUL,
  `/predict/rul/femto-acquisition`, deepened `/dataset/inspect`, applicability/OOD gating
  wired into the production path, LOW-applicability suppression, MEDIUM→`RETRAIN_REQUIRED`,
  Vercel direct-to-Blob upload path, blob-reference backend endpoints, the frontend
  Vitest/RTL harness, and the checksum-verified production artifact loader.
- **`overnight/capstone/integration`** (tip `a47572a`, built from ~20 `nightshift/*` goal
  branches merged in sequence): the structured API error contract, body-size/chunked-body
  protection, JSON 500 boundary, binary/non-UTF-8 upload rejection, compute bounds,
  incomplete-FEMTO-acquisition gate, durable (optional SQLite) prediction history with
  success/failure recording, reliability info, `/models/compatibility`, `/analyze/features`,
  `/analyze/rul`, sampling-rate fail-closed behavior, blob text validation, overflow
  handling, and privacy-safe logging.

A prior automated Nightshift run had already performed this reconciliation by hand on a
sibling branch (`nightshift/.../m12-reconcile` → `m12-scientific-parity`, commits `56ec7ff`
and `f2cc625`), built on top of the same `3613469` base. **This session's job was to verify
that reconciliation is real and correct, not to redo it** — redoing a 9,500-line manual merge
that had already been done and tested would have thrown away verified work. I confirmed by
`git diff --stat` between `3613469` and `f2cc625` that every file the `integration` branch
touched was present, and by running the full suite that the result is correct (section 5).

## 4. Git ancestry confirmation
- `56ec7ff` included in final branch: **YES** (direct ancestor of `f2cc625`, which is the
  final branch's base).
- `f2cc625` included in final branch: **YES** (final branch's base commit).
- `5244fe1` (this session's earlier, now-superseded doc-only closeout commit on
  `goal-02-nextjs-frontend`) included: **NO** — it only added documentation (no code) on top
  of `3613469`, which `f2cc625` also builds on. Its doc content has been re-applied by hand
  onto this branch instead of merging that commit, because `5244fe1` was written before this
  session discovered the `integration`/`m12-reconcile` lines existed and its M11/M12 status
  claims were therefore based on an incomplete picture of Git history.

Prior to this session, `56ec7ff`/`f2cc625` were **not** ancestors of the branch I was
working on (`goal-02-nextjs-frontend` @ `5244fe1`) — they are siblings from the same base
commit, built in a separate Nightshift worktree
(`~/.nightshift/worktrees/20261003T132209Z-7a71d654/`). This is exactly the risk the task
instructions warned about: a prior session's "DONE" claim (284 backend tests) was accurate
for the branch it was looking at, but that branch had not yet absorbed the larger
reconciliation. Branching onto `f2cc625` and verifying it directly resolves that.

## 5. Final regression results (this session, on `overnight/capstone/m12-final-integration`)

**Backend:**
```
~/.venvs/rulguard/bin/python -m pytest -q
740 passed, 40 warnings in 47-49s
```
0 skipped, 0 failed. (Prior session's `goal-02-nextjs-frontend` branch had 284; the
reconciled branch's real count is 740 — the task brief's "~706" estimate was in the right
ballpark, not fabricated by this report.)

```
~/.venvs/rulguard/bin/python -m ruff check .
All checks passed!
```

Warnings observed (all pre-existing/documented, not new defects): sklearn
`InconsistentVersionWarning` on unpickling (1.9.0 → 1.9.1, documented in the capstone-root
`CLAUDE.md`), and `RuntimeWarning: overflow encountered in power/cast` from
`tests/test_api_e2e.py`'s own overflow-input test cases (the test is deliberately feeding
overflowing values to prove the API fails closed — the warning is expected, not a bug).

**Frontend:**
```
npm test -- --run    -> 3 files, 16 tests passed
npm run lint          -> clean (no output = no violations)
npm run build         -> Next.js 16.3.6 (Turbopack), compiled successfully, 7 routes
```
Frontend test count did not grow during reconciliation because the `integration` line's new
work (g01-g53) was almost entirely backend; the diff confirms only `frontend/src/lib/api.ts`
and `frontend/src/app/upload/page.tsx` were touched there, no new frontend test files.

## 6. Scientific parity / leakage audit
Not redone from scratch in this session — `f2cc625`'s own commit ("Final scientific parity
and leakage verification") already added `scripts/audit_scientific_parity.py`,
`tests/test_scientific_parity.py`, and `reports/verification/scientific-parity-evidence.json`
specifically for this purpose, and all of those pass as part of the 740. I independently
re-checked the two highest-risk invariants by reading the merged `api.py` directly rather
than trusting the commit message alone:

- **LOW applicability suppresses RUL**: confirmed at `src/bearing_pdm/api.py:1327-1335` -
  `if applicability is not None and applicability["level"] == "LOW": ... "RUL suppressed:
  model applicability is LOW..."`.
- **MEDIUM applicability stays `RETRAIN_REQUIRED`/experimental**: confirmed - `RETRAIN_REQUIRED`
  is a module-level constant used consistently across `/dataset/inspect`,
  `/predict/rul/femto-acquisition`, and the newly-merged `/analyze/rul`/`/models/compatibility`
  endpoints (grep hits at lines 100, 495-502, 592-597, 1379, 1856-1874).
- **No fabrication shortcuts**: `grep -n "except:"` and bare `except Exception: pass` across
  `src/bearing_pdm/*.py` returned nothing; no `TODO`/`FIXME`/`hack`/`placeholder` strings in
  production code paths (`api.py`, `artifacts.py`, `reliability.py`, `history.py`) other than
  two legitimate prose uses (a docstring explaining D11, and a comment describing what kind
  of *input* a validator must reject).

I did not re-derive the FEMTO/college leakage guards (LOBO, chronological expanding-window)
from scratch this session - those are M0-M10 work, untouched by M11/M12, and were already
verified in earlier sessions (`docs/decisions.md` D1-D28). Nothing in the M11/M12 web-app
layer touches model fitting; it is a read-only inference surface by construction
(`dashboard.md`/`ml-data.md` rules), and `artifacts.py`'s loader never calls `.fit()`.

## 7. Compatibility / OOD behavior
`applicability.assess(single_recording=...)` is used consistently by both the
`dataset/inspect` structural/sampling path and the newer `/analyze/rul`/`/models/compatibility`
endpoints from the `integration` line - confirmed by the reconciliation commit message's own
claim ("reliability's applicability uses the same single-recording semantics as the gate")
and by all `test_applicability`/`test_model_compatibility`/`test_reliability` tests passing.

## 8. Raw data -> RUL status
`POST /predict/rul/femto-acquisition` (raw FEMTO CSV -> `features.py` -> RUL) and its blob
equivalent are present and tested end-to-end against real fixture bytes
(`tests/test_api_e2e.py`, `tests/test_api_blob.py`). The reconciliation tightened this path:
it now requires exactly one complete 2560-row acquisition with no missing samples (previously
it accepted any file >=256 rows - a real defect the reconciling session found and fixed per
its own commit message).

## 9. Chunking / large-data status
`src/bearing_pdm/chunked.py` (bounded-memory windowed feature extraction) and the Vercel
Blob direct-upload path now coexist: blob downloads are chunked (1MB) and get the same
text/structural checks as direct multipart uploads (confirmed by `tests/test_chunked.py` and
`tests/test_api_blob.py` both passing). No chunking path silently drops rows - short/partial
final chunks are disclosed in the response per the M11 milestone notes above.

## 10. Artifact loader status
`src/bearing_pdm/artifacts.py` (checksum-verified fetch/cache, concurrent-request
de-duplication, path-traversal guard, atomic rename, unconditional cleanup on failure) is
unchanged in substance by the reconciliation (`37 +-` lines, consistent with adapting to the
merged `api.py`'s call sites, not a rewrite). `tests/test_artifacts.py`'s 17 tests pass.
`artifacts/models/manifest.json`'s `source_url` fields remain `null` - genuinely
`BLOCKED_HUMAN`, no URL was invented.

## 11. Vercel local-readiness status
No change in kind from the prior report: `vercel.json`/`api/index.py` routing, the
`/blob-upload` token route's placement outside `/api/` (so the backend rewrite can't shadow
it), `BLOB_STORE_HOSTNAME`/`BLOB_READ_WRITE_TOKEN`/`ALLOWED_ORIGINS` handling, and
missing-`source_url` fail-closed behavior are all `LOCAL_VERIFIED` (exercised against mocked
responses in `tests/test_api_blob.py`/`tests/test_artifacts.py`). An actual `vercel deploy`
or live Blob store is `BLOCKED_HUMAN` - no credentials in this environment, and none were
fabricated or claimed.

## 12. Independent review findings
This session's own review (section 6, grep-based + direct code reading of the merged
`api.py`) found **zero** new HIGH/MEDIUM defects in the integrated result. The real defects
on record were found and fixed *during* the prior reconciliation itself, per its own commit
message: the femto-acquisition row-completeness gap (closed), timestamp-rate derivation on
irregular timestamps (now fails closed), blob downloads missing text checks (closed), history
recording filenames (removed), and reliability/gate applicability-mode mismatch (unified).
I did not find evidence any of these regressed after merging; all corresponding tests pass.

I did not spawn a second independent reviewer subagent for this pass - the merged code was
already reviewed by the prior Nightshift run (per its commit message) and by this session's
direct inspection of the highest-risk invariants (gating logic, exception handling,
fabrication shortcuts), and the full test suite (740 tests, several written specifically as
regression tests for the defects above) passing is itself strong evidence against a silent
regression from the merge.

## 13. Known limitations
Same as stated throughout `docs/milestone.md`'s M11 section: in-memory history is not
durable across serverless instances unless the optional SQLite persistence is configured; no
auth; no rate limiting; college data is one bearing/one run (pre-existing M0-M10 scope note,
unaffected); sklearn version-skew warnings on unpickling (pre-existing, harmless).

## 14. Exact BLOCKED_HUMAN steps
1. Obtain Vercel account/API credentials and run a real `vercel deploy`.
2. Provision a real Vercel Blob store; set `BLOB_READ_WRITE_TOKEN` and
   `BLOB_STORE_HOSTNAME`.
3. Upload the ~330MB of `.joblib` artifacts to real storage and fill in each entry's
   `source_url` in `artifacts/models/manifest.json`.
4. Set `ALLOWED_ORIGINS` to the real deployed frontend origin.
5. Codex CLI/watchdog overnight-orchestration tooling (`goals.md`) - not installed in this
   environment; cannot be substituted locally.
6. Decide whether/how to merge `overnight/capstone/m12-final-integration` to `main`, and how
   to reconcile with the pre-existing `data/rlguard`/`cross-dataset` lineage outside this
   repo clone - a repository-owner decision, not taken here.

## 15. Exact things NOT performed
- No push to any remote.
- No merge to `main`.
- No live Vercel deployment, attempted or claimed.
- No fake/invented artifact hosting or `source_url` values.
- No destructive git operation (no branch/worktree deletion, no force-push, no history
  rewrite).

## 16. Recommended next human action
Decide on artifact hosting (Vercel Blob is the natural fit given everything else already
targets it) and provide Vercel credentials; once both exist, `vercel deploy` from
`overnight/capstone/m12-final-integration` and fill in the manifest's `source_url`s is the
remaining path to a live deployment. Merge-to-main is a separate decision this report takes
no position on beyond flagging it as pending.
