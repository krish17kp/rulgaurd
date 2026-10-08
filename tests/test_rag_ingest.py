"""Phase L: multi-document knowledge ingestion (PDF/MD/TXT/DOCX, dirs, ZIPs)."""

from __future__ import annotations

import zipfile

import pytest

from bearing_pdm.rag.ingest import discover_sources, ingest_paths, ingest_zip_of_documents


def test_markdown_and_txt_are_processed_with_chunks(tmp_path):
    md = tmp_path / "note.md"
    md.write_text("# Title\n\n" + "Bearing degradation content. " * 50)
    txt = tmp_path / "note.txt"
    txt.write_text("Plain knowledge text. " * 50)

    result = ingest_paths([md, txt])
    statuses = {f.path: f.status for f in result.files}
    assert statuses[str(md)] == "processed"
    assert statuses[str(txt)] == "processed"
    assert len(result.chunks) >= 2
    for chunk in result.chunks:
        assert chunk.checksum.startswith("sha256:")
        assert chunk.source in (str(md), str(txt))


def test_corrupt_pdf_is_failed_not_silently_dropped(tmp_path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"not a pdf at all")
    result = ingest_paths([bad])
    assert result.files[0].status == "failed"
    assert result.files[0].reason


def test_unsupported_suffix_is_reported(tmp_path):
    csv = tmp_path / "data.csv"
    csv.write_text("a,b\n1,2\n")
    result = ingest_paths([csv])
    assert result.files[0].status == "unsupported"


def test_unchanged_file_skipped_on_second_pass(tmp_path):
    md = tmp_path / "note.md"
    md.write_text("Stable content. " * 50)
    first = ingest_paths([md])
    assert first.files[0].status == "processed"
    manifest = {f.path: f.checksum for f in first.files if f.checksum}

    second = ingest_paths([md], manifest)
    assert second.files[0].status == "unchanged"
    assert second.chunks == []


def test_changed_file_is_reprocessed(tmp_path):
    md = tmp_path / "note.md"
    md.write_text("Version one. " * 50)
    first = ingest_paths([md])
    manifest = {f.path: f.checksum for f in first.files if f.checksum}

    md.write_text("Version two, materially different content. " * 50)
    second = ingest_paths([md], manifest)
    assert second.files[0].status == "processed"
    assert second.files[0].checksum != manifest[str(md)]


def test_discover_sources_recurses_directory(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.md").write_text("x")
    (tmp_path / "sub" / "b.txt").write_text("y")
    (tmp_path / "ignore.bin").write_bytes(b"\x00")
    found = {p.name for p in discover_sources(tmp_path)}
    assert found == {"a.md", "b.txt"}


def test_zip_of_documents_is_ingested_safely(tmp_path):
    zip_path = tmp_path / "corpus.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("doc1.md", "Knowledge bundle document one. " * 50)
        zf.writestr("doc2.txt", "Knowledge bundle document two. " * 50)

    result = ingest_zip_of_documents(zip_path, tmp_path / "extracted")
    statuses = sorted(f.status for f in result.files)
    assert statuses == ["processed", "processed"]
    assert len(result.chunks) >= 2


def test_docx_text_extraction_via_stdlib_zip(tmp_path):
    """Minimal real DOCX built by hand (no python-docx dependency needed -
    DOCX is just a zip of WordprocessingML XML)."""
    docx_path = tmp_path / "report.docx"
    body_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>"
        + "Real DOCX paragraph text for ingestion testing. " * 20
        + "</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(docx_path, "w") as zf:
        zf.writestr("word/document.xml", body_xml)
        zf.writestr("[Content_Types].xml", "<Types/>")

    result = ingest_paths([docx_path])
    assert result.files[0].status == "processed"
    assert any("Real DOCX paragraph" in c.text for c in result.chunks)


def test_pdf_chunks_carry_page_numbers(tmp_path):
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter

    pdf_path = tmp_path / "doc.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    with pdf_path.open("wb") as f:
        writer.write(f)

    # Blank pages extract no text, so this just proves the multi-page PDF is
    # readable and produces no spurious chunks (rejected as empty), not a
    # crash - a real-text PDF's page numbers are covered by the next test.
    result = ingest_paths([pdf_path])
    assert result.files[0].status == "failed"
    assert "empty" in (result.files[0].reason or "")


def test_pdf_page_numbers_survive_to_retrieval_and_citations(tmp_path):
    """Regression: Chunk.page is computed here but was previously dropped by
    IndexedChunk/RetrievedChunk, so every citation's page was always None
    even for a PDF where the real page number is known. Verifies the fix
    end to end: ingest -> index -> search -> build_explanation."""
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    from bearing_pdm.rag.explain import PredictionContext, build_explanation
    from bearing_pdm.rag.retrieval import VectorIndex

    pdf_path = tmp_path / "two_page.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(100, 700, "Bearing vibration RMS content unique to page one testcase.")
    c.showPage()
    c.drawString(100, 700, "Remaining useful life content unique to page two testcase.")
    c.showPage()
    c.save()

    result = ingest_paths([pdf_path])
    assert result.files[0].status == "processed"
    pages_seen = {c.page for c in result.chunks}
    assert pages_seen == {1, 2}, pages_seen

    index = VectorIndex.build_from_chunks(result.chunks)
    hits = index.search("remaining useful life testcase", top_k=1)
    assert hits and hits[0].page == 2

    ctx = PredictionContext(rul_seconds=1000.0, rul_hours=0.28, applicability_level="HIGH")
    result = build_explanation(ctx, "remaining useful life testcase", index)
    assert result.citations
    assert any(citation.page == 2 for citation in result.citations)
