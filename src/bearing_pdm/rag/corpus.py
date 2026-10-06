"""Deterministic ingestion: real project documents + literature -> clean,
deterministically-chunked text with retained source metadata.

Corpus membership (goals.md #2) is an explicit allowlist, not "everything
under docs/". Generated status reports, session handoffs, release logs, and
agent prompts are deliberately excluded.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
# Literature PDFs live outside both git repos (capstone-root CLAUDE.md:
# "*.pdf, *.docx (root) | Literature. Reference only."); referenced by
# absolute path, never copied/committed into the repo.
LITERATURE_ROOT = REPO_ROOT.parent


@dataclass(frozen=True)
class SourceDocument:
    doc_id: str
    title: str
    path: Path
    kind: str  # "project_doc" | "literature"
    author: str | None = None
    year: int | None = None


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    source: str
    kind: str
    position: int
    text: str
    checksum: str
    author: str | None = None
    year: int | None = None
    page: int | None = None


# Real project documents already in the repository, defining the actual
# architecture/data contract/decisions this system was built to. Explicitly
# excludes docs/claims-audit.md, docs/PRODUCTION_RELEASE.md,
# docs/M12_FINAL_REPORT.md, docs/*_HANDOFF.md, and the untracked md/*.md
# nightshift planning files - those are generated status reports, not
# maintenance/technical knowledge.
SOURCE_DOCUMENTS: list[SourceDocument] = [
    SourceDocument("doc_architecture", "RULGuard Architecture",
                   REPO_ROOT / "docs" / "architecture.md", "project_doc"),
    SourceDocument("doc_data_contract", "Canonical Feature-Row Data Contract",
                   REPO_ROOT / "docs" / "data-contract.md", "project_doc"),
    SourceDocument("doc_decisions", "Decisions and Conflict Resolutions",
                   REPO_ROOT / "docs" / "decisions.md", "project_doc"),
    SourceDocument("doc_dataset_audit", "Dataset Audit",
                   REPO_ROOT / "docs" / "dataset-audit.md", "project_doc"),
    SourceDocument("doc_milestone", "Milestones (M0-M9)",
                   REPO_ROOT / "docs" / "milestone.md", "project_doc"),
    SourceDocument("doc_prd", "Product Requirements - bearing_pdm",
                   REPO_ROOT / "docs" / "prd.md", "project_doc"),
    SourceDocument("doc_dataset_compatibility", "Dataset Compatibility",
                   REPO_ROOT / "docs" / "dataset-compatibility.md", "project_doc"),
    SourceDocument("doc_prediction_reliability", "Prediction Reliability",
                   REPO_ROOT / "docs" / "prediction-reliability.md", "project_doc"),
    # Literature already supplied to the project, outside the repo per
    # capstone-root CLAUDE.md's "Literature. Reference only." - indexed by
    # absolute path, not copied in. Filenames verified against `ls` of the
    # capstone root (command.md's §2A input list named different filenames
    # than what is actually present on disk - this list uses the real ones).
    SourceDocument("lit_realtime_pdm",
                   "A Real-Time Predictive Maintenance System for Machinery",
                   LITERATURE_ROOT / "A_real-time_predictive_maintenance_system_for_mach.pdf",
                   "literature"),
    SourceDocument("lit_cloud_ml_pdm",
                   "Cloud-Based Machine Learning Methods for Parameter Prediction",
                   LITERATURE_ROOT / "Cloud-Based_Machine_Learning_Methods_for_Parameter.pdf",
                   "literature"),
    SourceDocument("lit_ml_approach_pdm",
                   "Machine Learning Approach for Predictive Maintenance",
                   LITERATURE_ROOT / "Machine_Learning_Approach_for_Predictive_Maintenan.pdf",
                   "literature"),
    SourceDocument("lit_ml_long_cycle_pdm",
                   "Machine Learning for Long-Cycle Maintenance Prediction",
                   LITERATURE_ROOT / "Machine_Learning_for_Long_Cycle_Maintenance_Predic.pdf",
                   "literature"),
    SourceDocument("lit_maintenance_strategies_multistage",
                   "Maintenance Strategies for Industrial Multi-Stage Systems",
                   LITERATURE_ROOT / "Maintenance_Strategies_for_Industrial_Multi-Stage_.pdf",
                   "literature"),
    SourceDocument("lit_sustainability_14_03387",
                   "Sustainability 14, 3387",
                   LITERATURE_ROOT / "sustainability-14-03387.pdf",
                   "literature", year=2022),
]

_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 200


def clean_text(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\x00", "")
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def _extract_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is required to ingest literature PDFs; install via "
            "requirements-rag.txt"
        ) from exc
    reader = PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def extract_text(doc: SourceDocument) -> str:
    """Raises FileNotFoundError / RuntimeError on unreadable sources - callers
    must handle unsupported/missing files cleanly (goals.md #3), not silently
    skip them."""
    if not doc.path.exists():
        raise FileNotFoundError(f"{doc.doc_id}: source file not found at {doc.path}")
    if doc.path.suffix.lower() == ".pdf":
        return _extract_pdf(doc.path)
    if doc.path.suffix.lower() in (".md", ".txt"):
        return _extract_markdown(doc.path)
    raise ValueError(f"{doc.doc_id}: unsupported file type {doc.path.suffix}")


def _chunk_positions(length: int) -> list[tuple[int, int]]:
    if length == 0:
        return []
    step = CHUNK_CHARS - CHUNK_OVERLAP
    spans = []
    start = 0
    while start < length:
        end = min(start + CHUNK_CHARS, length)
        spans.append((start, end))
        if end == length:
            break
        start += step
    return spans


def chunk_document(doc: SourceDocument) -> list[Chunk]:
    text = clean_text(extract_text(doc))
    if not text:
        raise ValueError(f"{doc.doc_id}: document is empty after cleaning, rejected")
    chunks: list[Chunk] = []
    for position, (start, end) in enumerate(_chunk_positions(len(text))):
        body = text[start:end].strip()
        if not body:
            continue
        checksum = hashlib.sha256(body.encode("utf-8")).hexdigest()
        chunk_id = f"{doc.doc_id}:{position:04d}:{checksum[:12]}"
        chunks.append(Chunk(
            chunk_id=chunk_id, doc_id=doc.doc_id, doc_title=doc.title,
            source=str(doc.path), kind=doc.kind, position=position, text=body,
            checksum=f"sha256:{checksum}", author=doc.author, year=doc.year,
        ))
    return chunks


@dataclass
class IngestResult:
    chunks: list[Chunk] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (doc_id, reason)


def ingest_corpus(documents: list[SourceDocument] | None = None) -> IngestResult:
    result = IngestResult()
    seen_checksums: set[str] = set()
    for doc in documents if documents is not None else SOURCE_DOCUMENTS:
        try:
            doc_chunks = chunk_document(doc)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            result.skipped.append((doc.doc_id, str(exc)))
            continue
        doc_checksum = hashlib.sha256(
            "".join(c.checksum for c in doc_chunks).encode()
        ).hexdigest()
        if doc_checksum in seen_checksums:
            result.skipped.append((doc.doc_id, "duplicate-source (identical chunk set)"))
            continue
        seen_checksums.add(doc_checksum)
        result.chunks.extend(doc_chunks)
    return result
