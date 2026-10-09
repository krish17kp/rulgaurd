"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ApiError,
  CrossDatasetResponse,
  FaultDiagnosisDataset,
  getCrossDatasetComparison,
} from "@/lib/api";
import { SignalChart } from "@/components/SignalChart";

type State =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: CrossDatasetResponse };

export default function DatasetsPage() {
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
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-10 px-6 py-16">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Datasets</h1>
        <p className="mt-1 text-base text-foreground-muted">
          Real and synthetic data this project has actually processed. See{" "}
          <Link href="/cross-dataset" className="text-accent underline">
            cross-dataset comparison
          </Link>{" "}
          for the numeric breakdown.
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
          <section>
            <h2 className="text-lg font-semibold">Real, run-to-failure RUL datasets</h2>
            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              <RealRulCard
                name={state.data.in_domain_trained_results.femto.dataset}
                samplingRateHz={state.data.in_domain_trained_results.femto.sampling_rate_hz}
                channels={state.data.in_domain_trained_results.femto.channels}
                purpose="In-domain trained and evaluated (leave-one-bearing-out)."
                href="/trajectory"
              />
              <RealRulCard
                name={state.data.not_zero_shot_single_dataset_results.college.dataset}
                samplingRateHz={state.data.not_zero_shot_single_dataset_results.college.sampling_rate_hz}
                channels={state.data.not_zero_shot_single_dataset_results.college.channels}
                purpose="Single physical bearing, own chronological split - not a FEMTO zero-shot test."
                caveat={state.data.not_zero_shot_single_dataset_results.college.naive_caveat}
                href="/trajectory"
              />
            </div>
          </section>

          {state.data.cross_dataset_experiments && (
            <section>
              <h2 className="text-lg font-semibold">Real, zero-shot transfer dataset</h2>
              <ImsCard data={state.data} />
            </section>
          )}

          {state.data.fault_diagnosis_datasets && (
            <section>
              <h2 className="text-lg font-semibold">
                Real, fault-diagnosis / condition-monitoring datasets
              </h2>
              <p className="mt-1 text-xs text-foreground-muted">
                These record fixed-condition snapshots, not a degradation trajectory - there is
                no RUL ground truth, so none is shown.
              </p>
              <div className="mt-3 grid gap-4 sm:grid-cols-2">
                {Object.entries(state.data.fault_diagnosis_datasets).map(([id, d]) => (
                  <FaultDiagnosisCard key={id} dataset={d} />
                ))}
              </div>
            </section>
          )}

          <section>
            <h2 className="text-lg font-semibold">Synthetic demonstration</h2>
            <SyntheticCard />
          </section>

          {Object.keys(state.data.not_yet_available).length > 0 && (
            <section>
              <h2 className="text-lg font-semibold">Not yet available</h2>
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                {Object.entries(state.data.not_yet_available).map(([id, info]) => (
                  <div key={id} className="rounded-lg border border-dashed border-surface-border p-4 text-xs text-foreground-muted">
                    <p className="font-medium text-foreground">{id.toUpperCase()} — not yet available</p>
                    <p className="mt-1">{info.reason}</p>
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}

function Badge({ tone }: { tone: "real" | "synthetic" }) {
  return (
    <span
      className={
        tone === "real"
          ? "rounded-full bg-accent/10 px-2.5 py-0.5 text-xs font-semibold text-accent"
          : "rounded-full bg-caution/20 px-2.5 py-0.5 text-xs font-semibold text-caution"
      }
    >
      {tone === "real" ? "REAL DATA" : "SYNTHETIC"}
    </span>
  );
}

function RealRulCard({
  name, samplingRateHz, channels, purpose, caveat, href,
}: {
  name: string; samplingRateHz: number; channels: string[]; purpose: string; caveat?: string; href: string;
}) {
  return (
    <div className="rounded-lg border border-surface-border p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-medium">{name}</h3>
        <Badge tone="real" />
      </div>
      <p className="mt-2 text-xs text-foreground-muted">{purpose}</p>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div><dt className="text-foreground-muted">Run-to-failure</dt><dd className="font-semibold">YES</dd></div>
        <div><dt className="text-foreground-muted">RUL supported</dt><dd className="font-semibold">YES</dd></div>
        <div><dt className="text-foreground-muted">Sampling rate</dt><dd>{samplingRateHz.toLocaleString()} Hz</dd></div>
        <div><dt className="text-foreground-muted">Channels</dt><dd>{channels.join(", ")}</dd></div>
      </dl>
      {caveat && <p className="mt-2 text-xs font-medium text-caution">{caveat}</p>}
      <Link href={href} className="mt-3 inline-block text-xs font-medium text-accent underline">
        Explore trajectory &rarr;
      </Link>
    </div>
  );
}

function ImsCard({ data }: { data: CrossDatasetResponse }) {
  const cde = data.cross_dataset_experiments;
  if (!cde) return null;
  const imsRows = cde.summary.filter((r) => r.test_domain === "ims");
  const imsSkill = cde.routing_skill_by_dataset["raw_seconds"]?.["ims"];
  return (
    <div className="mt-3 rounded-lg border border-surface-border p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-medium">IMS / NASA bearing run-to-failure</h3>
        <Badge tone="real" />
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div><dt className="text-foreground-muted">Run-to-failure</dt><dd className="font-semibold">YES</dd></div>
        <div><dt className="text-foreground-muted">FEMTO zero-shot RUL</dt><dd className="font-semibold">
          {imsSkill != null && imsSkill < 0 ? "SUPPORTED, but LOW skill" : "experimental"}
        </dd></div>
      </dl>
      {imsSkill != null && (
        <p className={`mt-2 text-xs font-medium ${imsSkill < 0 ? "text-red-600 dark:text-red-400" : ""}`}>
          FEMTO &rarr; IMS zero-shot skill: {imsSkill.toFixed(3)}
          {imsSkill < 0 ? " (worse than a label-free constant guess - an honest negative result, not hidden)" : ""}
        </p>
      )}
      {imsRows.length === 0 && (
        <p className="mt-2 text-xs text-foreground-muted">
          No zero-shot experiment row found for IMS in the current cross_dataset.json.
        </p>
      )}
      <Link href="/cross-dataset" className="mt-3 inline-block text-xs font-medium text-accent underline">
        See full zero-shot table &rarr;
      </Link>
    </div>
  );
}

function FaultDiagnosisCard({ dataset: d }: { dataset: FaultDiagnosisDataset }) {
  return (
    <div className="rounded-lg border border-surface-border p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-medium">{d.dataset}</h3>
        <Badge tone="real" />
      </div>
      <p className="mt-1 text-xs font-semibold text-caution">FAULT DIAGNOSIS / CONDITION MONITORING</p>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div><dt className="text-foreground-muted">Run-to-failure</dt><dd className="font-semibold">NO</dd></div>
        <div><dt className="text-foreground-muted">RUL supported</dt><dd className="font-semibold">NO</dd></div>
        <div><dt className="text-foreground-muted">Sampling rate</dt><dd>{d.sampling_rate_hz.toLocaleString()} Hz</dd></div>
        <div><dt className="text-foreground-muted">Channels</dt><dd>{d.channels.join(", ")}</dd></div>
      </dl>
      <p className="mt-2 text-xs text-foreground-muted">
        Conditions: {d.conditions.map((c) => c.label).join(", ")}
      </p>

      {d.representative && (
        <div className="mt-3">
          <p className="text-xs font-medium">Representative waveform ({d.representative.condition})</p>
          <SignalChart values={d.representative.signal} height={100} yLabel="amplitude" />
          <p className="mt-1 text-xs font-medium">FFT</p>
          <SignalChart
            values={d.representative.fft.magnitude}
            xValues={d.representative.fft.frequency_hz}
            height={100}
            yLabel="|FFT|"
          />
        </div>
      )}

      {d.applicability && (
        <p
          className={`mt-2 text-xs font-medium ${
            d.applicability.level === "LOW" ? "text-red-600 dark:text-red-400" : ""
          }`}
        >
          FEMTO-model applicability: {d.applicability.level} ({d.applicability.shift_ratio.toFixed(2)}x shift)
        </p>
      )}
      <p className="mt-2 rounded border border-surface-border bg-surface px-2 py-1.5 text-xs">
        <strong>RUL evaluation unavailable.</strong> {d.rul_unavailable_reason}
      </p>
      <p className="mt-1 text-xs text-foreground-muted break-all">Source: {d.source}</p>
    </div>
  );
}

function SyntheticCard() {
  return (
    <div className="mt-3 rounded-lg border border-caution/40 bg-caution/5 p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-medium">Synthetic bearing degradation simulator</h3>
        <Badge tone="synthetic" />
      </div>
      <p className="mt-2 text-xs font-semibold text-caution">
        SYNTHETIC DEMONSTRATION — NOT REAL-WORLD VALIDATION
      </p>
      <p className="mt-2 text-xs text-foreground-muted">
        A seeded signal generator for exercising the pipeline end to end. Still routed through
        the real applicability check — out-of-domain results correctly suppress RUL. Never
        combined with real-world model performance.
      </p>
    </div>
  );
}
