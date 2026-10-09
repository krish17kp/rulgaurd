"use client";

import { useState } from "react";
import { analyzeFemtoBearingZip, ApiError, BearingZipAnalysisResponse } from "@/lib/api";
import { BearingZipResult } from "@/components/BearingZipResult";

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "bundle_required"; message: string }
  | { status: "ready"; data: BearingZipAnalysisResponse };

/** Analyze > Bearing ZIP: upload a whole FEMTO bearing's acc_ and temp_ CSVs
 * as one ZIP and run the same pipeline as a single-acquisition upload over
 * every acquisition in the archive - nothing recomputed differently. */
export default function AnalyzeBearingZipPage() {
  const [state, setState] = useState<State>({ status: "idle" });

  async function onFile(file: File) {
    setState({ status: "loading" });
    try {
      const data = await analyzeFemtoBearingZip(file);
      if (data.status === "analysis_bundle_required") {
        setState({
          status: "bundle_required",
          message: data.message ?? "This bearing ZIP is too large to analyze directly.",
        });
        return;
      }
      setState({ status: "ready", data });
    } catch (err) {
      setState({ status: "error", error: (err as ApiError).detail ?? String(err) });
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-16">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Analyze a bearing ZIP</h1>
        <p className="mt-1 text-sm text-foreground-muted">
          Upload one FEMTO bearing folder (e.g. acc_00001.csv &hellip; acc_00911.csv, zipped) to see its
          full signal, feature, Health Indicator, stage, and RUL evidence — the same pipeline as a
          single-acquisition upload, run over every acquisition in the archive.
        </p>
      </header>

      <input
        type="file"
        accept=".zip"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void onFile(file);
        }}
        className="text-sm"
      />

      {state.status === "loading" && <p className="text-sm text-foreground-muted">Analyzing…</p>}
      {state.status === "error" && (
        <p className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {state.error}
        </p>
      )}
      {state.status === "bundle_required" && (
        <p className="rounded-lg border border-caution/40 bg-caution/10 p-4 text-sm text-caution">
          {state.message} A RULGuard Analysis Bundle (offline-generated compact export) is the
          supported path for archives this large; direct ZIP upload is bounded by Vercel&apos;s
          request-body limits.
        </p>
      )}
      {state.status === "ready" && <BearingZipResult data={state.data} />}
    </main>
  );
}
