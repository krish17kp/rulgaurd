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
    index = VectorIndex.build()
    index.save(DEFAULT_INDEX_PATH)
    print(f"Indexed {len(index.chunks)} chunks from "
          f"{len({c.doc_id for c in index.chunks})} documents -> {DEFAULT_INDEX_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
