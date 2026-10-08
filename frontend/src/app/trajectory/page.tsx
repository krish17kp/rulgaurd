"use client";

import { useEffect, useState } from "react";
import { ApiError, TrajectoryResponse, getTrajectory, getTrajectoryBearings } from "@/lib/api";
import { MultiSeriesChart } from "@/components/MultiSeriesChart";

type State =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; bearings: string[]; selected: string; data: TrajectoryResponse };

const STAGE_BADGE: Record<string, string> = {
  HEALTHY: "bg-green-500/15 text-green-600 dark:text-green-400",
  DEGRADING: "bg-caution/15 text-caution",
  CRITICAL: "bg-red-500/15 text-red-600 dark:text-red-400",
};

export default function TrajectoryPage() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    (async () => {
      try {
        const { bearings } = await getTrajectoryBearings();
        const selected = bearings.includes("femto:Bearing2_1") ? "femto:Bearing2_1" : bearings[0];
        const data = await getTrajectory(selected);
        setState({ status: "ready", bearings, selected, data });
      } catch (err) {
        setState({ status: "error", error: (err as ApiError).detail ?? String(err) });
      }
    })();
  }, []);

  async function selectBearing(bearing: string) {
    if (state.status !== "ready") return;
    const bearings = state.bearings;
    setState({ status: "loading" });
    try {
      const data = await getTrajectory(bearing);
      setState({ status: "ready", bearings, selected: bearing, data });
    } catch (err) {
      setState({ status: "error", error: (err as ApiError).detail ?? String(err) });
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-16">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Explore bearing trajectory</h1>
        <p className="mt-1 text-sm text-foreground-muted">
          Whole-run Health Indicator and leave-one-bearing-out RUL evidence for the six FEMTO
          learning bearings, read from the same fitted models and held-out evaluation artifacts
          as the project&apos;s Streamlit dashboard — nothing here is fit or retrained on demand.
        </p>
      </header>

      {state.status === "loading" && <p className="text-sm text-foreground-muted">Loading…</p>}
      {state.status === "error" && (
        <p className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {state.error}
        </p>
      )}

      {state.status === "ready" && (
        <>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">Bearing / run</span>
            <select
              className="w-fit rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm"
              value={state.selected}
              onChange={(e) => selectBearing(e.target.value)}
            >
              {state.bearings.map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </select>
          </label>

          <HealthSection data={state.data} />
          <RulSection data={state.data} />
        </>
      )}
    </main>
  );
}

function HealthSection({ data }: { data: TrajectoryResponse }) {
  const currentStage = data.stage.at(-1) ?? "HEALTHY";
  const series = [
    {
      label: "reference_hi (selected)",
      color: "#60a5fa",
      points: data.sequence_index.map((x, i) => ({ x, y: data.reference_hi[i] })),
    },
    ...(data.transparent_hi
      ? [{
          label: "transparent_hi (legacy comparison)",
          color: "#94a3b8",
          points: data.sequence_index.map((x, i) => ({ x, y: data.transparent_hi![i] })),
        }]
      : []),
    ...(data.pca_hi
      ? [{
          label: "pca_hi (legacy comparison)",
          color: "#c084fc",
          points: data.sequence_index.map((x, i) => ({ x, y: data.pca_hi![i] })),
        }]
      : []),
  ];

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-surface-border p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Health &amp; degradation</h2>
        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${STAGE_BADGE[currentStage] ?? ""}`}>
          {currentStage}
        </span>
      </div>
      <MultiSeriesChart series={series} xLabel="acquisition index (life progression)" yLabel="health indicator" />
      <p className="text-xs text-foreground-muted">
        Warn below {data.stage_thresholds.hi_warn.toFixed(3)}, critical below{" "}
        {data.stage_thresholds.hi_critical.toFixed(3)} (fitted on the other five bearings),
        committed after {data.stage_thresholds.persistence} consecutive acquisitions agree. The two
        legacy curves are shown only for comparison — neither is used for staging (see
        docs/decisions.md D18).
      </p>
      <p className="rounded-md bg-surface px-3 py-2 text-xs font-medium text-foreground-muted">
        Degradation stage is a severity band on the health indicator, not a physical fault
        diagnosis.
      </p>
    </section>
  );
}

function RulSection({ data }: { data: TrajectoryResponse }) {
  const actual = {
    label: "actual RUL (hours)",
    color: "#34d399",
    points: data.sequence_index.map((x, i) => ({
      x,
      y: data.actual_rul_seconds[i] !== null ? (data.actual_rul_seconds[i] as number) / 3600 : null,
    })),
  };
  const predictedBySeq = new Map(
    data.held_out_predicted_rul_seconds.sequence_index.map((seq, i) => [
      seq,
      data.held_out_predicted_rul_seconds.predicted_rul_seconds[i],
    ])
  );
  const predicted = {
    label: "predicted RUL — held out, leave-one-bearing-out (hours)",
    color: "#f472b6",
    points: data.sequence_index.map((x) => ({
      x,
      y: predictedBySeq.has(x) ? (predictedBySeq.get(x) as number) / 3600 : null,
    })),
  };

  const mae = data.held_out_metrics.mae_seconds;
  const n = data.held_out_metrics.n;
  const overestimateRate = data.held_out_metrics.overestimate_rate;

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-surface-border p-4">
      <h2 className="text-lg font-semibold">RUL analysis</h2>
      <MultiSeriesChart series={[actual, predicted]} xLabel="acquisition index" yLabel="RUL (hours)" />
      <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-3">
        <div>
          <dt className="text-foreground-muted">Bearing MAE</dt>
          <dd className="font-semibold">{mae !== null ? `${(mae / 3600).toFixed(2)} h` : "—"}</dd>
        </div>
        <div>
          <dt className="text-foreground-muted">Acquisitions</dt>
          <dd className="font-semibold">{n ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-foreground-muted">Over-prediction rate</dt>
          <dd className="font-semibold">
            {overestimateRate !== null ? `${(overestimateRate * 100).toFixed(1)}%` : "—"}
          </dd>
        </div>
      </dl>
      <p className="text-xs text-foreground-muted">
        Predicted values are from the leave-one-bearing-out evaluation: a model fit on the other
        five learning bearings, never on this one. A predicted point above the actual RUL curve is
        an unsafe over-prediction (more remaining life claimed than the bearing actually had); a
        point below is conservative.
      </p>
    </section>
  );
}
