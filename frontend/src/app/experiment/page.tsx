"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  Applicability,
  FaultSnapshot,
  SyntheticConfig,
  SyntheticResult,
  downloadSyntheticZip,
  getExperimentFixtures,
  getExperimentSnapshot,
  runSynthetic,
} from "@/lib/labApi";
import { SignalChart } from "@/components/SignalChart";
import { MultiSeriesChart } from "@/components/MultiSeriesChart";

type Tab = "cwru" | "paderborn" | "synthetic";
const TABS: Array<{ id: Tab; label: string }> = [
  { id: "cwru", label: "CWRU (real)" },
  { id: "paderborn", label: "Paderborn (real)" },
  { id: "synthetic", label: "Synthetic (simulated)" },
];
const LEVEL_STYLE = { HIGH: "bg-mint", MEDIUM: "bg-caution/20", LOW: "bg-danger/15" } as const;

function ApplicabilityBadge({ a }: { a: Applicability | null }) {
  if (!a) return <p className="text-xs text-foreground-muted">FEMTO applicability model unavailable.</p>;
  return (
    <div className={`rounded-xl border border-surface-border p-3 text-sm ${LEVEL_STYLE[a.level]}`}>
      FEMTO-model applicability: <strong>{a.level}</strong> ({a.shift_ratio.toFixed(2)}x in-domain feature shift)
      {a.reasons.length > 0 && (
        <ul className="mt-1 list-disc pl-5 text-xs">
          {a.reasons.slice(0, 3).map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FaultSnapshotView({ data }: { data: FaultSnapshot }) {
  return (
    <section className="flex flex-col gap-4 rounded-xl border border-surface-border bg-surface p-4">
      <h2 className="text-lg font-semibold">{data.label}</h2>
      <div>
        <p className="mb-1 text-xs font-medium text-foreground-muted">
          Waveform, first 0.1 s at {data.sample_rate_hz.toLocaleString()} Hz
        </p>
        <SignalChart values={data.signal.waveform} xLabel="sample" yLabel="amplitude" />
      </div>
      <div>
        <p className="mb-1 text-xs font-medium text-foreground-muted">FFT magnitude (whole recording)</p>
        <SignalChart values={data.signal.fft_magnitude} xValues={data.signal.fft_frequency_hz} xLabel="Hz" yLabel="magnitude" />
      </div>
      <ApplicabilityBadge a={data.applicability} />
      <p className="rounded-xl border border-surface-border bg-background p-3 text-sm">
        <strong>No RUL estimate.</strong> {data.note}
      </p>
      <details>
        <summary className="cursor-pointer text-sm font-medium">Features (time and frequency domain)</summary>
        <table className="mt-2 w-full text-left text-xs">
          <tbody>
            {Object.entries(data.features).map(([k, v]) => (
              <tr key={k} className="border-t border-surface-border">
                <td className="py-1 pr-3 font-mono">{k}</td>
                <td className="py-1 text-right tabular-nums">{v.toPrecision(5)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}

function FixturePicker({ dataset, fixtures }: { dataset: "cwru" | "paderborn"; fixtures: Record<string, string> }) {
  const ids = Object.keys(fixtures);
  const [fileId, setFileId] = useState(ids[0]);
  const [data, setData] = useState<FaultSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setBusy(true);
    setError(null);
    try {
      setData(await getExperimentSnapshot(dataset, fileId));
    } catch (err) {
      setError((err as ApiError).detail ?? String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="rounded-xl border border-surface-border bg-danger/10 p-3 text-sm font-semibold">
        Real data: fault diagnosis and condition monitoring (
        {dataset === "cwru" ? "Case Western Reserve University Bearing Data Center" : "Paderborn University KAt-DataCenter"}).
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm font-medium">
          Condition
          <select
            value={fileId}
            onChange={(e) => setFileId(e.target.value)}
            className="rounded-lg border border-surface-border bg-background px-3 py-2"
          >
            {ids.map((id) => (
              <option key={id} value={id}>
                {fixtures[id]}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => void load()}
          disabled={busy}
          className="rounded-full border-2 border-surface-border bg-mint px-5 py-2 font-display text-sm font-bold disabled:opacity-60"
        >
          {busy ? "Loading…" : "Load example recording"}
        </button>
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
      {data && <FaultSnapshotView data={data} />}
    </div>
  );
}

const FIELDS: Array<{ key: keyof SyntheticConfig; label: string; step: number }> = [
  { key: "seed", label: "Random seed", step: 1 },
  { key: "n_acquisitions", label: "Acquisitions", step: 1 },
  { key: "samples_per_acquisition", label: "Samples per acquisition", step: 1 },
  { key: "sample_rate_hz", label: "Sample rate (Hz)", step: 100 },
  { key: "shaft_freq_hz", label: "Shaft frequency (Hz)", step: 1 },
  { key: "baseline_noise_std", label: "Baseline noise std", step: 0.01 },
];

function SyntheticPanel() {
  const [cfg, setCfg] = useState<SyntheticConfig>({
    seed: 42,
    n_acquisitions: 10,
    samples_per_acquisition: 2560,
    sample_rate_hz: 25600,
    shaft_freq_hz: 50,
    baseline_noise_std: 0.05,
  });
  const [result, setResult] = useState<SyntheticResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      setResult(await runSynthetic(cfg));
    } catch (err) {
      setError((err as ApiError).detail ?? String(err));
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    const blob = await downloadSyntheticZip(cfg);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "synthetic_bearing.zip";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="rounded-xl border border-surface-border bg-caution/15 p-3 text-sm font-semibold">
        Synthetic, simulated data: a controlled demonstration signal, never real-world validation.
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {FIELDS.map((f) => (
          <label key={f.key} className="flex flex-col gap-1 text-sm font-medium">
            {f.label}
            <input
              type="number"
              step={f.step}
              value={cfg[f.key]}
              onChange={(e) => setCfg({ ...cfg, [f.key]: Number(e.target.value) })}
              className="rounded-lg border border-surface-border bg-background px-3 py-2"
            />
          </label>
        ))}
      </div>
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => void generate()}
          disabled={busy}
          className="rounded-full border-2 border-surface-border bg-mint px-5 py-2 font-display text-sm font-bold disabled:opacity-60"
        >
          {busy ? "Generating…" : "Generate synthetic bearing"}
        </button>
        <button
          type="button"
          onClick={() => void download()}
          className="rounded-full border-2 border-surface-border bg-surface px-5 py-2 font-display text-sm font-bold hover:bg-mint"
        >
          Download synthetic_bearing.zip
        </button>
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
      {result && (
        <section className="flex flex-col gap-4 rounded-xl border border-surface-border bg-surface p-4">
          <div>
            <p className="mb-1 text-xs font-medium text-foreground-muted">First acquisition, vibration X</p>
            <SignalChart values={result.first_acquisition} xLabel="sample" yLabel="amplitude" />
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-foreground-muted">Degradation progression</p>
            <MultiSeriesChart
              xLabel="acquisition"
              series={[
                { label: "RMS", color: "#3d2bff", points: result.rms.map((y, x) => ({ x, y })) },
                { label: "kurtosis", color: "#ff4fd8", points: result.kurtosis.map((y, x) => ({ x, y })) },
              ]}
            />
          </div>
          <ApplicabilityBadge a={result.applicability} />
          {result.rul_status && (
            <p className="text-sm">
              RUL:{" "}
              {result.rul_status === "suppressed" ? (
                <>
                  <strong>suppressed</strong>. This run is out of domain for the frozen FEMTO model, so no
                  RUL estimate is shown.
                </>
              ) : (
                <>routing status {result.rul_status} (synthetic data, never evidence of real-world accuracy).</>
              )}
            </p>
          )}
        </section>
      )}
    </div>
  );
}

/** The research lab's Experiment Lab: datasets that do not fit a trajectory model. */
export default function ExperimentPage() {
  const [tab, setTab] = useState<Tab>("cwru");
  const [fixtures, setFixtures] = useState<{ cwru: Record<string, string>; paderborn: Record<string, string> } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getExperimentFixtures()
      .then(setFixtures)
      .catch((err) => setError((err as ApiError).detail ?? String(err)));
  }, []);

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-6 py-16">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Experiment lab</h1>
        <p className="mt-1 text-sm text-foreground-muted">
          Datasets that are not run-to-failure trajectories. CWRU and Paderborn are fault-diagnosis
          snapshots with no RUL ground truth; the synthetic simulator is demonstration data. FEMTO,
          college and XJTU-SY have their own pages.
        </p>
      </header>
      <div className="flex flex-wrap gap-2" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`rounded-full border-2 border-surface-border px-4 py-1.5 text-sm font-semibold ${
              tab === t.id ? "bg-foreground text-background" : "bg-surface hover:bg-mint"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
      {tab === "synthetic" && <SyntheticPanel />}
      {tab !== "synthetic" && fixtures && <FixturePicker key={tab} dataset={tab} fixtures={fixtures[tab]} />}
    </main>
  );
}
