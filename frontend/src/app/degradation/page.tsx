"use client";

import Link from "next/link";
import { useState } from "react";
import { ApiError, HiResponse, HiRow, predictHi } from "@/lib/api";

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: HiResponse };

const STAGE_COLOR: Record<HiRow["stage"], string> = {
  HEALTHY: "bg-green-500",
  DEGRADING: "bg-caution",
  CRITICAL: "bg-red-500",
};

export default function DegradationPage() {
  const [rowsJson, setRowsJson] = useState("[]");
  const [state, setState] = useState<State>({ status: "idle" });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    let rows;
    try {
      rows = JSON.parse(rowsJson);
    } catch {
      setState({ status: "error", error: "Rows must be valid JSON: a list of feature-row objects." });
      return;
    }
    setState({ status: "loading" });
    try {
      const data = await predictHi({ dataset_id: "femto", rows });
      setState({ status: "ready", data });
    } catch (err) {
      setState({ status: "error", error: (err as ApiError).detail });
    }
  }

  const maxHi = state.status === "ready" ? Math.max(...state.data.rows.map((r) => r.health_indicator)) : 1;

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-16">
      <div className="rounded-lg border border-caution/30 bg-caution/10 p-3 text-xs text-caution">
        <p className="font-semibold">Advanced Tool — Health Indicator / Degradation Trend</p>
        <p className="mt-1">
          This interface expects ordered, pre-extracted feature rows for one bearing run — there
          is no raw multi-file degradation analysis here, only this manual feature-row input. For
          a single file&apos;s RUL estimate, use{" "}
          <Link href="/upload" className="underline">
            Analyze
          </Link>
          .
        </p>
      </div>
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Advanced: degradation / health indicator trend</h1>
        <p className="mt-1 text-sm text-foreground-muted">
          Paste an ordered list of feature rows for one bearing run (each needs{" "}
          <code>sequence_index</code> plus the HI model&apos;s feature columns — see{" "}
          <code>GET /models/info</code>). The health indicator and stage are a severity
          band on the signal, never a physical fault-type diagnosis.
        </p>
      </header>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <textarea
          className="h-40 rounded-lg border border-surface-border bg-surface p-3 font-mono text-xs"
          value={rowsJson}
          onChange={(e) => setRowsJson(e.target.value)}
          spellCheck={false}
        />
        <button
          type="submit"
          className="self-start rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-background disabled:opacity-50"
          disabled={state.status === "loading"}
        >
          {state.status === "loading" ? "Computing…" : "Compute HI trend"}
        </button>
      </form>

      {state.status === "error" && (
        <p className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {state.error}
        </p>
      )}

      {state.status === "ready" && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-foreground-muted">
            {state.data.note} Warn threshold: {state.data.hi_warn_threshold.toFixed(3)}, critical:{" "}
            {state.data.hi_critical_threshold.toFixed(3)}.
          </p>
          <div className="flex h-32 items-end gap-px overflow-x-auto rounded-lg border border-surface-border p-2  ">
            {state.data.rows.map((r) => (
              <div
                key={r.sequence_index}
                title={`seq ${r.sequence_index}: HI=${r.health_indicator.toFixed(3)} (${r.stage})`}
                className={`w-1.5 shrink-0 ${STAGE_COLOR[r.stage]}`}
                style={{ height: `${Math.max(4, (r.health_indicator / maxHi) * 100)}%` }}
              />
            ))}
          </div>
          <p className="text-xs text-foreground-muted">
            Latest: sequence_index {state.data.rows.at(-1)?.sequence_index}, HI{" "}
            {state.data.rows.at(-1)?.health_indicator.toFixed(3)}, stage{" "}
            {state.data.rows.at(-1)?.stage}.
          </p>
        </div>
      )}
    </main>
  );
}
