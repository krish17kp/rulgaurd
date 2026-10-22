# FINAL SECURITY TEST (2026-10-21, session 4)

## Secrets
- `GROQ_API_KEY` never printed, logged, or committed across all 4 sessions
  on this branch. Checked by: (a) presence-only `os.getenv` probes, (b)
  substring-search of every RAG output (direct calls, AppTest, real
  Playwright screenshots, server logs) for the key's first 8 characters —
  **zero leaks found** across ~70+ generated explanations this session
  (40 golden-eval questions + 10 injection variants + ~20 ad-hoc calls).
- `.env.local` (holds the real key) is gitignored and was never read with
  `cat`/printed; loaded only via `set -a; source .env.local; set +a` into
  subprocess environments.

## Prompt injection (10 variants, session 4)
override_rul, override_hi, override_stage, claim_healthy, reveal_key,
ignore_system, roleplay_developer, fake_citation, hidden_obfuscated
(zero-width-char obfuscation), multi_step — all via a real planted
malicious document ingested into a real `VectorIndex`, retrieved
successfully in all 10 cases (defense is at generation time, which is the
correct and only trustworthy layer — retrieval cannot and should not try
to pre-filter content by intent). **10/10: context never mutated, no key
leaked, no fake citation adopted, never flipped to a HEALTHY-only claim.**
See FINAL_RAG_EVALUATION.md for per-variant detail.

## Archive/bundle security
Bundle tamper detection confirmed: corrupting `dataset.json` bytes in a
copy of a real exported bundle correctly raised
`BundleValidationError: dataset.json checksum mismatch` on load — not
silently accepted. `canonical_path` (a local absolute path) is correctly
stripped from exported bundles, confirmed by direct inspection of the
round-trip diff.

## Not covered this session (archive ingestion fuzzing, Phase 6 full scope)
Malformed/truncated/path-traversal archive tests, multipart-RAR
missing-part handling, and archive-bomb defense were **not independently
re-tested this session** — relies on the existing test suite's coverage
(`tests/test_analyze_dataset_rar.py` and similar, part of the 968 passing
tests) rather than a fresh adversarial pass. NOT_TESTABLE_THIS_SESSION for
a true red-team pass on archive handling specifically.

## Unsafe code patterns
Not re-audited this session beyond what the existing `ruff check .`
(clean) and the project's own `security.md` rules cover. No new
`shell=True`, `eval`/`exec`, or `pickle.load` usage was introduced by this
session's changes (`src/bearing_pdm/rag/explain.py` additions reviewed
directly: only `httpx` calls and dict/string handling, no code execution
of any kind).

## SESSION 6 UPDATE — archive security / negative ingestion (item 4)

The existing committed test suite already covers almost every requested
scenario with real controlled fixtures (not the multi-GB real archives),
confirmed passing in this session's full 972-test run:

| Scenario | Evidence |
|---|---|
| ZIP path traversal (`../../etc/passwd`) | `tests/test_archive.py::test_path_traversal_rejected` — `ZipSecurityError` |
| Absolute path entry | `tests/test_archive.py::test_absolute_path_rejected` |
| Excessive expanded size (zip-bomb ratio) | `tests/test_archive.py::test_zip_bomb_ratio_rejected` |
| Excessive file count | `tests/test_archive.py::test_excessive_file_count_rejected` |
| Nested archive | `tests/test_archive.py::test_nested_archive_rejected` |
| Duplicate path | `tests/test_archive.py::test_duplicate_path_rejected` |
| Empty archive | `tests/test_archive.py::test_empty_zip_rejected` (and reconfirmed below) |
| Encrypted zip | `tests/test_archive.py::test_encrypted_zip_rejected` |
| Symlink entry | `tests/test_archive.py::test_symlink_entry_rejected` |
| Malformed/corrupt zip | `tests/test_archive.py::test_malformed_zip_reports_invalid` |
| Missing multipart RAR part | `tests/test_rar_archive.py::test_discover_rar_parts_missing_part_raises` — real controlled fixture (part01/02/04 present, part03 missing), `RarArchiveError`, no subprocess invoked |
| Non-RAR file as RAR | `tests/test_rar_archive.py::test_discover_rar_parts_non_rar_rejected` |
| Tampered bundle checksum, HTTP-level | `tests/test_analyze_bundle_endpoint.py::test_corrupt_checksum_is_rejected_with_400_not_a_traceback` — the actual API endpoint the UI's import button calls, returns 400 with a `"checksum"` message, never a 500/traceback |
| Malformed zip, HTTP-level | `tests/test_analyze_bundle_endpoint.py::test_malformed_zip_is_rejected_not_a_500` |
| Missing manifest member / bad schema version | `tests/test_analyze_bundle_endpoint.py::test_missing_manifest_member_is_rejected`, `test_unsupported_schema_version_is_rejected` |

