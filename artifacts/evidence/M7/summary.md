# M7 evidence: RAG explanations

Date: 2026-10-30. Run on the deployed API container (forevue.tech) with the real Groq key:
`python scripts/evaluate_rag.py` -> `rag_evaluation.json` (this folder).

- Index: 560 chunks from 16 documents (10 project docs, 6 literature PDFs), TF-IDF, NumPy cosine.
- Retrieval over 12 questions whose relevant documents were fixed from the documents'
  content before the first run: hit@4 0.92, hit@1 0.83, MRR 0.86. The one miss: "Which fields
  does a canonical feature row contain?" retrieves the dataset audit and architecture docs,
  not the data contract.
- Grounding over 24 answers (12 questions x a RUL-shown and a RUL-withheld prediction):
  every answer carries citations; 0 answers shown with a number absent from the prediction,
  the cited evidence or the question. 3 answers came from Groq (`openai/gpt-oss-120b`); 1 of
  them was rejected by the number check and replaced by the template. The other 21 used the
  deterministic template because the provider did not answer during the burst of requests
  (most likely rate limiting); the chain treats that as unavailable, never as a result.
- Design differences from the original M7 plan: Groq instead of local Ollama (no GPU on the
  server), TF-IDF NumPy instead of FAISS (not installed), both documented in docs/rag.md.
