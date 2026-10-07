"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  CrossDatasetExperiments,
  CrossDatasetResponse,
  DatasetMetricSummary,
  getCrossDatasetComparison,
} from "@/lib/api";

type State =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: CrossDatasetResponse };

export default function CrossDatasetPage() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    (async () => {
      try {
        const data = await getCrossDatasetComparison();
        setState({ status: "ready", data });
      } catch (err) {
        setState({ status: "error", error: (err as ApiError).detail ?? String(err) });
      }
    })();
  }, []);

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-8 px-6 py-16">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Cross-dataset comparison</h1>
        <p className="mt-1 text-sm text-foreground-muted">
          Real numbers read verbatim from <code>/evaluation/cross-dataset</code>, which assembles
          from the same committed artifacts as the Reliability page. Nothing here is recomputed
          in the browser.
        </p>
      </header>

      {state.status === "loading" && <p className="text-sm">Loading…</p>}
      {state.status === "error" && (
        <p className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {state.error}
        </p>
      )}

      {state.status === "ready" && (
        <>
          <section className="rounded-lg border border-caution/30 bg-caution/10 p-4 text-xs text-caution">
            {state.data.comparability_warning}
          </section>

          <section>
            <h2 className="text-lg font-semibold">In-domain trained results</h2>
            <DatasetCard summary={state.data.in_domain_trained_results.femto} />
          </section>

          <section>
            <h2 className="text-lg font-semibold">
              Not a zero-shot comparison (single-dataset, own split)
            </h2>
            <DatasetCard summary={state.data.not_zero_shot_single_dataset_results.college} />
          </section>

          {state.data.cross_dataset_experiments && (
            <CrossDatasetExperimentsSection data={state.data.cross_dataset_experiments} />
          )}

          {Object.keys(state.data.not_yet_available).length > 0 && (
            <section>
              <h2 className="text-lg font-semibold">Not yet available</h2>
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                {Object.entries(state.data.not_yet_available).map(([id, info]) => (
                  <PendingCard key={id} label={id.toUpperCase()} reason={info.reason} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}

const CATEGORY_LABEL: Record<string, string> = {
  "WITHIN-DOMAIN": "Within-domain (trained and tested on the same dataset, LOBO)",
  "ZERO-SHOT": "Zero-shot transfer (FEMTO-trained model, never saw this dataset)",
  "CALIBRATED": "Calibrated (FEMTO model + a linear map fit on other bearings of the target)",
  "MULTI-DATASET": "Multi-dataset (trained across datasets; LODO = left this domain out entirely)",
};

/** The real within-domain / zero-shot / calibrated / multi-dataset numbers
 * from reports/metrics/cross_dataset.json, via /evaluation/cross-dataset's
 * cross_dataset_experiments field. Zero-shot transfer is never relabeled as
 * "in-domain", and a negative skill value (worse than a label-free constant
 * guess) is shown as-is, not hidden - this is specifically where an
 * honest "FEMTO -> IMS zero-shot does not work" result belongs. */
function CrossDatasetExperimentsSection({ data }: { data: CrossDatasetExperiments }) {
  const categories = Array.from(new Set(data.summary.map((r) => r.category)));
  return (
    <section>
      <h2 className="text-lg font-semibold">Multi-dataset experiments</h2>
      <p className="mt-1 text-xs text-foreground-muted">
        From {data.generated_from}. Skill is held-out performance vs. a label-free constant guess
        (life-fraction units): 0 = no skill, negative = worse than guessing.
      </p>
      {categories.map((category) => (
        <div key={category} className="mt-4">
          <h3 className="text-sm font-semibold">{CATEGORY_LABEL[category] ?? category}</h3>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-foreground-muted">
                <tr>
                  <th className="pr-3 py-1">Experiment</th>
                  <th className="pr-3 py-1">Model</th>
                  <th className="pr-3 py-1">Test dataset</th>
                  <th className="pr-3 py-1">Bearings</th>
                  <th className="pr-3 py-1">MAE (h)</th>
                  <th className="pr-3 py-1">Skill</th>
                </tr>
              </thead>
              <tbody>
                {data.summary
                  .filter((r) => r.category === category)
                  .map((r, i) => (
                    <tr key={i} className="border-t border-surface-border">
                      <td className="pr-3 py-1">{r.experiment}</td>
                      <td className="pr-3 py-1">{r.model}</td>
                      <td className="pr-3 py-1">{r.test_domain}</td>
                      <td className="pr-3 py-1">{r.n_bearings}</td>
                      <td className="pr-3 py-1">
                        {r.mae_seconds != null ? (r.mae_seconds / 3600).toFixed(1) : "—"}
                      </td>
                      <td
                        className={`pr-3 py-1 font-medium ${
                          r.fraction_skill != null && r.fraction_skill < 0
                            ? "text-red-600 dark:text-red-400"
                            : ""
                        }`}
                      >
                        {r.fraction_skill != null ? r.fraction_skill.toFixed(3) : "—"}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      <div className="mt-4 rounded-lg border border-surface-border p-4">
        <h3 className="text-sm font-semibold">Skill on an unseen machine, by model</h3>
        <p className="mt-1 text-xs text-foreground-muted">
          &ldquo;unseen&rdquo; = mean zero-shot / leave-one-domain-out skill - the honest answer
          to &ldquo;how does this do on a machine it never saw&rdquo;.
        </p>
        {Object.entries(data.routing_skill_by_dataset).map(([model, byDataset]) => (
          <div key={model} className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
            <p className="col-span-full font-medium text-foreground">{model}</p>
            {Object.entries(byDataset).map(([dataset, skill]) => (
              <div key={dataset}>
                <p className="text-foreground-muted">{dataset}</p>
                <p className={`font-semibold ${skill < 0 ? "text-red-600 dark:text-red-400" : ""}`}>
                  {skill.toFixed(3)}
                  {skill < 0 ? " (worse than guessing)" : ""}
                </p>
              </div>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

function DatasetCard({ summary }: { summary: DatasetMetricSummary }) {
  const improvementPct =
    ((summary.naive_mae_seconds - summary.extra_trees_mae_seconds) / summary.naive_mae_seconds) * 100;
  return (
    <div className="mt-2 rounded-lg border border-surface-border p-4">
      <h3 className="font-medium">{summary.dataset}</h3>
      <dl className="mt-2 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <Stat label="Sampling rate" value={`${summary.sampling_rate_hz.toLocaleString()} Hz`} />
        <Stat label="Bearings" value={String(summary.bearings)} />
        <Stat label="Channels" value={summary.channels.join(", ")} />
        <Stat label="Evaluation" value={summary.evaluation_method} />
        <Stat label="ExtraTrees MAE" value={`${(summary.extra_trees_mae_seconds / 3600).toFixed(2)} h`} />
        <Stat label="Naive MAE" value={`${(summary.naive_mae_seconds / 3600).toFixed(2)} h`} />
        <Stat
          label={summary.naive_caveat ? "Improvement vs naive (see caveat)" : "Improvement vs naive"}
          value={`${improvementPct.toFixed(1)}%`}
        />
        <Stat label="n" value={String(summary.n)} />
      </dl>
      {summary.naive_caveat && (
        <p className="mt-2 text-xs font-medium text-caution">{summary.naive_caveat}</p>
      )}
      {summary.health_indicator_selected && (
        <p className="mt-2 text-xs text-foreground-muted">
          Health indicator: {summary.health_indicator_selected}
        </p>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-foreground-muted">{label}</dt>
      <dd className="font-semibold">{value}</dd>
    </div>
  );
}

function PendingCard({ label, reason }: { label: string; reason: string }) {
  return (
    <div className="rounded-lg border border-dashed border-surface-border p-4 text-xs text-foreground-muted">
      <p className="font-medium text-foreground">{label} — not yet available</p>
      <p className="mt-1">{reason}</p>
    </div>
  );
}
