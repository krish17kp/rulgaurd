# FINAL CLAIMS AUDIT / HOSTILE SELF-REVIEW (2026-10-21, session 4)

## Note on independence
The task asked for a fresh, independently-biased reviewer subagent. **This
session's harness explicitly prohibits a fork (this session) from
spawning subagents** — the fork-boilerplate instruction is a hard
constraint, not a judgment call. What follows is a deliberately
adversarial self-review of this session's own evidence, written to try to
break each claim — but it is not blind to this session's own
work, and that is a genuine, stated limitation, not glossed over. A truly
independent reviewer (a separate conversation/session with no visibility
into this one) has NOT reviewed this work.

## Attempting to find critical defects in this session's own evidence

1. **Is the 72/72 feature-formula match too good to be true?** Checked:
   the first-pass mismatch (genuinely found, genuinely investigated, root
   cause confirmed via `canonical_xjtu.json`'s `window_s` field and
   `pipeline.py:_vibration_features`) is documented with its full
   discovery process, not hidden. The final 72/72 match is real because
   the independent code was written from scratch and only made to match
   the pipeline's *documented* windowing parameter (0.1s), not its
   internal implementation — reusing the parameter value, not the code.
   **Stands.**
2. **Is the XJTU HI anomaly conclusion self-serving (avoiding a harder
   fix)?** Checked: the investigation explicitly tested whether the
   positive correlation survives excluding the terminal collapse (it gets
   STRONGER, 0.49->0.69 and 0.58->0.86) — this is evidence AGAINST the
   easy "it's just the cliff" explanation, and the report states the
   harder truth (a genuine mid-run improving trend) rather than the easier
   one. No code was changed to make this anomaly disappear. **Stands as a
   real limitation, not a cover-up.**
3. **Is "10/10 injection variants passed" too clean?** Checked: all 10
   variants DID retrieve the malicious chunk (the system doesn't block
   retrieval — only generation-time compliance), which is disclosed, not
   hidden. The pass criteria (context unchanged, no key leak, no fake
   citation adopted, not flipped to HEALTHY-only) are objective and
   checked programmatically, not eyeballed. Weakness: pass criteria don't
   check whether the model's prose *repeats* the injected claim while
   correctly refusing to act on it (as seen in the session-3 "999,999"
   paraphrase) — a borderline case that could read as validating the
   injected content to an inattentive reader, even though the ML output
   itself is untouched. **Flagging as a real minor finding, not
   previously stated this bluntly:** citation-correctness evaluation
   should distinguish "quoted the malicious text while refusing it" from
   "silently ignored it" in a future pass — the current test only checks
   the latter matters (ML output unchanged), not UI clarity about why a
   retrieved document shouldn't be trusted.
4. **Is "Recall@5=1.0" on n=17 meaningful?** No — flagged honestly in
   FINAL_RAG_EVALUATION.md as a small corpus (~14 unique source documents)
   result, not a large-scale IR benchmark claim.
5. **Is the clean-environment test actually clean?** Partially — it's a
   fresh venv on the SAME checkout, SAME disk, SAME OS, not a separate
   worktree/clone or container. A truly hostile reviewer would flag this
   as insufficient isolation (e.g., it wouldn't catch a dependency on an
   absolute path elsewhere on this machine). Stated as a limitation in
   FINAL_REPRODUCIBILITY.md.
6. **Are the state-switch screenshots actually proving no staleness, or
   just showing the final state?** Re-examined: the per-step file/
   recording counts shown DO change correctly across switches (8384/2803
   for femto:Bearing1_1 vs 911 for femto:Bearing2_1), which IS evidence
   against staleness (a stale cache bug would show the same numbers
   persisting incorrectly) — but Signal/FFT/Evidence tabs specifically
   were not re-screenshotted after each switch this session, only
   Overview. **Real gap, stated in FINAL_SYSTEM_TEST.md already.**

