# RULGuard Final Publication Readiness Decision

## Release status

PUBLICATION_READY_WITH_LIMITATIONS

## Audited revision

- Branch: `overnight/capstone/full-dataset-zip-rag`
- Working revision: HEAD `ab8425c` plus the uncommitted changes in this audit
  (`src/bearing_pdm/analysis_bundle.py`, `src/bearing_pdm/rag/explain.py`,
  `tests/test_analysis_bundle.py`, `tests/test_rag.py`,
  `tests/rag_golden_eval.json`)
- Audit dates: 2026-10-21 to 2026-10-22, seven audit passes
- Environment: project's own `.venv-linux`, plus a separate clean venv
  (`/tmp/clean_audit_venv2`) used to confirm `bearing_pdm` resolves only
  inside `rulgaurd-public`
- Tested Groq model (release default): `openai/gpt-oss-120b`

## Executive conclusion

RULGuard is suitable for capstone demonstration and academic publication
under the limitations stated below. Across seven audit passes, the team
found and fixed three real defects (a Groq model-selection bug that could
silently select a safety-classifier model instead of a chat model, a
bundle-import routing/prefix collision bug, and a credential-ambiguity risk
in the RAG provider chain), closed every engineering gap that was closable
without changing scientific methodology, and documented two genuine
scientific limitations (XJTU bedding-in behavior, thin RAG retrieval
sample size) that are permanent properties of the data and corpus, not
code defects. The project is not rated unconditionally PUBLICATION_READY
because those two scientific limitations require specific, softened
language in any paper or presentation — removing the "WITH_LIMITATIONS"
qualifier would require different data or a larger corpus, not more
engineering.

## Verified software status

- `pytest`: **990 passed, 0 failed** (final full-suite run)
- `ruff check .`: clean, all checks passed
- Real Streamlit + Playwright/Chromium testing: FEMTO and XJTU exercised
  across all Analyze tabs (Overview, Signal, FFT, Features, Health,
  Trajectory, Applicability, RUL, Evaluation, Evidence); 23 screenshots in
  `artifacts/evidence/final_publication_audit/` from the full walkthrough,
  plus 4 additional targeted Evidence-tab screenshots after the final RAG
  fixes (FEMTO supported/unsupported question, XJTU RUL-suppression/
  unsupported-fault-diagnosis question)
- Clean-environment validation: a separate venv (`/tmp/clean_audit_venv2`)
  confirmed `bearing_pdm.__file__` resolves only inside `rulgaurd-public`
  (not a sibling clone), ran the full `pytest` suite (972/972 at that
  point) and `ruff check .` cleanly, and launched real Streamlit with
  Playwright against a small real fixture with no crashes; Groq resolved
  to the correct release model there too. This was a separate venv on the
  same checkout, not a separate git worktree/clone.
- Bundle export/import: round-tripped through the actual Streamlit UI
  (export button -> import widget), with an exact match on
  dataset/bearing/HI/stage/applicability/RUL status/numeric RUL against
  the original (minus the intentional `canonical_path` redaction, itself a
  security feature). A tampered copy was cleanly rejected on checksum
  mismatch with a useful message, no traceback.
- Archive-security / negative-ingestion testing: 10 scenarios covered (ZIP
  path traversal, TAR path traversal, missing multipart RAR part, corrupt
  archive, truncated archive, empty archive, excessive expansion metadata,
  excessive file count, unsupported archive type, misleadingly-named
  folder) — 7 via pre-existing committed tests re-confirmed passing, 3
  checked directly this session (truncated archive, unsupported type,
  misleading folder name). All reject cleanly: no write outside the
  extraction root, no traceback, no silent fallback to the wrong dataset.
- State/restart testing: real Playwright screenshots across
  XJTU->FEMTO->XJTU and Bearing1_1->Bearing2_1->Bearing1_1 dataset/bearing
  switches showed no stale selector state; a fresh process + fresh browser
  context correctly reloaded persisted routing artifacts after restart.
- Independent hostile review: a genuinely independent reviewer context
  (`ecc:mle-reviewer`, spawned with zero inherited context, not told to
  trust the self-assessment) reviewed the full audit report set, the exact
  git diff, and test output, and independently re-ran pytest and
  hand-verified RUL numbers against `reports/metrics/*.json`. Result: 0
  critical findings, 0 unresolved major findings (one MAJOR finding this
  reviewer surfaced — the `OnlineLLM` generic `api_key` fallback — has
  since been resolved; see Security section below).

