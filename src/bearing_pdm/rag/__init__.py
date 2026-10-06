"""M7 RAG layer: ingestion, embeddings, retrieval, grounded explanation.

Provider-independent by design (goals.md #4, #6): every stage behind an
interface so an online embedding/LLM provider can be swapped in later without
touching retrieval or explanation logic.
"""
