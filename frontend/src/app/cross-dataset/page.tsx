"use client";

import { useEffect, useState } from "react";
import { ApiError, CrossDatasetResponse, DatasetMetricSummary, getCrossDatasetComparison } from "@/lib/api";

type State =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: CrossDatasetResponse };

export default function CrossDatasetPage() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    (async () => {
      try {
        const data = await getCrossDatasetComparison();
        setState({ status: "ready", data });
      } catch (err) {
        setState({ status: "error", error: (err as ApiError).detail ?? String(err) });
      }
    })();
  }, []);

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-8 px-6 py-16">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Cross-dataset comparison</h1>
        <p className="mt-1 text-sm text-foreground-muted">
          Real numbers read verbatim from <code>/evaluation/cross-dataset</code>, which assembles
          from the same committed artifacts as the Reliability page. Nothing here is recomputed
          in the browser.
        </p>
      </header>

      {state.status === "loading" && <p className="text-sm">Loading…</p>}
      {state.status === "error" && (
        <p className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {state.error}
        </p>
      )}

      {state.status === "ready" && (
        <>
          <section className="rounded-lg border border-caution/30 bg-caution/10 p-4 text-xs text-caution">
            {state.data.comparability_warning}
          </section>

          <section>
            <h2 className="text-lg font-semibold">In-domain trained results</h2>
            <DatasetCard summary={state.data.in_domain_trained_results.femto} />
          </section>

          <section>
            <h2 className="text-lg font-semibold">
              Not a zero-shot comparison (single-dataset, own split)
            </h2>
            <DatasetCard summary={state.data.not_zero_shot_single_dataset_results.college} />
          </section>

          <section>
            <h2 className="text-lg font-semibold">Not yet available</h2>
            <div className="mt-2 grid gap-3 sm:grid-cols-2">
              <PendingCard label="IMS" reason={state.data.not_yet_available.ims.reason} />
              <PendingCard label="XJTU-SY" reason={state.data.not_yet_available.xjtu_sy.reason} />
            </div>
          </section>
        </>
      )}
    </main>
  );
}

function DatasetCard({ summary }: { summary: DatasetMetricSummary }) {
  const improvementPct =
    ((summary.naive_mae_seconds - summary.extra_trees_mae_seconds) / summary.naive_mae_seconds) * 100;
  return (
    <div className="mt-2 rounded-lg border border-surface-border p-4">
      <h3 className="font-medium">{summary.dataset}</h3>
      <dl className="mt-2 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <Stat label="Sampling rate" value={`${summary.sampling_rate_hz.toLocaleString()} Hz`} />
        <Stat label="Bearings" value={String(summary.bearings)} />
        <Stat label="Channels" value={summary.channels.join(", ")} />
        <Stat label="Evaluation" value={summary.evaluation_method} />
        <Stat label="ExtraTrees MAE" value={`${(summary.extra_trees_mae_seconds / 3600).toFixed(2)} h`} />
        <Stat label="Naive MAE" value={`${(summary.naive_mae_seconds / 3600).toFixed(2)} h`} />
        <Stat
          label={summary.naive_caveat ? "Improvement vs naive (see caveat)" : "Improvement vs naive"}
          value={`${improvementPct.toFixed(1)}%`}
        />
        <Stat label="n" value={String(summary.n)} />
      </dl>
      {summary.naive_caveat && (
        <p className="mt-2 text-xs font-medium text-caution">{summary.naive_caveat}</p>
      )}
      {summary.health_indicator_selected && (
        <p className="mt-2 text-xs text-foreground-muted">
          Health indicator: {summary.health_indicator_selected}
        </p>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-foreground-muted">{label}</dt>
      <dd className="font-semibold">{value}</dd>
    </div>
  );
}

function PendingCard({ label, reason }: { label: string; reason: string }) {
  return (
    <div className="rounded-lg border border-dashed border-surface-border p-4 text-xs text-foreground-muted">
      <p className="font-medium text-foreground">{label} — not yet available</p>
      <p className="mt-1">{reason}</p>
    </div>
  );
}
