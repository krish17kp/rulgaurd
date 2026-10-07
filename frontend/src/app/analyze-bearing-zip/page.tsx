"use client";

import { useState } from "react";
import { analyzeFemtoBearingZip, ApiError, BearingZipAnalysisResponse } from "@/lib/api";
import { SignalChart } from "@/components/SignalChart";
import { MultiSeriesChart, ChartSeries } from "@/components/MultiSeriesChart";

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "bundle_required"; message: string }
  | { status: "ready"; data: BearingZipAnalysisResponse };

const HI_COLORS: Record<string, string> = {
  reference_hi: "#38bdf8",
  transparent_hi: "#a3a3a3",
  pca_hi: "#f472b6",
};

/** Analyze > Bearing ZIP (nightshift Phase G): upload a whole FEMTO bearing's
 * acc_* / temp_* files as one ZIP and run the exact same scientific pipeline
 * the single-acquisition and /trajectory pages use - nothing here is
 * recomputed with different formulas or retrained. */
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
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-16">
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

function BearingZipResult({ data }: { data: BearingZipAnalysisResponse }) {
  const hiSeries: ChartSeries[] = [];
  if (data.sequence_index && data.reference_hi) {
    hiSeries.push({
      label: "Reference HI",
      color: HI_COLORS.reference_hi,
      points: data.sequence_index.map((x, i) => ({ x, y: data.reference_hi![i] })),
    });
  }
  if (data.sequence_index && data.transparent_hi) {
    hiSeries.push({
      label: "Transparent HI (legacy)",
      color: HI_COLORS.transparent_hi,
      points: data.sequence_index.map((x, i) => ({ x, y: data.transparent_hi![i] })),
    });
  }
  if (data.sequence_index && data.pca_hi) {
    hiSeries.push({
      label: "PCA HI (legacy)",
      color: HI_COLORS.pca_hi,
      points: data.sequence_index.map((x, i) => ({ x, y: data.pca_hi![i] })),
    });
  }

  const rulSeries: ChartSeries[] = [];
  if (data.sequence_index && data.actual_rul_seconds) {
    rulSeries.push({
      label: "Actual RUL (hours)",
      color: "#38bdf8",
      points: data.sequence_index.map((x, i) => ({
        x,
        y: data.actual_rul_seconds![i] != null ? data.actual_rul_seconds![i]! / 3600 : null,
      })),
    });
  }
  if (data.sequence_index && data.held_out_predicted_rul_seconds) {
    rulSeries.push({
      label: "Held-out predicted RUL (hours)",
      color: "#f97316",
      points: data.sequence_index.map((x, i) => ({
        x,
        y: data.held_out_predicted_rul_seconds![i] / 3600,
      })),
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="rounded-xl border border-surface-border bg-surface p-4">
        <h2 className="text-sm font-semibold">Overview</h2>
        <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
          <dt className="text-foreground-muted">Bearing</dt>
          <dd className="font-mono">{data.bearing_run_id}</dd>
          <dt className="text-foreground-muted">Acquisitions</dt>
          <dd>{data.acquisition_count}</dd>
          <dt className="text-foreground-muted">Sample rate</dt>
          <dd>{data.sample_rate_hz?.toLocaleString()} Hz</dd>
        </dl>
        {data.warnings.length > 0 && (
          <ul className="mt-2 list-disc pl-5 text-xs text-caution">
            {data.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
      </section>

      {data.representative_signals && (
        <section className="rounded-xl border border-surface-border bg-surface p-4">
          <h2 className="text-sm font-semibold">Representative signal (early / middle / late)</h2>
          <div className="mt-2 grid gap-4">
            {(["early", "middle", "late"] as const).map((pos) =>
              data.representative_signals![pos] ? (
                <div key={pos}>
                  <p className="mb-1 text-xs font-medium text-foreground-muted capitalize">
                    {pos} — vibration X
                  </p>
                  <SignalChart values={data.representative_signals![pos].vibration_x} xLabel="sample" yLabel="amplitude" />
                </div>
              ) : null
            )}
          </div>
        </section>
      )}

      {data.representative_fft && (
        <section className="rounded-xl border border-surface-border bg-surface p-4">
          <h2 className="text-sm font-semibold">Representative FFT (early / middle / late)</h2>
          <div className="mt-2 grid gap-4">
            {(["early", "middle", "late"] as const).map((pos) =>
              data.representative_fft![pos] ? (
                <div key={pos}>
                  <p className="mb-1 text-xs font-medium text-foreground-muted capitalize">
                    {pos} — vibration X FFT
                  </p>
                  <SignalChart
                    values={data.representative_fft![pos].vibration_x.magnitude}
                    xValues={data.representative_fft![pos].vibration_x.frequency_hz}
                    xLabel="Hz"
                    yLabel="magnitude"
                  />
                </div>
              ) : null
            )}
          </div>
        </section>
      )}

      {hiSeries.length > 0 && (
        <section className="rounded-xl border border-surface-border bg-surface p-4">
          <h2 className="text-sm font-semibold">Health Indicator &amp; stage</h2>
          <p className="mt-1 text-xs text-foreground-muted">
            Stage is a degradation severity band on the Health Indicator, not a physical
            fault-type diagnosis.
          </p>
          <MultiSeriesChart series={hiSeries} xLabel="acquisition index" yLabel="HI" />
        </section>
      )}

      {rulSeries.length > 0 ? (
        <section className="rounded-xl border border-surface-border bg-surface p-4">
          <h2 className="text-sm font-semibold">RUL: actual vs. held-out prediction</h2>
          {data.held_out_mae_seconds != null && (
            <p className="mt-1 text-xs text-foreground-muted">
              Leave-one-bearing-out MAE: {(data.held_out_mae_seconds / 3600).toFixed(2)} h over{" "}
              {data.acquisition_count} acquisitions. Predictions above the actual line are unsafe
              over-predictions.
            </p>
          )}
          <MultiSeriesChart series={rulSeries} xLabel="acquisition index" yLabel="RUL (hours)" />
        </section>
      ) : (
        data.held_out_unavailable_reason && (
          <p className="text-xs text-foreground-muted">{data.held_out_unavailable_reason}</p>
        )
      )}
    </div>
  );
}
