#!/usr/bin/env python
"""Ingest a document directory or ZIP and export a `.rulguard-knowledge.zip`
retrieval bundle (M12 Phase U).

Usage:
    python scripts/build_knowledge_bundle.py --dir docs/ --output docs.rulguard-knowledge.zip
    python scripts/build_knowledge_bundle.py --zip corpus.zip --output corpus.rulguard-knowledge.zip
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from bearing_pdm.rag.ingest import discover_sources, ingest_paths, ingest_zip_of_documents
from bearing_pdm.rag.retrieval import VectorIndex


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dir", type=Path, help="directory of PDF/MD/TXT/DOCX files")
    source.add_argument("--zip", type=Path, help="ZIP of PDF/MD/TXT/DOCX files")
    parser.add_argument("--output", type=Path, required=True, help="output .rulguard-knowledge.zip")
    parser.add_argument("--bundle-id", default="knowledge")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="rulguard_knowledge_") as tmp:
        if args.dir:
            result = ingest_paths(discover_sources(args.dir))
        else:
            result = ingest_zip_of_documents(args.zip, Path(tmp))

        for f in result.files:
            print(f"{f.status}: {f.path}" + (f" ({f.reason})" if f.reason else ""))

        if not result.chunks:
            print("no chunks produced - nothing to index", file=sys.stderr)
            return 1

        index = VectorIndex.build_from_chunks(result.chunks)
        out_path = index.save_knowledge_bundle(args.output, bundle_id=args.bundle_id)

    print(f"wrote {out_path} ({len(result.chunks)} chunks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
