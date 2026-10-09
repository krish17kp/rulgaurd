"use client";

import { useState } from "react";
import {
  AnalysisBundleResponse,
  ApiError,
  CollegeBundleEntry,
  analyzeBundle,
} from "@/lib/api";
import { BearingZipResult } from "@/components/BearingZipResult";
import { MultiSeriesChart, ChartSeries } from "@/components/MultiSeriesChart";

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: AnalysisBundleResponse };

/** Analyze > Analysis Bundle (nightshift Phase 5): upload a portable
 * `.rulguard.zip` built offline by scripts/build_analysis_bundle.py and view
 * it - checksum/schema verified server-side, never refit/recomputed here.
 * FEMTO bundles reuse the bearing-ZIP result view; college's whole-run
 * trajectory bundle has its own renderer below (no FEMTO-fit Health
 * Indicator is ever shown for college data - D11). */
export default function AnalyzeBundlePage() {
  const [state, setState] = useState<State>({ status: "idle" });

  async function onFile(file: File) {
    setState({ status: "loading" });
    try {
      const data = await analyzeBundle(file);
      setState({ status: "ready", data });
    } catch (err) {
      setState({ status: "error", error: (err as ApiError).detail ?? String(err) });
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-16">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Load an Analysis Bundle</h1>
        <p className="mt-1 text-sm text-foreground-muted">
          Upload a <code>.rulguard.zip</code> Analysis Bundle — a compact, checksummed export of
          a FEMTO bearing or the college whole-run trajectory produced offline by{" "}
          <code>scripts/build_analysis_bundle.py</code>. Loading a bundle never fits, retrains,
          or recomputes anything; it only displays results already on disk.
        </p>
      </header>

      <input
        type="file"
        accept=".zip"
        data-testid="file-input"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void onFile(file);
        }}
        className="text-sm"
      />

      {state.status === "loading" && <p className="text-sm text-foreground-muted">Loading…</p>}
      {state.status === "error" && (
        <p className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {state.error}
        </p>
      )}
      {state.status === "ready" && <BundleResult data={state.data} />}
    </main>
  );
}

function BundleResult({ data }: { data: AnalysisBundleResponse }) {
  if (data.kind === "femto" && data.payload) {
    const payload = data.payload as Record<string, unknown>;
    return (
      <BearingZipResult
        data={{
          status: "ok",
          message: null,
          bearing_run_id: (payload.bearing_run_id as string) ?? data.dataset_id ?? "unknown",
          acquisition_count: (payload.acquisition_count as number) ?? null,
          sample_rate_hz: (payload.sample_rate_hz as number) ?? null,
          representative_indices: (payload.representative_indices as Record<string, number>) ?? null,
          representative_signals:
            (payload.representative_signals as Record<string, { vibration_x: number[]; vibration_y: number[] }>) ??
            null,
          representative_fft:
            (payload.representative_fft as Record<
              string,
              { vibration_x: { frequency_hz: number[]; magnitude: number[] }; vibration_y: { frequency_hz: number[]; magnitude: number[] } }
            >) ?? null,
          feature_trajectory: (payload.feature_trajectory as Record<string, (number | null)[]>) ?? null,
          sequence_index: (payload.sequence_index as number[]) ?? null,
          reference_hi: (payload.reference_hi as number[] | null) ?? null,
          transparent_hi: (payload.transparent_hi as number[] | null) ?? null,
          pca_hi: (payload.pca_hi as number[] | null) ?? null,
          stage: (payload.stage as string[] | null) ?? null,
          actual_rul_seconds: (payload.actual_rul_seconds as (number | null)[]) ?? null,
          held_out_predicted_rul_seconds: (payload.held_out_predicted_rul_seconds as number[] | null) ?? null,
          held_out_mae_seconds: (payload.held_out_mae_seconds as number | null) ?? null,
          held_out_unavailable_reason: (payload.held_out_unavailable_reason as string | null) ?? null,
          warnings: (payload.warnings as string[]) ?? [],
        }}
      />
    );
  }

  if (data.kind === "college" && data.payload) {
    const entry = Object.values(data.payload as Record<string, CollegeBundleEntry>)[0];
    if (entry) return <CollegeBundleResult data={entry} />;
  }

  return (
    <section className="rounded-xl border border-surface-border bg-surface p-4 text-sm">
      <p className="font-medium">No renderer available for this bundle.</p>
      <p className="mt-1 text-xs text-foreground-muted">
        dataset_id: <span className="font-mono">{data.dataset_id ?? "unknown"}</span> — the bundle
        loaded and passed checksum verification, but its shape does not match a known FEMTO or
        college Analysis Bundle, so nothing is charted here rather than risking a mislabeled chart.
      </p>
    </section>
  );
}

