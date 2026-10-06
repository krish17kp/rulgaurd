"use client";

import { useEffect, useState } from "react";
import { analyzeFemtoSignal, ApiError, FemtoSignalResponse } from "@/lib/api";
import { SignalChart } from "@/components/SignalChart";

type State =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: FemtoSignalResponse };

const FEATURE_ORDER = [
  "mean",
  "abs_mean",
  "rms",
  "std",
  "var",
  "min",
  "max",
  "peak_to_peak",
  "crest_factor",
  "shape_factor",
  "impulse_factor",
  "clearance_factor",
  "kurtosis",
  "skewness",
  "dominant_frequency_hz",
  "spectral_centroid_hz",
  "spectral_entropy",
  "frequency_rms_hz",
  "total_spectral_energy",
];

function featureRows(features: Record<string, number>, axis: "vibration_x" | "vibration_y") {
  const prefix = `${axis}_`;
  return FEATURE_ORDER.filter((name) => `${prefix}${name}` in features).map((name) => ({
    name,
    value: features[`${prefix}${name}`],
  }));
}

/** Tabs: SIGNAL & FFT / FEATURES, backed by the real uploaded samples from
 * /analyze/femto-signal (src/bearing_pdm/api.py). Fetched once per file -
 * the backend remains the only place features/FFT are computed. */
export function SignalAndFeatures({ file }: { file: File }) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [tab, setTab] = useState<"signal" | "features">("signal");

  useEffect(() => {
    let cancelled = false;
    analyzeFemtoSignal(file)
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data });
      })
      .catch((err) => {
        if (!cancelled) setState({ status: "error", error: (err as ApiError).detail ?? "Could not load signal data." });
      });
    return () => {
      cancelled = true;
    };
  }, [file]);

  if (state.status === "loading") {
    return <p className="text-sm text-foreground-muted">Loading signal and feature view…</p>;
  }
  if (state.status === "error") {
    return <p className="text-sm text-danger">{state.error}</p>;
  }

  const { data } = state;

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-surface-border bg-surface p-4">
      <div className="flex gap-2 border-b border-surface-border pb-2 text-xs font-medium">
        <button
          type="button"
          onClick={() => setTab("signal")}
          className={`rounded px-2 py-1 ${tab === "signal" ? "bg-accent text-white" : "text-foreground-muted"}`}
        >
          Signal &amp; FFT
        </button>
        <button
          type="button"
          onClick={() => setTab("features")}
          className={`rounded px-2 py-1 ${tab === "features" ? "bg-accent text-white" : "text-foreground-muted"}`}
        >
          Features
        </button>
      </div>

      {tab === "signal" && (
        <div className="flex flex-col gap-4">
          <p className="text-xs text-foreground-muted">
            {data.samples} samples at {data.sample_rate_hz.toLocaleString()} Hz (the raw uploaded acquisition — not
            reconstructed).
          </p>
          <div>
            <p className="mb-1 text-xs font-medium text-foreground-muted">Vibration X waveform</p>
            <SignalChart values={data.vibration_x.waveform} xLabel="sample" yLabel="amplitude" />
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-foreground-muted">Vibration Y waveform</p>
            <SignalChart values={data.vibration_y.waveform} xLabel="sample" yLabel="amplitude" color="#f472b6" />
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-foreground-muted">Vibration X FFT magnitude</p>
            <SignalChart
              values={data.vibration_x.fft_magnitude}
              xValues={data.vibration_x.fft_frequency_hz}
              xLabel="Hz"
              yLabel="magnitude"
            />
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-foreground-muted">Vibration Y FFT magnitude</p>
            <SignalChart
              values={data.vibration_y.fft_magnitude}
              xValues={data.vibration_y.fft_frequency_hz}
              xLabel="Hz"
              yLabel="magnitude"
              color="#f472b6"
            />
          </div>
        </div>
      )}

      {tab === "features" && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {(["vibration_x", "vibration_y"] as const).map((axis) => (
            <table key={axis} className="w-full text-left text-xs">
              <caption className="mb-1 text-left font-medium text-foreground-muted">{axis}</caption>
              <tbody>
                {featureRows(data.features, axis).map((row) => (
                  <tr key={row.name} className="border-t border-surface-border">
                    <td className="py-1 pr-3 font-mono">{row.name}</td>
                    <td className="py-1 text-right tabular-nums">
                      {Number.isFinite(row.value) ? row.value.toPrecision(5) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
        </div>
      )}
    </div>
  );
}
