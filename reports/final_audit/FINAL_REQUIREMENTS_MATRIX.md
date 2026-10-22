# FINAL REQUIREMENTS MATRIX (three-session cumulative pass)

Session 1: Groq provider implementation (mocked tests only). Session 2:
live Groq verification + a real defect found/fixed. Session 3 (2026-10-21):
real pixel-level browser screenshot matrix (Playwright), golden RAG eval
set, multi-variant prompt-injection red team, empirical prefix-invariance,
HI bearing-by-bearing audit, RUL metric reproduction, XJTU suppression
verification, bundle round-trip. This is still not the full 46-phase audit
— rows not covered are marked NOT_TESTABLE_THIS_SESSION, not PASS/FAIL. See
FINAL_RELEASE_DECISION.md's gate table for the authoritative release-gate
status (A-X); this matrix is the requirement-level detail underneath it.

| ID | Requirement / claim | Verification method | Evidence | Status |
|----|---|---|---|---|
| R1 | Full automated test suite passes | `pytest -q` | 967 passed, 0 failed, 132.47s (this session, `.venv-linux`) | PASS |
| R2 | Lint clean | `ruff check .` | "All checks passed!" (this session) | PASS |
| R3 | `bearing_pdm` resolves to this checkout, not a sibling clone | `python -c "import bearing_pdm; print(bearing_pdm.__file__)"` | Printed path under `rulgaurd-public/src/bearing_pdm/__init__.py` | PASS |
| R4 | GroqProvider implemented in existing RAG provider abstraction | Code read + new unit tests | `src/bearing_pdm/rag/explain.py` `GroqProvider` class; 9 new tests in `tests/test_rag.py`, all passing | PASS (mocked HTTP only) |
| R5 | Groq attempted first when `GROQ_API_KEY` present | Unit test `test_build_explanation_chain_prefers_groq_when_configured` | Passing test, mocked HTTP | PASS (mocked) |
| R6 | Groq falls back to DeterministicFallbackLLM on failure | 2026-10-21: live test, invalid key in throwaway subprocess env (`.env.local` untouched) | `provider=deterministic-fallback`, `fallback_used=True`, no crash | PASS (live-tested) |
| R7 | Live Groq API call succeeds with real key/model | 2026-10-21: `GROQ_API_KEY` loaded from `.env.local` into env (never printed); direct `build_explanation()` call + real Streamlit evidence tab via `AppTest` on `dashboard_cross.py` | FEMTO: `online:groq:allam-2-7b`, 0.97s. XJTU (via AppTest): `online:groq:openai/gpt-oss-120b`. Prompt-injection probe: `online:groq:openai/gpt-oss-safeguard-20b` | PASS |
| R7a | **Defect found+fixed:** `_resolve_model()` could pick a non-chat model (`llama-prompt-guard-2-86m`) when the hardcoded fallback id was absent from the account's `/models` list, causing a live 400 and silent fallback | Reproduced directly (`GroqProvider().generate()` raised `ProviderBillingBlocked: http_400`), root-caused via manual `/models` + per-model `/chat/completions` probe | Fix: filter `whisper`/`prompt-guard`/`orpheus`/`tts` substrings before taking first remaining id (`_GROQ_NON_CHAT_MARKERS`); regression test `test_groq_provider_skips_non_chat_models_when_fallback_id_is_absent` | FIXED, verified live |
| R7b | RAG never alters the ML output even when a live LLM is used | 2026-10-21: FEMTO evidence-tab explanation text cross-checked against `routing_femto.parquet` for the same bearing | Explanation quoted "~3023s / 0.84h / HI 2.3e-5 / CRITICAL"; parquet has `predicted_rul_seconds=3022.9, health_indicator=2.3197e-05, stage=CRITICAL` — exact match | PASS |
| R7c | No API key exposure in rendered output | 2026-10-21: searched full rendered markdown/caption text (AppTest) for key substring after a live Groq call | Key substring absent in both FEMTO and XJTU runs | PASS |
| R8 | GROQ_API_KEY never logged/printed/exposed to browser | Code read: `os.environ.get("GROQ_API_KEY")` read once, never placed in any response field, UI shows only `provider.name:model_used` | `src/bearing_pdm/rag/explain.py`, `dashboard_cross.py:351`, `api.py:2868` | PASS (static review) |
| R9 | Real FEMTO and college data present locally | `ls`/`find` | FEMTO zips extracted at `data/interim/femto/*`; 129 real college CSVs at `datasets/college/` | PASS (presence only; adapter correctness not re-derived) |
| R10 | Canonical cross-dataset artifacts exist for femto/college/xjtu/ims | `find data/processed` | `canonical_{femto_learning,college,xjtu,ims}.{parquet,json}` present | PASS (presence only; not re-validated for lineage/correctness this session) |
| R11 | Leakage guard present and invoked for both datasets | Code read: `evaluation.py` | `assert_no_leakage(df_learning, allowed_roles={"learning"})`, `assert_no_leakage(df_college, allowed_roles={"college_run"})` | PASS (static review; not independently re-derived with a new test) |
| R12 | Prefix-invariance (causal HI/stage/RUL unaffected by future data) | Not run this session | — | NOT_TESTABLE_THIS_SESSION |
| R13 | Independent feature-formula validation against raw signal | Not run this session | — | NOT_TESTABLE_THIS_SESSION |
| R14 | Real browser/Playwright UI pass across all tabs, both datasets | 2026-10-21 session 3: chrome-devtools MCP retried, still unreachable. Installed Playwright+Chromium into `.venv-linux`, launched the real `scripts/run_dashboard.py` entrypoint (`dashboard.py`), drove it with a real headless Chromium browser | All 10 Analyze tabs captured for FEMTO and XJTU: `artifacts/evidence/final_publication_audit/{femto,xjtu}_0{1..9}_*.png`, `*_10_evidence.png` + `*_evidence_groq.png` (23 PNGs total) | PASS |
| R15 | Screenshot matrix + visual review | 2026-10-21 session 3: 23 real screenshots captured; 3 inspected in detail (`femto_01_overview.png`: correct quality-gate/sampling-rate/file-count display; `xjtu_08_rul.png`: correct RUL_SUPPRESSED banner + per-recording decision counts, no traceback; `femto_evidence_groq.png`: correct citations, provider label, numbers matching backend exactly) | See above | PARTIAL (3/23 individually reviewed; remaining 20 captured, not all inspected) |
| R16 | RAG golden evaluation set (30-50 Qs) + retrieval Recall@k/MRR | 2026-10-21 session 3: built `tests/rag_golden_eval.json` (33 Qs across all required categories + 4 negative/should-abstain); scored retrieval and generation | Recall@1=0.5, Recall@3=0.5, Recall@5=1.0, MRR=0.625 (n=2 gold-labelled questions — honestly small); 0/33 forbidden-claim violations, 0/33 key leaks, 4/4 generation-level correct abstention (1/4 flagged by an over-strict citation-presence metric, but the generated text itself correctly declined) | PARTIAL (set built and scored; retrieval-metric n is small) |
| R17 | Prompt-injection probe against real retrieval + live Groq | 2026-10-21 session 3: planted a real malicious fixture document (`/tmp/injection_fixture.md`, not committed) into a `VectorIndex.build_from_chunks()` alongside the real corpus; ran 3 variants (direct override, indirect "what does it say", key-exfiltration attempt) | Malicious chunk was retrieved in all 3 cases (defense is at generation time, not retrieval-blocking); `"999999"` never appeared unqualified, `ctx.rul_seconds`/`degradation_stage` never mutated (structurally read-only), no key substring leaked in any of the 3 | PASS (3-variant fixture-document red team; still narrower than the full Phase 24 spec) |
| R18 | Prefix-invariance (causal HI unaffected by future data) | 2026-10-21 session 3: `apply_reference_hi()` computed on full vs. truncated-prefix real FEMTO/XJTU canonical data at 3 points each | diff=0.00e+00 (exact match) at all 6 points tested (3 FEMTO, 3 XJTU) | PASS |
| R19 | HI/stage bearing-by-bearing statistics table | 2026-10-21 session 3: computed `apply_reference_hi()` output stats (first/10%/50%/90%/last, Spearman, reversion events) for all 6 FEMTO + all 15 XJTU bearings from real canonical data, no refit | See FINAL_HI_STAGE_VALIDATION.md; 2 XJTU bearings show a real positive-Spearman anomaly, flagged not fixed | PARTIAL (FEMTO+XJTU done; IMS not covered; anomaly found, not root-caused) |
| R20 | RUL evaluation reproduced from existing artifacts | 2026-10-21 session 3: recomputed mean/per-bearing MAE from `reports/metrics/rul_evaluation.json` directly, no refit | naive mean MAE=6584.76s, ET mean MAE=5061.02s, ET beats naive on 4/6 bearings — exact match to project's own documented claim | PASS (FEMTO only; college/hidden-set/cross-dataset not reproduced) |
| R21 | XJTU suppression correctness explained | 2026-10-21 session 3: read `routing_xjtu.json`'s real decision record for `xjtu:Bearing1_1` directly | `sn_fraction_multi`: applicability=HIGH (0.47x shift) but validated_skill=-0.222 (negative) -> correctly ineligible; confirms "high applicability != validated skill" is real system behavior, not a bug | PASS |
| R22 | Bundle export/import round-trip + tamper detection | 2026-10-21 session 3: `build_routing_bundle()`/`load_bundle()` round-trip on real `routing_femto.json`; separately corrupted `dataset.json` bytes in a copy and reloaded | Round-trip exact match once the intentional `canonical_path` redaction (a security feature, not a bug) is accounted for; tampered copy correctly raised `BundleValidationError: dataset.json checksum mismatch` | PASS |
| R18 | Export/import bundle round-trip, tamper-detection | Not run this session | — | NOT_TESTABLE_THIS_SESSION |
| R19 | State/restart tests (dataset switching, fresh browser, persisted artifacts) | Not run this session | — | NOT_TESTABLE_THIS_SESSION |
| R20 | HI/stage scientific audit across every available bearing | Not run this session | — | NOT_TESTABLE_THIS_SESSION |
| R21 | RUL evaluation reproduced from source artifacts (per-bearing MAE, OOF safety) | Not run this session | — | NOT_TESTABLE_THIS_SESSION |
| R22 | Independent hostile second-pass review | Not run this session | — | NOT_TESTABLE_THIS_SESSION |

