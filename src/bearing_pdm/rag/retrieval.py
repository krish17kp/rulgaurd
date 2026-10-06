"""Embeddings + vector index + top-k retrieval, provider-independent.

Online-first per goals.md #4: this module defines an `Embedder` interface.
No online embedding provider is configured in this environment (checked
ANTHROPIC_API_KEY, OPENAI_API_KEY, AI_GATEWAY_API_KEY, VERCEL_AI_GATEWAY_API_KEY,
GROQ_API_KEY, COHERE_API_KEY, GOOGLE_API_KEY - all unset, locally and in the
linked Vercel project's env vars). Ollama is also not installed on this
machine (capstone-root CLAUDE.md). Per goals.md #5's explicit allowance,
`TfidfEmbedder` is the NumPy-only local fallback: deterministic, zero
external dependency, "matching the original M7 design" language for the
case where FAISS/a heavier embedder cannot run. Swapping in a real online
embedder later only requires implementing `Embedder` - nothing else in this
module changes.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import numpy as np

from bearing_pdm.rag.corpus import ingest_corpus

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Removing function words is what actually separates a genuine topical match
# from a nonsense query sharing one common word (verified empirically: without
# this filter, an out-of-corpus query scored within noise of a real question).
_STOPWORDS = frozenset(
    "a an the is are was were be been being this that these those of to in on "
    "for with as by at from into over under and or not no if then than so "
    "it its it's they them their he she his her we our you your i my do does "
    "did done have has had can could should would will shall may might must "
    "about above after again against all am any because before below between "
    "both but down during each few further here how more most other out own "
    "same such too up very what when where which while who whom why".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2]


class Embedder(Protocol):
    name: str

    def fit(self, texts: list[str]) -> None: ...
    def embed(self, texts: list[str]) -> np.ndarray: ...


class TfidfEmbedder:
    """Deterministic, dependency-free local embedder. Not a learned semantic
    embedding - a real term-frequency/inverse-document-frequency vector space,
    which is a legitimate (if weaker) retrieval signal, not a placeholder that
    fakes similarity. Clearly labelled as such everywhere it's reported."""

    name = "tfidf-local-v1"

    def __init__(self) -> None:
        self.vocabulary: list[str] = []
        self.idf: np.ndarray = np.zeros(0)

    def fit(self, texts: list[str]) -> None:
        doc_freq: Counter[str] = Counter()
        n_docs = len(texts)
        for text in texts:
            doc_freq.update(set(tokenize(text)))
        self.vocabulary = sorted(doc_freq)
        index = {term: i for i, term in enumerate(self.vocabulary)}
        self._index = index
        self.idf = np.array([
            math.log((1 + n_docs) / (1 + doc_freq[term])) + 1.0
            for term in self.vocabulary
        ])

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), len(self.vocabulary)))
        for row, text in enumerate(texts):
            counts = Counter(tokenize(text))
            if not counts:
                continue
            total = sum(counts.values())
            for term, count in counts.items():
                col = self._index.get(term)
                if col is not None:
                    vectors[row, col] = (count / total) * self.idf[col]
            norm = np.linalg.norm(vectors[row])
            if norm > 0:
                vectors[row] /= norm
        return vectors


@dataclass
class IndexedChunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    source: str
    kind: str
    text: str
    checksum: str
    # Sparse (vocab_index, weight) pairs, not a dense ~8000-wide float list:
    # a dense index.json was 22MB (520 chunks x 8111-term vocabulary), far
    # too large to commit or bundle into a Vercel function. Each chunk's
    # real term count is in the low hundreds, so sparse storage is a size
    # reduction with zero loss of precision, not an approximation.
    vector: list[tuple[int, float]]


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    source: str
    kind: str
    text: str
    checksum: str
    score: float


# Package-relative, not repo-root-relative: the frontend build's prebuild
# step copies the whole src/bearing_pdm/ directory into
# frontend/api/bearing_pdm/ for the Vercel Python function (see
# frontend/package.json's "prebuild" script). A path computed from
# Path(__file__).resolve().parents[N] would silently resolve to the wrong
# directory after that copy (parents[3] from here means something different
# under frontend/api/bearing_pdm/rag/ than under src/bearing_pdm/rag/) - a
# path inside this same package travels correctly either way.
DEFAULT_INDEX_PATH = Path(__file__).resolve().parent / "data" / "index.json"


class VectorIndex:
    """NumPy cosine-similarity index - the explicit local fallback mechanism
    named in goals.md #5 ("NumPy similarity fallback is acceptable"). Not
    FAISS: FAISS is not installed in this environment (capstone-root
    CLAUDE.md lists it under "Not installed"), and installing a new
    compiled dependency for a read-only retrieval index that NumPy can do in
    a few lines is scope creep, not a scientific necessity."""

    def __init__(self, embedder: Embedder, chunks: list[IndexedChunk]):
        self.embedder = embedder
        self.chunks = chunks
        vocab_size = len(getattr(embedder, "vocabulary", []))
        self._matrix = np.zeros((len(chunks), vocab_size))
        for row, c in enumerate(chunks):
            for col, weight in c.vector:
                self._matrix[row, col] = weight

    @staticmethod
    def _sparsify(dense: np.ndarray) -> list[tuple[int, float]]:
        nonzero = np.nonzero(dense)[0]
        return [(int(i), float(dense[i])) for i in nonzero]

    @classmethod
    def build(cls, embedder: Embedder | None = None) -> "VectorIndex":
        embedder = embedder or TfidfEmbedder()
        result = ingest_corpus()
        if not result.chunks:
            raise ValueError("Ingestion produced zero chunks - nothing to index")
        texts = [c.text for c in result.chunks]
        embedder.fit(texts)
        vectors = embedder.embed(texts)
        indexed = [
            IndexedChunk(c.chunk_id, c.doc_id, c.doc_title, c.source, c.kind,
                         c.text, c.checksum, cls._sparsify(vectors[i]))
            for i, c in enumerate(result.chunks)
        ]
        return cls(embedder, indexed)

    def save(self, path: Path = DEFAULT_INDEX_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "built_at": datetime.now(UTC).isoformat(),
            "embedder": self.embedder.name,
            "vocabulary": getattr(self.embedder, "vocabulary", []),
            "idf": getattr(self.embedder, "idf", np.zeros(0)).tolist(),
            "chunks": [asdict(c) for c in self.chunks],
        }
        path.write_text(json.dumps(payload, separators=(",", ":")))

    @classmethod
    def load(cls, path: Path = DEFAULT_INDEX_PATH) -> "VectorIndex":
        payload = json.loads(path.read_text())
        embedder = TfidfEmbedder()
        embedder.vocabulary = payload["vocabulary"]
        embedder._index = {term: i for i, term in enumerate(embedder.vocabulary)}
        embedder.idf = np.array(payload["idf"])
        chunks = [
            IndexedChunk(**{**c, "vector": [tuple(pair) for pair in c["vector"]]})
            for c in payload["chunks"]
        ]
        index = cls(embedder, chunks)
        index.built_at = payload["built_at"]
        return index

    def search(self, query: str, top_k: int = 4) -> list[RetrievedChunk]:
        if not query.strip() or not self.chunks:
            return []
        query_vec = self.embedder.embed([query])[0]
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []
        scores = self._matrix @ query_vec
        order = np.argsort(-scores)[:top_k]
        results = []
        for i in order:
            score = float(scores[i])
            if score <= 0:
                continue
            c = self.chunks[i]
            results.append(RetrievedChunk(
                c.chunk_id, c.doc_id, c.doc_title, c.source, c.kind, c.text,
                c.checksum, score,
            ))
        return results
