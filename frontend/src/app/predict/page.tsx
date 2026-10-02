"use client";

import { useState } from "react";
import { ApiError, PredictRulResponse, predictRul } from "@/lib/api";
import { ApplicabilityNote } from "@/components/ApplicabilityNote";

type SubmitState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: PredictRulResponse };

export default function PredictPage() {
  const [featuresJson, setFeaturesJson] = useState("{}");
  const [result, setResult] = useState<SubmitState>({ status: "idle" });

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    let features: Record<string, number>;
    try {
      features = JSON.parse(featuresJson);
    } catch {
      setResult({ status: "error", error: "Features must be valid JSON: {\"col\": 1.23, ...}" });
      return;
    }
    setResult({ status: "loading" });
    try {
      const data = await predictRul({ dataset_id: "femto", features });
      setResult({ status: "ready", data });
    } catch (err) {
      setResult({ status: "error", error: (err as ApiError).detail });
    }
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-16">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Predict RUL</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Paste an already-extracted FEMTO feature row (column name → value). This does not
          accept raw sensor CSVs yet — dataset upload, adapter detection, and feature
          extraction over HTTP are a separate, not-yet-implemented goal (see the
          repository&apos;s <code>goals.md</code>). Missing columns fall back to the
          model&apos;s training median and are disclosed below, not hidden.
        </p>
      </header>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <textarea
          className="h-48 rounded-lg border border-zinc-300 p-3 font-mono text-xs dark:border-zinc-700 dark:bg-zinc-900"
          value={featuresJson}
          onChange={(e) => setFeaturesJson(e.target.value)}
          spellCheck={false}
        />
        <button
          type="submit"
          className="self-start rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          disabled={result.status === "loading"}
        >
          {result.status === "loading" ? "Predicting…" : "Predict"}
        </button>
      </form>

      {result.status === "error" && (
        <p className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {result.error}
        </p>
      )}

      {result.status === "ready" && (
        <div className="rounded-lg border border-zinc-200 p-5 dark:border-zinc-800">
          <p className="text-3xl font-semibold">
            {result.data.rul_hours.toFixed(1)} <span className="text-base font-normal text-zinc-500">hours</span>
          </p>
          <p className="text-sm text-zinc-500">
            ({result.data.rul_seconds.toFixed(0)} seconds) — model: {result.data.model_name}
          </p>
          {result.data.features_missing.length > 0 && (
            <p className="mt-3 text-sm text-amber-700 dark:text-amber-400">
              {result.data.features_missing.length} of {result.data.features_used.length} features
              were not provided and were filled with the training median:{" "}
              <span className="font-mono text-xs">{result.data.features_missing.join(", ")}</span>
            </p>
          )}
          <ApplicabilityNote result={result.data} />
        </div>
      )}
    </main>
  );
}
