"""Phase N: bounded cloud knowledge ingestion (/knowledge/ingest-zip,
/knowledge/load). Real small zip-of-documents through the real endpoints."""

from __future__ import annotations

import zipfile
from io import BytesIO

from fastapi.testclient import TestClient

from bearing_pdm import api

client = TestClient(api.app)


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_ingest_zip_reports_per_file_status_and_builds_chunks():
    payload = _zip_bytes({
        "note.txt": b"The ExtraTrees model is the selected primary FEMTO RUL estimator.",
        "readme.md": b"# Notes\n\nHealth indicator stages are severity bands, not fault diagnoses.",
    })
    resp = client.post(
        "/knowledge/ingest-zip",
        files={"file": ("docs.zip", payload, "application/zip")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    statuses = {f["path"].split("/")[-1]: f["status"] for f in body["files"]}
    assert statuses["note.txt"] == "processed"
    assert statuses["readme.md"] == "processed"
    assert body["chunk_count"] >= 2


def test_oversized_ingest_zip_returns_knowledge_bundle_required():
    big = _zip_bytes({"big.txt": b"x" * (5 * 1024 * 1024)})
    resp = client.post(
        "/knowledge/ingest-zip",
        files={"file": ("docs.zip", big, "application/zip")},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "knowledge_bundle_required"


def test_knowledge_load_round_trip_becomes_live_explain_index(tmp_path):
    from bearing_pdm.rag.corpus import Chunk
    from bearing_pdm.rag.retrieval import VectorIndex

    original_index = api._rag_index_cache
    chunks = [
        Chunk(
            chunk_id="c1", doc_id="d1", doc_title="Test Doc", source="test.md",
            kind="markdown", position=0,
            text="Applicability LOW must suppress the numeric RUL prediction.",
            checksum="abc123",
        ),
    ]
    index = VectorIndex.build_from_chunks(chunks)
    bundle_path = tmp_path / "test.rulguard-knowledge.zip"
    index.save_knowledge_bundle(bundle_path)

    try:
        with open(bundle_path, "rb") as fh:
            resp = client.post(
                "/knowledge/load",
                files={"file": ("test.rulguard-knowledge.zip", fh.read(), "application/zip")},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["chunk_count"] == 1

        live = api._rag_index()
        results = live.search("applicability suppress")
        assert results and results[0].chunk_id == "c1"
    finally:
        # This endpoint swaps the module-global live RAG index - restore it so
        # other tests in the same process don't see this tiny test index.
        api._rag_index_cache = original_index
