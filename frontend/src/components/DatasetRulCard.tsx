"use client";

import { useState } from "react";
import { DatasetRul } from "@/lib/api";
import { MultiSeriesChart } from "@/components/MultiSeriesChart";

const h = (s: number) => `${(s / 3600).toFixed(s < 36000 ? 2 : 1)} h`;

const WITHHELD: Record<string, string> = {
  no_failure_data:
    "RUL withheld: no bearing in this dataset is marked as having run until it failed, so there is no true remaining life to learn from or check against.",
  too_few_bearings:
    "RUL withheld: fewer than {min} bearings ran until failure. One bearing is held out for testing while the model learns from the others, so at least {min} are needed for a meaningful test.",
  not_better_than_naive:
    "RUL withheld: tested on this dataset, the model was not more accurate than simply guessing the average bearing life. Showing its numbers would suggest an accuracy it does not have.",
};

/** RUL learned and tested on the uploaded dataset's own run-to-failure bearings. */
export function DatasetRulCard({ rul }: { rul: DatasetRul }) {
  const bearings = Object.keys(rul.trajectories ?? {}).sort();
  const [bearing, setBearing] = useState(bearings[0]);
  const traj = rul.trajectories?.[bearing] ?? [];
  const line = (label: string, color: string, key: "predicted_rul_seconds" | "actual_rul_seconds" | "naive_rul_seconds") => ({
    label,
    color,
    points: traj.map((p) => ({ x: p.elapsed_s / 3600, y: p[key] != null ? p[key]! / 3600 : null })),
  });

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-surface-border bg-surface p-5 text-sm">
      <div>
        <h2 className="text-base font-semibold">Remaining life (RUL), learned from this dataset</h2>
        <p className="mt-1 text-foreground-muted">
          {rul.n_bearings} bearing(s) ran until failure. Each one was predicted by a model trained only on the others,
          so every number below is a test on a bearing the model had never seen.
        </p>
      </div>
      {rul.status !== "validated" ? (
        <p className="text-caution">{WITHHELD[rul.status].replaceAll("{min}", String(rul.min_bearings))}</p>
      ) : (
        <p>RUL shown: on bearings it had never seen, the model beat the average-life guess.</p>
      )}
      {rul.mae_seconds != null && (
        <dl className="grid gap-2 sm:grid-cols-4">
          <div>
            <dt className="text-foreground-muted">Average error</dt>
            <dd className="tabular-nums">{h(rul.mae_seconds)}</dd>
          </div>
          <div>
            <dt className="text-foreground-muted">Average-life guess error</dt>
            <dd className="tabular-nums">{h(rul.naive_mae_seconds!)}</dd>
          </div>
          <div>
            <dt className="text-foreground-muted">Better than guess by</dt>
            <dd className="tabular-nums">{Math.round((rul.skill_vs_naive ?? 0) * 100)}%</dd>
          </div>
          <div>
            <dt className="text-foreground-muted">True life inside the 90% range</dt>
            <dd className="tabular-nums">{Math.round(rul.interval_coverage! * 100)}% of the time</dd>
          </div>
        </dl>
      )}
      {bearings.length > 0 && (
        <>
          <label className="flex items-center gap-2">
            Bearing
            <select
              value={bearing}
              onChange={(e) => setBearing(e.target.value)}
              className="rounded-md border border-surface-border bg-background px-2 py-1 font-mono text-xs"
            >
              {bearings.map((b) => (
                <option key={b}>{b}</option>
              ))}
            </select>
          </label>
          <MultiSeriesChart
            series={[
              line("predicted RUL (hours)", "#f97316", "predicted_rul_seconds"),
              line("actual RUL (hours)", "#38bdf8", "actual_rul_seconds"),
              line("average-life guess (hours)", "#a3a3a3", "naive_rul_seconds"),
            ]}
            xLabel="elapsed time (h)"
            yLabel="RUL (h)"
          />
        </>
      )}
      {rul.per_bearing && (
        <table className="w-full text-left text-xs">
          <thead className="text-foreground-muted">
            <tr>
              <th className="py-1 pr-3">Held-out bearing</th>
              <th className="py-1 pr-3">Life</th>
              <th className="py-1 pr-3">Model error</th>
              <th className="py-1 pr-3">Guess error</th>
            </tr>
          </thead>
          <tbody>
            {rul.per_bearing.map((r) => (
              <tr key={r.bearing} className="border-t border-surface-border">
                <td className="py-1 pr-3 font-mono">{r.bearing}</td>
                <td className="py-1 pr-3 tabular-nums">{h(r.total_life_s)}</td>
                <td className={`py-1 pr-3 tabular-nums ${r.mae_seconds < r.naive_mae_seconds ? "" : "text-caution"}`}>
                  {h(r.mae_seconds)}
                </td>
                <td className="py-1 pr-3 tabular-nums">{h(r.naive_mae_seconds)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {rul.ends_healthy.length > 0 && (
        <p className="text-xs text-caution">
          Marked as failed but still healthy at the last recording, so check they really failed:{" "}
          <span className="font-mono">{rul.ends_healthy.join(", ")}</span>
        </p>
      )}
    </div>
  );
}
