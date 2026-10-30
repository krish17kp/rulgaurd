"use client";

import { useState } from "react";
import { RoutingBundlePayload } from "@/lib/api";
import { MultiSeriesChart, ChartSeries } from "@/components/MultiSeriesChart";

const MODEL_NAMES: Record<string, string> = {
  raw_seconds: "FEMTO RUL model",
  sn_fraction: "Normalized life-fraction model",
  sn_fraction_multi: "Cross-dataset normalized model",
};

export function modelName(id: string): string {
  return MODEL_NAMES[id] ?? id;
}

const LEVEL_TEXT = {
  HIGH: "looks like its training data",
  MEDIUM: "partly differs from its training data",
  LOW: "differs strongly from its training data",
} as const;

/** Plain-language reason RUL was withheld, most decisive cause first. */
export function withheldReason(decision: RoutingBundlePayload["decisions"][string], notValidated: boolean): string {
  if (notValidated) {
    return "No RULGuard model has shown skill on this dataset in held-out testing, so a life estimate would be a guess.";
  }
  if (!decision.quality_ok && decision.quality_reasons.length) {
    return `The recordings did not pass the quality checks: ${decision.quality_reasons.join("; ")}.`;
  }
  if (Object.values(decision.applicability).every((a) => a.level === "LOW")) {
    return "This bearing's vibration differs too much from the data every model was trained on.";
  }
  return "No model passed both the applicability check and the validated-skill check for this bearing.";
}

/** Any dataset the cross-dataset pipeline routes (XJTU, IMS, a manually
 * mapped generic dataset, or a future adapter) - dataset-agnostic by the
 * same shape bundle_kind() uses server-side, so one renderer covers all of
 * them rather than a per-dataset frontend branch. A routing bundle never
 * ships raw signal/FFT (analysis_bundle.py: derived results only), so this
 * shows the sections that ARE scientifically available: profile, per-
 * bearing applicability/status, and - when the dataset has more than one
 * ordered recording - a trajectory (health indicator, stage, RUL). */