function CollegeBundleResult({ data }: { data: CollegeBundleEntry }) {
  const trendSeries = (name: string, color: string): ChartSeries | null => {
    const values = data.feature_trends[name];
    if (!values) return null;
    return {
      label: name,
      color,
      points: data.sequence_index.map((x, i) => ({ x, y: values[i] ?? null })),
    };
  };

  const amplitudeSeries = [
    trendSeries("vibration_x_rms", "#60a5fa"),
    trendSeries("vibration_x_kurtosis", "#f472b6"),
    trendSeries("vibration_x_crest_factor", "#34d399"),
  ].filter((s): s is ChartSeries => s !== null);

  const tempSeries = [
    trendSeries("bearing_temp_mean", "#f97316"),
    trendSeries("ambient_temp_mean", "#94a3b8"),
    trendSeries("bearing_minus_ambient_temp_mean", "#c084fc"),
  ].filter((s): s is ChartSeries => s !== null);

  const predictedBySeq = new Map(
    data.held_out_predicted_rul_seconds.sequence_index.map((seq, i) => [
      seq,
      data.held_out_predicted_rul_seconds.predicted_rul_seconds[i],
    ])
  );
  const rulSeries: ChartSeries[] = [
    {
      label: "actual RUL (hours)",
      color: "#38bdf8",
      points: data.sequence_index.map((x, i) => ({
        x,
        y: data.actual_rul_seconds[i] != null ? (data.actual_rul_seconds[i] as number) / 3600 : null,
      })),
    },
    {
      label: "predicted RUL — walk-forward (hours)",
      color: "#f97316",
      points: data.sequence_index.map((x) => ({
        x,
        y: predictedBySeq.has(x) ? (predictedBySeq.get(x) as number) / 3600 : null,
      })),
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <section className="rounded-xl border border-surface-border bg-surface p-4">
        <h2 className="text-sm font-semibold">Overview</h2>
        <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
          <dt className="text-foreground-muted">Dataset</dt>
          <dd className="font-mono">{data.dataset_id}</dd>
          <dt className="text-foreground-muted">Acquisitions</dt>
          <dd>{data.n_acquisitions}</dd>
          <dt className="text-foreground-muted">Sample rate</dt>
          <dd>{data.sample_rate_hz.toLocaleString()} Hz</dd>
          <dt className="text-foreground-muted">Temperature coverage</dt>
          <dd>{(data.temp_available_fraction * 100).toFixed(1)}%</dd>
        </dl>
        <p className="mt-2 text-xs text-foreground-muted">{data.coverage_note}</p>
      </section>

      {amplitudeSeries.length > 0 && (
        <section className="rounded-xl border border-surface-border bg-surface p-4">
          <h2 className="text-sm font-semibold">Vibration feature trend</h2>
          <MultiSeriesChart series={amplitudeSeries} xLabel="acquisition index" yLabel="value" />
        </section>
      )}

      {tempSeries.length > 0 && (
        <section className="rounded-xl border border-surface-border bg-surface p-4">
          <h2 className="text-sm font-semibold">Bearing / ambient temperature</h2>
          <MultiSeriesChart series={tempSeries} xLabel="acquisition index" yLabel="°C" />
        </section>
      )}

      <section className="rounded-xl border border-surface-border bg-surface p-4">
        <h2 className="text-sm font-semibold">RUL: actual vs. chronological walk-forward</h2>
        <MultiSeriesChart series={rulSeries} xLabel="acquisition index" yLabel="RUL (hours)" />
        <p className="mt-2 rounded-md bg-caution/10 p-2 text-xs text-caution">{data.naive_caveat}</p>
      </section>

      <section className="rounded-xl border border-surface-border bg-surface p-4 text-xs text-foreground-muted">
        <h2 className="mb-1 text-sm font-semibold text-foreground">Applicability / domain shift</h2>
        <p>{data.domain_shift_note}</p>
      </section>
    </div>
  );
}