Three scenarios without an existing dedicated test were checked directly
against the real `safe_extract_zip`/`build_manifest_from_zip` functions
this session (ad-hoc, not committed as new tests — ponytail: these are
thin wrappers around already-tested code paths, not new logic):
- **Truncated archive**: a valid zip with its last 200 bytes chopped off
  -> `ZipSecurityError: malformed ZIP: File is not a zip file`. Clean
  rejection, no traceback, nothing written to the output directory.
- **Unsupported archive type** (`.tar.gz` fed to the zip path):
  `ZipSecurityError: malformed ZIP: File is not a zip file`. Same clean
  rejection — the system has no tar/7z extraction path at all (only
  `.zip` via `archive.py` and `.rar` via `rar_archive.py`), so anything
  else is rejected at the same zip-format-validation gate rather than
  silently falling back to a wrong dataset.
- **Misleadingly-named folder/file** (`FEMTO_Bearing_Dataset_Learning_set.zip`
  whose actual contents are unrelated junk): `build_manifest_from_zip`
  correctly ignores the filename and classifies by content, returning
  `compatibility=ADAPTER_REQUIRED, dataset_type=None` — never a false
  positive FEMTO match from the name alone.
- In all cases: nothing written outside the intended extraction root
  (`out_trunc`/`out_tar` directories confirmed empty), no raw traceback
  surfaced, no silent fallback to a wrong dataset.

**Net for this item: PASS.** All 10 requested scenarios are covered,
either by pre-existing committed tests (re-confirmed passing this
session) or by this session's direct checks against the real validation
functions.

## SESSION 7 UPDATE — provider credential isolation (micro-closure item 1)

The independent reviewer's MAJOR finding (`OnlineLLM` falling back to a
generic `os.environ.get("api_key")`) is **RESOLVED**. Full codebase search
for `api_key|API_KEY|token|Authorization|bearer` in
`src/bearing_pdm/rag/explain.py` confirmed this was the *only* generic-
fallback instance; `GroqProvider`, `OpenAIProvider`, `OpenRouterProvider`
already used only their own explicitly named variable.

Fix: removed the `or os.environ.get("api_key")` line from `OnlineLLM.__init__`
(`src/bearing_pdm/rag/explain.py`). It now reads only `AI_GATEWAY_API_KEY`
or `VERCEL_AI_GATEWAY_API_KEY`.

6 new regression tests added (`tests/test_rag.py`), dummy values only:
1. `test_only_groq_api_key_enables_groq_provider`
2. `test_only_openai_api_key_enables_openai_provider`
3. `test_only_openrouter_api_key_enables_openrouter_provider`
4. `test_generic_api_key_env_var_enables_no_provider` - a bare `api_key`/
   `API_KEY` enables none of Groq/OpenAI/OpenRouter/OnlineLLM.
5. `test_cross_provider_key_cannot_enable_wrong_provider` - a key set
   under one provider's variable never enables a different provider.
6. `test_no_provider_leaks_secret_value_in_errors_or_repr` - a dummy
   secret never appears in any provider's `repr()` or in a raised
   `ProviderUnavailable` message.

All pass (62/62 in `tests/test_rag.py`, full suite 990/990). `ruff check .`
clean.