export function RoutingBundleResult({
  data,
  signalNote,
  incompleteBearings = [],
  notValidated = false,
}: {
  data: RoutingBundlePayload;
  signalNote?: string;
  /** Bearings cut short by archive parts that were not uploaded. */
  incompleteBearings?: string[];
  /** The job's validation says no model has skill on this dataset. */
  notValidated?: boolean;
}) {
  const bearingIds = Object.keys(data.decisions).sort();
  const [bearing, setBearing] = useState(bearingIds[0] ?? "");
  const [advanced, setAdvanced] = useState(false);
  const decision = data.decisions[bearing];
  const trajectory = data.trajectories?.[bearing] ?? [];

  if (!decision) {
    return (
      <section className="rounded-xl border border-surface-border bg-surface p-4 text-sm">
        Routing bundle loaded but contains no bearings.
      </section>
    );
  }

  const current = decision.current;
  const rulAvailable = current.status !== "RUL_SUPPRESSED" && trajectory.some(
    (p) => p.predicted_rul_seconds != null
  );

  const hiSeries: ChartSeries[] =
    trajectory.length > 1
      ? [
          {
            label: "health indicator",
            color: "#60a5fa",
            points: trajectory.map((p) => ({ x: p.elapsed_s / 3600, y: p.health_indicator ?? null })),
          },
        ]
      : [];
  const partial = incompleteBearings.includes(bearing);
  // Where the degradation stage changes along the trajectory.
  const stageMarkers: Array<{ x: number; label: string }> = [];
  let lastStage: string | null = null;
  for (const p of trajectory) {
    if (!p.stage) continue;
    if (lastStage && p.stage !== lastStage) stageMarkers.push({ x: p.elapsed_s / 3600, label: p.stage.toLowerCase() });
    lastStage = p.stage;
  }
  const rulSeries: ChartSeries[] =
    trajectory.length > 1 && rulAvailable
      ? [
          {
            label: "predicted RUL (hours)",
            color: "#f97316",
            points: trajectory.map((p) => ({
              x: p.elapsed_s / 3600,
              y: p.predicted_rul_seconds != null ? p.predicted_rul_seconds / 3600 : null,
            })),
          },
          ...(trajectory.some((p) => p.actual_rul_seconds != null)
            ? [
                {
                  label: "actual RUL (hours)",
                  color: "#38bdf8",
                  points: trajectory.map((p) => ({
                    x: p.elapsed_s / 3600,
                    y: p.actual_rul_seconds != null ? p.actual_rul_seconds / 3600 : null,
                  })),
                },
              ]
            : []),
        ]
      : [];

  return (
    <div className="flex flex-col gap-6">
      <label className="flex items-center gap-2 self-end text-xs text-foreground-muted">
        <input type="checkbox" checked={advanced} onChange={(e) => setAdvanced(e.target.checked)} />
        Show advanced details (status codes, model IDs, feature shift, reasons)
      </label>
      <section className="rounded-xl border border-surface-border bg-surface p-4">
        <h2 className="text-sm font-semibold">Overview</h2>
        <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
          <dt className="text-foreground-muted">Dataset</dt>
          <dd className="font-mono">{data.dataset_id}</dd>
          <dt className="text-foreground-muted">Detected as</dt>
          <dd>{data.profile.known_datasets.map((d) => d.dataset_id).join(", ") || "custom / generic (manually mapped)"}</dd>
          <dt className="text-foreground-muted">Files profiled</dt>
          <dd>{data.profile.n_files.toLocaleString()}</dd>
          <dt className="text-foreground-muted">Sampling rate</dt>
          <dd>
            {data.profile.sampling_rate_hz != null
              ? `${data.profile.sampling_rate_hz.toLocaleString()} Hz`
              : "unknown"}
          </dd>
          <dt className="text-foreground-muted">Channels found</dt>
          <dd>{data.profile.channels_found.join(", ") || "none"}</dd>
          <dt className="text-foreground-muted">Bearings</dt>
          <dd>{bearingIds.length}</dd>
        </dl>
        {advanced && (
          <p className="mt-2 text-xs text-foreground-muted">Sampling rate source: {data.profile.sampling_rate_source}</p>
        )}
        {advanced && data.profile.warnings.length > 0 && (
          <ul className="mt-2 list-inside list-disc text-xs text-foreground-muted">
            {data.profile.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-surface-border bg-surface p-4 text-sm text-foreground-muted">
        <h2 className="text-sm font-semibold text-foreground">Signal / FFT</h2>
        <p className="mt-1">
          {signalNote ??
            "Raw signal is not included in this Analysis Bundle — a routing bundle carries only " +
              "derived results (features, health indicator, applicability), never the raw dataset."}
        </p>
      </section>

      {bearingIds.length > 1 ? (
        <label className="text-sm">
          Bearing{" "}
          <select
            value={bearing}
            onChange={(e) => setBearing(e.target.value)}
            className="ml-2 rounded-md border border-surface-border bg-surface px-2 py-1 text-sm"
          >
            {bearingIds.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <p className="text-sm text-foreground-muted">
          Bearing: <span className="font-mono text-foreground">{bearing}</span>
        </p>
      )}

      <section className="rounded-xl border border-surface-border bg-surface p-4">
        <h2 className="text-sm font-semibold">Remaining useful life</h2>
        {!rulAvailable ? (
          <div className="mt-2 text-sm">
            <p className="font-medium">RUL intentionally withheld</p>
            <p className="mt-1 text-foreground-muted">{withheldReason(decision, notValidated)}</p>
            {advanced && (
              <p className="mt-1 text-xs text-foreground-muted">
                Status: <span className="font-mono">{current.status}</span>, scope {current.scope || "n/a"}, validated skill{" "}
                {current.validated_skill != null ? current.validated_skill.toFixed(2) : "n/a"}
                {decision.quality_ok ? ", quality checks passed" : `, quality: ${decision.quality_reasons.join("; ")}`}
              </p>
            )}
          </div>
        ) : (
          <MultiSeriesChart series={rulSeries} xLabel="elapsed time (h)" yLabel="RUL (h)" />
        )}
      </section>

      <section className="rounded-xl border border-surface-border bg-surface p-4">
        <h2 className="text-sm font-semibold">Does each model apply to this bearing?</h2>
        <ul className="mt-2 flex flex-col text-sm">
          {Object.entries(decision.applicability).map(([model, app]) => (
            <li key={model} className="flex flex-wrap items-baseline justify-between gap-2 border-t border-surface-border py-2 first:border-t-0">
              <span>
                <span className="font-medium">{modelName(model)}</span>
                <span className="text-foreground-muted">: {app.level}, the signal {LEVEL_TEXT[app.level]}</span>
              </span>
              {advanced && (
                <span className="text-xs text-foreground-muted">
                  <span className="font-mono">{model}</span>, feature shift {app.shift_ratio.toFixed(2)}x
                </span>
              )}
              {advanced && app.reasons.length > 0 && (
                <ul className="w-full list-inside list-disc text-xs text-foreground-muted">
                  {app.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </section>

      {hiSeries.length > 0 ? (
        <section className="rounded-xl border border-surface-border bg-surface p-4">
          <h2 className="text-sm font-semibold">Health / trajectory{partial ? " (partial trajectory)" : ""}</h2>
          {partial && (
            <p className="mt-1 text-xs text-caution">
              Some of this bearing&apos;s recordings are in archive parts that were not uploaded. Shaded spans have no
              recordings; the line is never drawn across them.
            </p>
          )}
          <MultiSeriesChart
            series={hiSeries}
            xLabel="elapsed time (h)"
            yLabel="HI (1 healthy → 0 failed)"
            markers={stageMarkers}
          />
        </section>
      ) : (
        <section className="rounded-xl border border-surface-border bg-surface p-4 text-sm text-foreground-muted">
          Only one recording is available for this bearing — no trajectory is shown for an
          isolated snapshot.
        </section>
      )}
    </div>
  );
}