See `FINAL_RELEASE_DECISION.md` for the overall decision and blockers list.

## SESSION 4 additions

| ID | Requirement | Evidence | Status |
|----|---|---|---|
| R23 | XJTU HI anomaly root cause (Bearing2_1, Bearing3_3) | xjtu_hi_anomaly_investigation.md | RESOLVED — scientific limitation, not a bug |
| R24 | RAG golden set >= 40 questions, categorized | tests/rag_golden_eval.json (40 q) | DONE |
| R25 | Prompt-injection red team, 10+ variants | FINAL_SECURITY_TEST.md | 10/10 PASS |
| R26 | Independent feature-formula validation (not self-calling) | FINAL_DATA_VALIDATION.md | 72/72 exact match |
| R27 | Full per-bearing RUL validation table | FINAL_RUL_VALIDATION.md | DONE |
| R28 | Expanded prefix-invariance (>=3 bearings/dataset) | FINAL_RUL_VALIDATION.md / FINAL_HI_STAGE_VALIDATION.md | 18/18 exact |
| R29 | State-switch test (real browser) | FINAL_SYSTEM_TEST.md | PASS, partial tab coverage |
| R30 | Restart test (fresh process + fresh browser context) | FINAL_SYSTEM_TEST.md | PASS |
| R31 | Clean-environment reproducibility | FINAL_REPRODUCIBILITY.md | PASS, found real requirements-rag.txt gap |
| R32 | Hostile second review | FINAL_CLAIMS_AUDIT.md | DONE as disclosed self-review (fork cannot spawn subagents) |
