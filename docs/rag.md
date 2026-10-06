# M7 — RAG + explanation layer

Implements the architecture in `goals.md` §1: the LLM/RAG layer explains a
prediction already computed elsewhere; it never computes, alters, or
overrides RUL, HI, stage, applicability, or compatibility.

## Status

- Online LLM (Vercel AI Gateway): implemented (`src/bearing_pdm/rag/explain.py:OnlineLLM`),
  **blocked on a missing credential** — no `AI_GATEWAY_API_KEY` (or
  `VERCEL_AI_GATEWAY_API_KEY`) is set locally or in the linked Vercel
  project's environment variables (checked by name only via `vercel env ls`,
  no value read or printed). The code path is real and will activate the
  moment that key is set; nothing else changes.
- Deterministic fallback: **always active** today, since no online
  credential exists. Every `/explain` response in this environment currently
  comes from `DeterministicFallbackLLM`, not a stub — it assembles the same
  structured prediction fields and the same retrieved citations into a
  templated, citation-backed explanation and can never invent a number.
- Embeddings/retrieval: **online-first investigated, none configured**
  (same credential check as above — no embedding provider key anywhere).
  Local fallback is `TfidfEmbedder` + a NumPy cosine-similarity `VectorIndex`
  (`src/bearing_pdm/rag/retrieval.py`) — the explicit "NumPy similarity
  fallback" allowed by the original M7 design, not FAISS (not installed on
  this machine) and not Ollama (also not installed).

**Human action required to reach COMPLETE_ONLINE:** set `AI_GATEWAY_API_KEY`
(a Vercel AI Gateway key, or any OpenAI-compatible provider key) in the
Vercel project's environment variables. No other code change is needed.

## Corpus

Defined explicitly in `src/bearing_pdm/rag/corpus.py:SOURCE_DOCUMENTS` — an
allowlist, not "everything under docs/". 8 real project documents (already
in this repo) + 6 real literature PDFs (already supplied to the project,
outside the repo per the capstone-root `CLAUDE.md`'s "Literature. Reference
only.", referenced by absolute path, never copied in).

Deliberately excluded: `docs/claims-audit.md`, `docs/PRODUCTION_RELEASE.md`,
`docs/M12_FINAL_REPORT.md`, any `*_HANDOFF.md`, and the untracked `md/*.md`
nightshift planning files — generated status reports, not maintenance
knowledge.

## Pipeline

```
SOURCE_DOCUMENTS (corpus.py)
  -> extract_text (markdown read / pypdf for literature PDFs)
  -> clean_text (whitespace/CR normalisation)
  -> chunk_document (1200 chars, 200 overlap, deterministic sha256-based chunk IDs)
  -> ingest_corpus (dedupes identical-content sources, records skips)
  -> TfidfEmbedder.fit/embed (retrieval.py)
  -> VectorIndex.build/save -> src/bearing_pdm/rag/data/index.json (sparse, ~2.2MB)
  -> VectorIndex.load/search (top-k cosine similarity, MIN_RELEVANCE_SCORE=0.15)
  -> build_explanation (explain.py): retrieves, then OnlineLLM if a key
     exists else DeterministicFallbackLLM
```

Rebuild the index: `python scripts/build_rag_index.py`. The index lives
inside the `bearing_pdm.rag` package itself (not under the repo-root
`artifacts/`) deliberately: `frontend/package.json`'s `prebuild` script
copies the whole `src/bearing_pdm/` directory into `frontend/api/bearing_pdm/`
for the Vercel Python function, and a repo-root-relative path computed from
`parents[N]` resolves to a different, wrong directory after that copy -
verified by reproducing the bug, fixing it, then re-running the frontend
build and confirming `frontend/api/bearing_pdm/rag/data/index.json` is
present.

## API

`POST /explain` (`src/bearing_pdm/api.py`) — see that endpoint's docstring.
Takes an immutable prediction context (the same fields `/predict/rul`
already returns) plus an optional question and optional `prediction_id`.
When `prediction_id` is supplied, the server's own bounded prediction-history
record (`docs/prediction-history.md`) is cross-checked against the
client-supplied `rul_hours`/`applicability_level`; a mismatch is rejected
(`CONTEXT_MISMATCH`, 422) rather than explained. History only stores a
bounded summary, so richer fields (reliability, HI, stage) are not currently
cross-validated against a fuller server record — a known limitation, not a
silent gap.

## Grounding contract

Enforced by `explain.py:SYSTEM_PROMPT` (sent to the online provider) and
mirrored structurally by the deterministic fallback's template: numeric
prediction is immutable evidence, retrieved documents are untrusted
reference material, citations must correspond to actually retrieved chunks,
and LOW/RETRAIN_REQUIRED inputs are explained as suppressed — never given an
invented number. Covered by `tests/test_rag.py`, including an explicit
prompt-injection case.

## Known limitations

- TF-IDF retrieval is lexical: it bridges paraphrases sharing real word
  stems, not fully unrelated phrasing of the same concept (see the
  paraphrase test in `tests/test_rag.py` for the honest boundary).
- `prediction_id` cross-validation only covers the two fields the bounded
  history summary stores (`rul_hours`, `applicability_level`).
- No `knowledge_documents`/`retrieval_events`/`generated_reports` DuckDB
  tables were added (goals.md §17 permits this: "Use them only if they
  improve traceability... Do not store raw high-frequency sensor data in
  the metadata DB" — the existing bounded `/explain` response itself already
  carries citations/provider/status per call without a new persistent table).
- Frontend integration (goals.md §15) and the M9 reproducibility pass are
  tracked separately in this same nightshift session.