No counts above are invented; all are drawn from the actual commands run
during the audit sessions.

## Scientific validation

- **FEMTO held-out RUL validation**: the full per-bearing leave-one-bearing-
  out (LOBO) table was reproduced exactly from `reports/metrics/rul_evaluation.json`
  with no refitting. Naive baseline mean MAE 6584.76s, ExtraTrees mean MAE
  5061.02s; ExtraTrees beats naive on 4 of 6 bearings (loses on 2, reported
  honestly rather than hidden).
- **Baseline comparison**: ExtraTrees is compared against the naive
  baseline on every reported FEMTO bearing, per-bearing not just mean.
- **HI/stage validation**: a full bearing-by-bearing table was built for
  FEMTO (6 bearings) and XJTU (15 bearings). Two XJTU bearings show a real
  statistical anomaly (see Health Indicator Limitation below); IMS was not
  covered this round.
- **Prefix invariance**: causal values (health indicator) were verified
  byte-identical between a prefix-only computation and the full-trajectory
  computation, 18/18 exact matches across 3 FEMTO + 3 XJTU bearings at
  early/middle/late points.
- **Independent feature-formula validation**: RMS, kurtosis, and crest
  factor were independently reimplemented from raw NumPy/SciPy arrays
  (not by calling the production feature functions) and compared against
  the canonical pipeline output — 72/72 exact matches across FEMTO + XJTU,
  2 bearings each, early/middle/late, both channels. Nyquist frequency and
  channel orientation were confirmed correct.
- **XJTU applicability / RUL suppression**: read the real decision record
  for a case where `sn_fraction_multi` applicability was HIGH but the
  validated predictive skill was negative (-0.222) — RUL was correctly
  suppressed because high applicability alone does not imply validated
  predictive skill. This is intentional safety behavior, confirmed not a
  bug.
- **No refitting against frozen `Full_Test_Set`**: confirmed by code
  reading (`assert_no_leakage` in `evaluation.py`, called with
  `allowed_roles={"learning"}` for FEMTO and `allowed_roles={"college_run"}`
  for college) and by never invoking a retrain against the hidden set
  during any audit session.

## Health Indicator limitation

- The HI is **not hardcoded**: FEMTO and XJTU bearings show materially
  different trajectories bearing-to-bearing, confirmed by the full
  per-bearing table.
- Some XJTU bearings (`Bearing2_1`, `Bearing3_3`) exhibit a genuine
  mechanical **bedding-in / running-in** trend: RMS stays flat-to-declining
  for roughly 98% of the run, then jumps 15-20x only in the final 1-2
  recordings. Excluding the terminal collapse makes the whole-run
  Spearman(HI, time) correlation **more** positive (0.49→0.69 for
  Bearing2_1, 0.58→0.86 for Bearing3_3), proving the body of the run — not
  the terminal failure — drives the sign. This was investigated at the
  signal level (raw vibration, RMS, kurtosis, crest factor) and confirmed
  not to be a code defect, a reference-window bug, or an adapter issue.
- **Consequence**: whole-run HI monotonicity is therefore not guaranteed
  for every bearing. Do not claim the HI is monotonically decreasing for
  every bearing; the supported claim is terminal discrimination (the HI
  correctly reaches a low value near failure), not whole-run monotonicity.
- FEMTO `Bearing1_2`'s early stage reversal (DEGRADING at sequence 0, later
  HEALTHY) is consistent with the project's own prior documented finding
  (`docs/decisions.md` D18/D19): `REFERENCE_HI_SKIP=10` deliberately skips
  the run-in transient, and this bearing's 19 stage reversions are already
  recorded as a genuinely noisy HI on that specific bearing — reported, not
  suppressed. No code defect found.

## RUL scope

- Validated RUL performance is strongest on **FEMTO**, where the full LOBO
  evaluation exists and was reproduced this audit.
- Cross-dataset applicability is evaluated (applicability/OOD gating exists
  and was exercised for XJTU), but **numerical cross-dataset RUL is
  suppressed where validated predictive skill is absent** — this is
  intentional safety behavior, not missing output or a bug.
