#!/usr/bin/env python
"""M7 evaluation: retrieval quality and grounding of the explanation assistant.

The relevant documents for each question were chosen from the documents' content
before this script was first run. Retrieval: hit@k and MRR over the questions.
Grounding: every answer is checked for numbers absent from the model result and
the cited evidence (`unsupported_numbers`); whichever provider is configured is
used (Groq on the server, the deterministic template without a key).

Usage:
    python scripts/evaluate_rag.py [--out artifacts/evidence/M7/rag_evaluation.json]
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from bearing_pdm.rag.explain import PredictionContext, build_explanation, unsupported_numbers
from bearing_pdm.rag.retrieval import DEFAULT_INDEX_PATH, VectorIndex

TOP_K = 4
LIT = "lit_"
QUESTIONS = [
    ("Why is RUL withheld for my uploaded dataset?",
     {"doc_upload_analysis", "doc_dataset_compatibility", "doc_prediction_reliability"}),
    ("How many run-to-failure bearings are needed before RUL is shown for an upload?",
     {"doc_upload_analysis"}),
    ("What does the health rating reliability trend measure?", {"doc_upload_analysis"}),
    ("What naive baseline must the RUL model beat?",
     {"doc_upload_analysis", "doc_decisions", "doc_cross_dataset"}),
    ("What does applicability LOW mean for a prediction?",
     {"doc_prediction_reliability", "doc_dataset_compatibility", "doc_cross_dataset"}),
    ("Which fields does a canonical feature row contain?", {"doc_data_contract"}),
    ("How was the FEMTO hidden Full_Test_Set scored?",
     {"doc_decisions", "doc_milestone", "doc_dataset_audit"}),
    ("Are degradation stages a fault diagnosis?", {"doc_decisions", "doc_upload_analysis"}),
    ("Why is life fraction used as the cross-domain target?",
     {"doc_decisions", "doc_cross_dataset"}),
    ("Can RULGuard read MATLAB mat or wav recordings?", {"doc_upload_analysis"}),
    ("How does predictive maintenance differ from preventive maintenance?", {LIT}),
    ("Why did the health indicator pin at 1.0 for many learning acquisitions?",
     {"doc_decisions"}),
]
CONTEXTS = {
    "rul_shown": PredictionContext(dataset_id="xjtu", model_name="ExtraTrees (raw_seconds)",
                                   rul_seconds=20160.0, rul_hours=5.6, applicability_level="HIGH",
                                   compatibility="COMPATIBLE", health_indicator=0.4321,
                                   degradation_stage="DEGRADING"),
    "rul_withheld": PredictionContext(dataset_id="generic", applicability_level="LOW",
                                      applicability_reasons=["feature distribution shift 7.36x"],
                                      compatibility="RETRAIN_REQUIRED", health_indicator=0.81,
                                      degradation_stage="HEALTHY"),
}


def _relevant(doc_id: str, expected: set[str]) -> bool:
    return doc_id in expected or (LIT in expected and doc_id.startswith(LIT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("artifacts/evidence/M7/rag_evaluation.json"))
    args = ap.parse_args()
    index = VectorIndex.load(DEFAULT_INDEX_PATH)

    retrieval = []
    for q, expected in QUESTIONS:
        docs = [c.doc_id for c in index.search(q, top_k=TOP_K)]
        rank = next((i + 1 for i, d in enumerate(docs) if _relevant(d, expected)), None)
        retrieval.append({"question": q, "expected": sorted(expected), "retrieved": docs,
                          "first_relevant_rank": rank})

    answers = []
    for name, ctx in CONTEXTS.items():
        for q, _ in QUESTIONS:
            r = build_explanation(ctx, q, index)
            answers.append({"context": name, "question": q, "provider": r.provider,
                            "fallback_used": r.fallback_used, "status": r.status,
                            "n_citations": len(r.citations),
                            "online_answer_rejected": r.explanation.startswith(
                                "An online answer was discarded"),
                            "unsupported_numbers": unsupported_numbers(
                                r.explanation, ctx, "", q, r.citations)
                            if not r.fallback_used else []})

    n = len(retrieval)
    online = [a for a in answers if not a["fallback_used"] or a["online_answer_rejected"]]
    report = {
        "generated_at": datetime.now(UTC).isoformat(), "index_chunks": len(index.chunks),
        "index_documents": len({c.doc_id for c in index.chunks}), "top_k": TOP_K,
        "retrieval": {"hit_at_k": sum(r["first_relevant_rank"] is not None for r in retrieval) / n,
                      "hit_at_1": sum(r["first_relevant_rank"] == 1 for r in retrieval) / n,
                      "mrr": sum(1 / r["first_relevant_rank"] for r in retrieval
                                 if r["first_relevant_rank"]) / n,
                      "per_question": retrieval},
        "grounding": {"n_answers": len(answers),
                      "providers": sorted({a["provider"] for a in answers}),
                      "n_online_answers": len(online),
                      "n_online_rejected_for_numbers": sum(a["online_answer_rejected"] for a in answers),
                      "n_answers_with_citations": sum(a["n_citations"] > 0 for a in answers),
                      "n_insufficient_evidence": sum(a["status"] == "insufficient_evidence"
                                                     for a in answers),
                      "n_shown_with_unsupported_numbers": sum(bool(a["unsupported_numbers"])
                                                              for a in answers),
                      "per_answer": answers},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    g = report["grounding"]
    print(f"retrieval hit@{TOP_K} {report['retrieval']['hit_at_k']:.2f}, "
          f"hit@1 {report['retrieval']['hit_at_1']:.2f}, MRR {report['retrieval']['mrr']:.2f}; "
          f"{g['n_answers']} answers via {g['providers']}: {g['n_online_rejected_for_numbers']} "
          f"online answers rejected, {g['n_shown_with_unsupported_numbers']} shown with "
          f"unsupported numbers -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
