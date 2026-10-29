"use client";

import { useState } from "react";
import { RoutingBundlePayload } from "@/lib/api";
import { MultiSeriesChart, ChartSeries } from "@/components/MultiSeriesChart";

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
}: {
  data: RoutingBundlePayload;
  signalNote?: string;
}) {
  const bearingIds = Object.keys(data.decisions).sort();
  const [bearing, setBearing] = useState(bearingIds[0] ?? "");
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
        {data.profile.warnings.length > 0 && (
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
        <h2 className="text-sm font-semibold">Applicability</h2>
        <dl className="mt-2 grid grid-cols-3 gap-2 text-sm">
          {Object.entries(decision.applicability).map(([model, app]) => (
            <div key={model} className="col-span-3 grid grid-cols-3 gap-2 border-t border-surface-border py-1 first:border-t-0">
              <dt className="font-mono text-xs text-foreground-muted">{model}</dt>
              <dd>{app.level}</dd>
              <dd className="text-xs text-foreground-muted">shift {app.shift_ratio.toFixed(2)}x</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="rounded-xl border border-surface-border bg-surface p-4">
        <h2 className="text-sm font-semibold">Remaining useful life</h2>
        {!rulAvailable ? (
          <p className="mt-2 text-sm text-foreground-muted">
            RUL unavailable for this analysis ({current.status}). The applicability or validated-
            skill gate above did not permit a prediction for this bearing — see Applicability.
          </p>
        ) : (
          <MultiSeriesChart series={rulSeries} xLabel="elapsed time (h)" yLabel="RUL (h)" />
        )}
      </section>

      {hiSeries.length > 0 ? (
        <section className="rounded-xl border border-surface-border bg-surface p-4">
          <h2 className="text-sm font-semibold">Health / trajectory</h2>
          <MultiSeriesChart series={hiSeries} xLabel="elapsed time (h)" yLabel="HI (1 healthy → 0 failed)" />
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