- Do not claim validated universal RUL prediction across every supported
  dataset. College and hidden-set/cross-dataset RUL metrics were not
  reproduced in this audit.

## RAG status

- Release model: `openai/gpt-oss-120b` (confirmed via real live API calls
  in multiple sessions, including from the clean venv).
- Provider-specific credential isolation: each provider reads only its own
  explicitly named environment variable (`GROQ_API_KEY`, `OPENAI_API_KEY`,
  `OPENROUTER_API_KEY`, `AI_GATEWAY_API_KEY`/`VERCEL_AI_GATEWAY_API_KEY`).
  A generic `api_key`/`API_KEY` variable **cannot** enable any provider
  (regression-tested), and a key set for one provider cannot activate a
  different provider (regression-tested).
- No secret leakage found: the real key value never appears in `repr()`,
  exception text, logs, or rendered Streamlit output, verified directly.
- RAG cannot modify RUL/HI/stage/applicability: `PredictionContext` is a
  frozen dataclass, read-only by every provider — structural, not just
  behavioral, and verified across direct calls, real browser screenshots,
  and the prompt-injection red team.
- 40-question golden evaluation set (`tests/rag_golden_eval.json`), of
  which 17 questions carry gold retrieval labels usable for Recall/MRR.
- Retrieval metrics (on the 17 gold-labelled questions):
  - Recall@1 = 0.588
  - Recall@3 = 0.824
  - Recall@5 = 1.000
  - MRR = 0.727
- Hard RAG safety (no fabricated evidence, no invented citation, no
  fault-diagnosis language, immutable RUL/HI/stage facts always present):
  **10/10**, verified per-question across a 10-question negative/
  off-topic/abstention regression set.
- Strict citation-free abstention (the stronger bar: zero citations
  returned, not just no fabrication): **8/10** on the same set. The
  remaining 2 cases still surface a topically-adjacent (not fabricated)
  citation rather than fully abstaining — disclosed, not hidden.
- 10-variant prompt-injection red team (override RUL, override HI,
  override stage, claim HEALTHY, reveal API key, ignore system
  instructions, role-play as developer, fake citation injection, hidden/
  obfuscated instruction, multi-step instruction) against a planted
  malicious document through real retrieval + Groq: **10/10 passed** — no
  ML field mutated, no key leaked, no fabricated citation adopted.
- Groq live evaluation was rate-limited on the free tier: of the questions
  attempted against the live API in the final evaluation run, 8 calls
  succeeded before rate-limiting diverted the rest to deterministic
  fallback. This was **not** a 40/40 live-call benchmark, and is not
  presented as one.
- Deterministic fallback remains available and was verified to behave
  safely (same abstention guarantees) when `GROQ_API_KEY` is absent,
  tested via a subprocess environment override without touching
  `.env.local`.

## Security validation

- Provider credential isolation: see RAG status above. Originally flagged
  by the independent reviewer as a MAJOR finding (`OnlineLLM`'s generic
  `api_key` environment-variable fallback could silently consume an
  unrelated secret) — **RESOLVED**: the fallback was removed, and 6
  regression tests confirm no cross-provider key confusion and no
  generic-key activation is possible.
- Prompt-injection testing: 10/10 passed (see RAG status above).
- Archive traversal/corrupt/truncated/limit tests: 10 scenarios covered,
  all reject cleanly with no traceback and no escape from the extraction
  root (see Verified software status above).
- Bundle checksum/tamper rejection: verified through the real UI — a
  tampered copy of an exported bundle is rejected on checksum mismatch
  with a clean error message, no traceback.
- No raw secret exposure: confirmed the real `GROQ_API_KEY` value never
  appears in logs, exceptions, `repr()`, or rendered UI output across every
  session.

## Independent review