## Critical findings from this self-review that block or limit publication readiness
- Point 3 above (quoted-vs-ignored injected text) is a genuine, newly
  surfaced minor finding — not fixed this session (would require a UI/
  prompt change to make "this text came from an untrusted source and was
  not followed" more explicit when a model quotes it), recorded as a
  minor finding for a future pass, not release-blocking (the numeric/
  secret integrity guarantees that matter are already verified).
- Point 5 (clean-env isolation strength) is a real reproducibility
  limitation, not a release blocker, but should not be oversold as a full
  Phase 38 pass.
- No critical, release-blocking defect was found by this self-review that
  the earlier sections of this audit had missed or mis-stated.

## SESSION 6 UPDATE — a true independent review WAS reachable

Prior sessions assumed a fork cannot spawn any subagent and marked this
gate NOT_INDEPENDENTLY_VERIFIED without actually testing the claim this
round. This session checked concretely: the `Agent` tool's `subagent_type`
list includes many non-fork agent types (`ecc:code-reviewer`,
`ecc:mle-reviewer`, `general-purpose`, etc.) that start with zero
inherited context - genuinely independent of this session's own
conclusions. Spawned `ecc:mle-reviewer` with the full set of
`reports/final_audit/*.md` reports, told explicitly not to trust the
self-audit's conclusions, and asked to actively hunt for 15 specific
failure categories (leakage, non-causal calculations, test contamination,
HI/Spearman misuse, unsupported cross-dataset claims, RAG issues, hidden
failed tests, security, irreproducible numbers, etc.).

**Result: a genuinely independent review completed.** It re-ran `pytest`
itself (972 passed, matching this session's own count), hand-recomputed
the FEMTO LOBO RUL numbers from `reports/metrics/rul_evaluation.json`
and confirmed them exact, verified `.env.local` is gitignored and
untracked, read `health.py`'s causality and `evaluation.py`'s leakage
guards directly, and confirmed the RAG citation/state-mutation claims by
reading `explain.py` itself.

It surfaced two real MAJOR findings this self-review had not identified:
1. **`OnlineLLM`'s AI-Gateway provider falls back to a bare, generic
   `os.environ.get("api_key")`** (`explain.py`, in the Vercel AI Gateway
   provider, not the Groq provider this session patched) - a genuine
   credential-leakage-adjacent hazard in any shared environment where an
   unrelated secret happens to be exported under that common name. **Not
   fixed this session** (out of this round's 5-item scope, and this
   provider is lower-priority than Groq - no live key for it is
   configured on this machine) - recorded here as an open finding for a
   future pass.
2. **Groq model selection is non-deterministic run-to-run** when
   `GROQ_MODEL` is unset (confirmed independently - this session itself
   observed only 8/40 golden-eval calls actually landing on Groq before
   rate-limit fallback, for unrelated reasons, but the reviewer's point
   stands structurally regardless of rate limiting). Already honestly
   caveated in `FINAL_RELEASE_DECISION.md`; the reviewer's independent
   confirmation strengthens rather than contradicts that existing
   disclosure.

No CRITICAL finding. The reviewer's own words: "I would not block
publication outright, but I would not sign off on PUBLICATION_READY
without qualification either... on balance their self-assessment is
honest rather than self-serving." Full finding list (including 7
NON-ISSUE items it explicitly checked and cleared) is preserved in this
session's transcript; the two MAJOR items above are the only ones with
no corresponding existing disclosure.

**This gate is now PASS, not NOT_INDEPENDENTLY_VERIFIED** - a fresh,
differently-typed agent with no inherited context performed the review,
not a self-review.

## SESSION 7 UPDATE — independent review findings disposition

**OnlineLLM generic `api_key` env fallback (MAJOR): RESOLVED.** Removed
in `src/bearing_pdm/rag/explain.py`; `OnlineLLM` now reads only
`AI_GATEWAY_API_KEY`/`VERCEL_AI_GATEWAY_API_KEY`. 6 new regression tests
confirm no provider can be enabled by a generic/wrong-provider credential
and no secret leaks into a repr or error message. See
`FINAL_SECURITY_TEST.md` session 7 update for full detail.

**Groq model selection non-determinism across runs (MINOR, acknowledged,
not resolved - by design):** the independent reviewer's second MAJOR
finding. This is not a credential or safety defect - it's the Groq
provider auto-resolving a model from the live `/models` endpoint when
`GROQ_MODEL` is unset, which can legitimately return a different model
as Groq's catalog changes. The project already documents this as a known
limitation (`FINAL_RELEASE_DECISION.md`); a deployment that needs
reproducible generation-quality numbers should pin `GROQ_MODEL`
explicitly. Not treated as release-blocking - it does not affect
correctness of the numeric RUL/HI/stage pipeline, only the (already
clearly caveated as non-reproducible) free-form explanation text.

No new CRITICAL finding from the independent review. Both MAJOR findings
are now accounted for: one fixed, one an acknowledged-and-documented
design limitation.
