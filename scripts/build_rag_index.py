#!/usr/bin/env python
"""Build the M7 RAG vector index from the real project/literature corpus and
persist it to artifacts/rag_index/index.json (goals.md #5: "persistent/
reloadable index... no full re-embedding on each question").

Usage:
    python scripts/build_rag_index.py
"""

from __future__ import annotations

import sys

from bearing_pdm.rag.corpus import ingest_corpus
from bearing_pdm.rag.retrieval import DEFAULT_INDEX_PATH, VectorIndex


def main() -> int:
    result = ingest_corpus()
    for doc_id, reason in result.skipped:
        print(f"SKIPPED {doc_id}: {reason}", file=sys.stderr)
    if not result.chunks:
        print("No chunks ingested - aborting.", file=sys.stderr)
        return 1
    # A source missing here (the literature PDFs live outside the repo) keeps the
    # chunks the existing index already holds for it, instead of silently vanishing.
    chunks = list(result.chunks)
    missing = {doc_id for doc_id, _ in result.skipped}
    if missing and DEFAULT_INDEX_PATH.exists():
        kept = [c for c in VectorIndex.load(DEFAULT_INDEX_PATH).chunks if c.doc_id in missing]
        print(f"Kept {len(kept)} existing chunks for {len(missing)} unavailable source(s)",
              file=sys.stderr)
        chunks += kept
    index = VectorIndex.build_from_chunks(chunks)
    index.save(DEFAULT_INDEX_PATH)
    print(f"Indexed {len(index.chunks)} chunks from "
          f"{len({c.doc_id for c in index.chunks})} documents -> {DEFAULT_INDEX_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
