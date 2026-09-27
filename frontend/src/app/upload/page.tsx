"use client";

import { useState } from "react";
import { ApiError, Compatibility, DatasetProfileResponse, inspectDataset } from "@/lib/api";

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: DatasetProfileResponse };

const BADGE: Record<Compatibility, string> = {
  FULLY_SUPPORTED: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300",
  ADAPTER_REQUIRED: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  UNSUPPORTED: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  INVALID_INPUT: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
};

export default function UploadPage() {
  const [state, setState] = useState<State>({ status: "idle" });

  async function handleFile(file: File) {
    setState({ status: "loading" });
    try {
      const data = await inspectDataset(file);
      setState({ status: "ready", data });
    } catch (err) {
      setState({ status: "error", error: (err as ApiError).detail });
    }
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-16">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Upload a dataset</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Inspects the file&apos;s structure (delimiter, header, column meanings) and reports
          whether it is compatible with the pipeline — it does not run a prediction. A
          column-name-only check: it does not guess sampling rate, units, or sensor meaning
          for a headerless file, and it never sends an incompatible file to a trained model.
        </p>
      </header>

      <input
        type="file"
        accept=".csv,.txt,.tsv,.dat"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
        className="text-sm"
      />

      {state.status === "loading" && <p className="text-sm">Inspecting…</p>}

      {state.status === "error" && (
        <p className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {state.error}
        </p>
      )}

      {state.status === "ready" && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <span className={`rounded-full px-3 py-1 text-xs font-medium ${BADGE[state.data.compatibility]}`}>
              {state.data.compatibility.replace(/_/g, " ")}
            </span>
            <span className="text-sm text-zinc-500">{state.data.profile.file}</span>
          </div>

          {state.data.reasons.length > 0 && (
            <ul className="list-inside list-disc text-sm text-zinc-700 dark:text-zinc-300">
              {state.data.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}

          {state.data.profile.columns && (
            <table className="w-full text-left text-xs">
              <thead className="text-zinc-500">
                <tr>
                  <th className="py-1 pr-3">Column</th>
                  <th className="py-1 pr-3">Mapped to</th>
                  <th className="py-1 pr-3">Confidence</th>
                  <th className="py-1 pr-3">Missing %</th>
                </tr>
              </thead>
              <tbody>
                {state.data.profile.columns.map((c) => (
                  <tr key={c.name} className="border-t border-zinc-200 dark:border-zinc-800">
                    <td className="py-1 pr-3 font-mono">{c.name}</td>
                    <td className="py-1 pr-3">{c.canonical ?? "—"}</td>
                    <td className="py-1 pr-3">{c.confidence}</td>
                    <td className="py-1 pr-3">{(c.nan_fraction * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {state.data.profile.warnings.length > 0 && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
              {state.data.profile.warnings.map((w) => (
                <p key={w}>{w}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </main>
  );
}