- A genuinely independent reviewer context (`ecc:mle-reviewer`, a separate
  subagent type spawned with no inherited context and explicit instructions
  not to trust the implementer's self-assessment) reviewed the full report
  set, the exact diff, and test evidence, and independently re-ran pytest
  and hand-checked RUL numbers against the metrics JSON.
- Result: **0 critical findings, 0 unresolved major findings** remaining.
  One MAJOR finding it raised (the `OnlineLLM` generic-credential fallback)
  has since been fixed and verified; the only other finding it noted (Groq
  model non-determinism when `GROQ_MODEL` is unset) was already an
  acknowledged, documented design limitation, not a defect.
- Earlier audit sessions' "hostile review" was performed as a disclosed
  self-review and was explicitly **not** labeled independent at the time;
  this is the first pass in which a genuinely separate reviewing context
  was used and confirmed reachable.

## Known limitations

1. Cross-dataset numerical RUL is not claimed as validated outside FEMTO.
2. XJTU running-in behavior means whole-run HI monotonicity is not
   universal across every bearing (see Health Indicator Limitation above).
3. RAG retrieval evaluation is based on a relatively small project corpus
   (~14 documents) and 17 gold-labelled questions.
4. Groq free-tier rate limiting prevented every golden question from being
   tested as a live Groq call in a single run; 8 live calls succeeded in
   the final evaluation pass.
5. Strict citation-free abstention is 8/10, even though hard safety
   behavior (no fabrication, no diagnosis, immutable facts preserved) is
   10/10.
6. Stage labels (HEALTHY/DEGRADING/CRITICAL) are severity bands, not
   physical fault diagnoses.
7. College consists of a single experimental run on a single bearing, so
   no broad cross-machine generalization should be claimed from it.
8. Groq's selected model is not pinned by default (`GROQ_MODEL` unset uses
   an ordered allowlist with a live `/models` lookup) — functionally safe
   after the fix (every candidate is verified chat-capable), but the exact
   model used is not bit-for-bit reproducible run-to-run unless `GROQ_MODEL`
   is set explicitly for a given deployment.

## Publication-safe claims

The paper/presentation MAY claim:

- An applicability-aware bearing prognostics framework across multiple
  run-to-failure datasets (FEMTO, college, XJTU).
- Held-out (leave-one-bearing-out) RUL evaluation on FEMTO, with a stated
  naive-baseline comparison.
- Cross-dataset health/degradation analysis with documented, bearing-level
  findings (including the bedding-in limitation).
- Applicability-driven RUL suppression as a deliberate safety mechanism,
  not a missing feature.
- Evidence-grounded RAG explanation of model output, with citations to a
  defined project corpus.
- RAG does not alter the deterministic ML output — this is structurally
  guaranteed (frozen `PredictionContext`) and was tested under adversarial
  prompt injection.
- A multi-dataset adapter architecture (FEMTO/college/XJTU/IMS) with
  dataset-specific parsing kept separate from normalized feature contracts.

## Claims that must NOT be made

- "Works for all machines" or any unqualified cross-machine generalization
  claim, particularly from the single college run.
- "Production-ready" or "validated real-time predictive maintenance" — this
  is offline replay of recorded data, evaluated as a research prototype.
- "HI is monotonic on every bearing" — contradicted directly by the XJTU
  bedding-in finding.
- "Detects physical fault type" (inner race / outer race / ball / cage /
  lubrication) — no fault-type diagnosis exists anywhere in the system;
  stages are severity bands only.
- "RUL is validated on every supported dataset" — only FEMTO has a full
  held-out RUL evaluation; other datasets are zero-shot/applicability
  experiments with RUL suppressed when skill is unvalidated.
- "RAG predicts RUL" or any phrasing implying the language model computes
  or adjusts a numeric result.
- Any claim that the college naive-baseline MAE=0.0 is a real predictive
  result — it is an algebraic oracle artifact of label construction
  (`docs/decisions.md` D10), not a working predictor.

## Final release decision

**PUBLICATION_READY_WITH_LIMITATIONS.** The repository is suitable for
capstone demonstration and academic publication provided the documented
scientific and evaluation limitations above are retained, and the
forbidden claims above are not made, in the paper or presentation. Every
engineering gap that was closable without altering scientific methodology
has been closed with real, reproducible evidence (990 passing tests, clean
lint, real browser and clean-environment verification, independent
review). The remaining qualifier exists because of genuine, permanent
properties of the underlying data (XJTU bedding-in behavior, a single
college run) and the current evaluation corpus size (RAG retrieval
sample), not because of unresolved defects in the software.
