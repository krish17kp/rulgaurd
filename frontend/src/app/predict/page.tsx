"use client";

import Link from "next/link";
import { useState } from "react";
import { ApiError, PredictRulResponse, predictRul } from "@/lib/api";
import { ApplicabilityNote } from "@/components/ApplicabilityNote";
import { SuppressedResultNotice, isSuppressedApplicability } from "@/components/SuppressedResultNotice";

type SubmitState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; error: string; suppressed: boolean }
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
      setResult({
        status: "error",
        error: "Features must be valid JSON: {\"col\": 1.23, ...}",
        suppressed: false,
      });
      return;
    }
    setResult({ status: "loading" });
    try {
      const data = await predictRul({ dataset_id: "femto", features });
      setResult({ status: "ready", data });
    } catch (err) {
      const apiErr = err as ApiError;
      setResult({ status: "error", error: apiErr.detail, suppressed: isSuppressedApplicability(apiErr) });
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-16">
      <div className="rounded-lg border border-caution/30 bg-caution/10 p-3 text-xs text-caution">
        <p className="font-semibold">Advanced Tool — Direct Model Input</p>
        <p className="mt-1">
          For researchers/developers who already have extracted FEMTO feature values, not raw
          sensor files.{" "}
          <Link href="/upload" className="underline">
            Analyze a raw bearing file instead
          </Link>
          .
        </p>
      </div>
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Predict</h1>
        <p className="mt-1 text-base text-foreground-muted">
          Paste an already-extracted FEMTO feature row (column name → value).
        </p>
      </header>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <textarea
          aria-label="FEMTO feature row as JSON"
          className="h-48 rounded-lg border border-surface-border bg-surface p-3 font-mono text-xs"
          value={featuresJson}
          onChange={(e) => setFeaturesJson(e.target.value)}
          spellCheck={false}
        />
        <button
          type="submit"
          className="self-start rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-background disabled:opacity-50"
          disabled={result.status === "loading"}
        >
          {result.status === "loading" ? "Predicting…" : "Predict"}
        </button>
      </form>

      {result.status === "error" && result.suppressed && <SuppressedResultNotice detail={result.error} />}

      {result.status === "error" && !result.suppressed && (
        <p className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {result.error}
        </p>
      )}

      {result.status === "ready" && (
        <div className="rounded-lg border border-surface-border p-5  ">
          <p className="text-3xl font-semibold">
            {result.data.rul_hours.toFixed(1)} <span className="text-base font-normal text-foreground-muted">hours</span>
          </p>
          <p className="text-sm text-foreground-muted">
            ({result.data.rul_seconds.toFixed(0)} seconds) — model: {result.data.model_name}
          </p>
          {result.data.features_missing.length > 0 && (
            <p className="mt-3 text-sm text-caution">
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
