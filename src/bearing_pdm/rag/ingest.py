"""General-purpose knowledge ingestion: arbitrary PDF/Markdown/TXT/DOCX files,
directories, or ZIPs of the above -> deterministic chunks with full citation
metadata, incremental by checksum.

Distinct from corpus.py's SOURCE_DOCUMENTS allowlist (the project's own curated
corpus, unchanged by this module). This module is for user-supplied knowledge
(Phase L): one PDF, many PDFs, a folder, or a ZIP, via Knowledge Bundle (M).
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from bearing_pdm.archive import LOCAL_FULL_MODE, safe_extract_zip
from bearing_pdm.rag.corpus import Chunk, _chunk_positions, clean_text

INGEST_VERSION = 1
SUPPORTED_SUFFIXES = {".pdf", ".md", ".txt", ".docx"}
_DOCX_BODY_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _extract_pdf_pages(path: Path) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return [page.extract_text() or "" for page in reader.pages]


def _extract_docx(path: Path) -> str:
    """Stdlib-only DOCX text extraction (docx is a zip of XML) - no new
    dependency needed for plain paragraph text."""
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    return "\n".join(node.text or "" for node in root.iter(_DOCX_BODY_NS))


@dataclass(frozen=True)
class KnowledgeSource:
    doc_id: str
    title: str
    path: Path
    author: str | None = None
    year: int | None = None


def _extract_pages(source: KnowledgeSource) -> list[str]:
    """Raises on unreadable/corrupt files; ValueError on unsupported suffix.
    Callers map these to failed/unsupported status, never silently drop."""
    suffix = source.path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_pages(source.path)
    if suffix in (".md", ".txt"):
        return [source.path.read_text(encoding="utf-8", errors="strict")]
    if suffix == ".docx":
        return [_extract_docx(source.path)]
    raise ValueError(f"unsupported file type: {suffix}")


def discover_sources(root: Path) -> list[Path]:
    """A single file, a directory (recursive), or nothing - ZIPs are handled
    separately by ingest_zip since they need extraction first."""
    if root.is_file():
        return [root] if root.suffix.lower() in SUPPORTED_SUFFIXES else []
    return sorted(p for p in root.rglob("*") if p.suffix.lower() in SUPPORTED_SUFFIXES)


@dataclass
class FileIngestResult:
    path: str
    status: str  # "processed" | "unchanged" | "failed" | "unsupported"
    doc_id: str | None = None
    checksum: str | None = None
    chunk_count: int = 0
    reason: str | None = None


@dataclass
class KnowledgeIngestResult:
    files: list[FileIngestResult] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)


def _doc_id_for(path: Path) -> str:
    return "kb_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]


def _chunk_source(source: KnowledgeSource, checksum: str) -> list[Chunk]:
    pages = _extract_pages(source)
    chunks: list[Chunk] = []
    position = 0
    for page_num, page_text in enumerate(pages, start=1):
        text = clean_text(page_text)
        if not text:
            continue
        has_pages = len(pages) > 1 or source.path.suffix.lower() == ".pdf"
        for start, end in _chunk_positions(len(text)):
            body = text[start:end].strip()
            if not body:
                continue
            body_checksum = hashlib.sha256(body.encode("utf-8")).hexdigest()
            chunk_id = f"{source.doc_id}:{position:04d}:{body_checksum[:12]}"
            chunks.append(Chunk(
                chunk_id=chunk_id, doc_id=source.doc_id, doc_title=source.title,
                source=str(source.path), kind="knowledge", position=position,
                text=body, checksum=f"sha256:{body_checksum}",
                author=source.author, year=source.year,
                page=page_num if has_pages else None,
            ))
            position += 1
    if not chunks:
        raise ValueError("document is empty after cleaning, rejected")
    return chunks


def ingest_paths(
    paths: list[Path],
    manifest: dict[str, str] | None = None,
) -> KnowledgeIngestResult:
    """Incremental ingestion keyed by file-path -> sha256 in `manifest` (the
    caller's previously-saved state); a file whose checksum is unchanged is
    reported as 'unchanged' and not re-chunked. Never silently drops a bad
    file - every input path gets an explicit status."""
    manifest = manifest or {}
    result = KnowledgeIngestResult()
    for path in paths:
        key = str(path)
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            result.files.append(FileIngestResult(key, "unsupported", reason=f"suffix {path.suffix!r}"))
            continue
        try:
            checksum = _sha256_file(path)
        except OSError as exc:
            result.files.append(FileIngestResult(key, "failed", reason=str(exc)))
            continue
        if manifest.get(key) == checksum:
            result.files.append(FileIngestResult(key, "unchanged", checksum=checksum))
            continue
        source = KnowledgeSource(doc_id=_doc_id_for(path), title=path.stem, path=path)
        try:
            chunks = _chunk_source(source, checksum)
        except Exception as exc:  # noqa: BLE001 - any parser failure -> failed status, never crash ingestion
            result.files.append(FileIngestResult(key, "failed", reason=str(exc)))
            continue
        result.chunks.extend(chunks)
        result.files.append(FileIngestResult(
            key, "processed", doc_id=source.doc_id, checksum=checksum, chunk_count=len(chunks),
        ))
    return result


def ingest_zip_of_documents(
    zip_path: Path,
    work_dir: Path,
    manifest: dict[str, str] | None = None,
) -> KnowledgeIngestResult:
    """Safely extracts (Phase E's safe_extract_zip - no second unsafe
    extraction path) then ingests every supported file inside."""
    safe_extract_zip(zip_path, work_dir, LOCAL_FULL_MODE)
    paths = discover_sources(work_dir)
    return ingest_paths(paths, manifest)


def load_manifest(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_manifest(path: Path, manifest: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def demo() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        md = tmp_path / "note.md"
        md.write_text("# Bearing wear\n\n" + "Vibration RMS increases as bearings degrade. " * 40)
        txt = tmp_path / "note.txt"
        txt.write_text("Plain text knowledge source for stress testing ingestion. " * 30)
        bad = tmp_path / "broken.pdf"
        bad.write_bytes(b"not a real pdf")

        result = ingest_paths([md, txt, bad, tmp_path / "missing.csv"])
        statuses = {f.path: f.status for f in result.files}
        assert statuses[str(md)] == "processed", statuses
        assert statuses[str(txt)] == "processed", statuses
        assert statuses[str(bad)] == "failed", statuses
        assert statuses[str(tmp_path / "missing.csv")] == "unsupported", statuses
        assert len(result.chunks) >= 2

        manifest = {str(f.path): f.checksum for f in result.files if f.checksum}
        second = ingest_paths([md, txt], manifest)
        assert all(f.status == "unchanged" for f in second.files), second.files
        print("ingest.py demo OK")


if __name__ == "__main__":
    demo()
