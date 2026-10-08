"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, HealthResponse, getHealth } from "@/lib/api";

type LoadState<T> =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: T };

const CAPABILITIES = [
  { title: "Remaining Useful Life", body: "An estimate, in hours, of how much life a bearing has left based on its current vibration signal." },
  { title: "Health / degradation monitoring", body: "A severity band (healthy, degrading, critical) on the signal over a run — not a specific fault diagnosis." },
  { title: "Applicability checking", body: "Before trusting a number, the system checks whether your signal looks like the data the model was trained on." },
  { title: "Reliability evaluation", body: "Real, measured accuracy of the model against held-out bearings it never trained on." },
];

export default function Home() {
  const [health, setHealth] = useState<LoadState<HealthResponse>>({ status: "loading" });

  useEffect(() => {
    getHealth()
      .then((data) => setHealth({ status: "ready", data }))
      .catch((err: ApiError) => setHealth({ status: "error", error: err.detail }));
  }, []);

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-14 px-6 py-16 sm:py-20">
      <header className="flex flex-col gap-5">
        <span className="w-fit rounded-full bg-accent/10 px-3 py-1 text-xs font-medium tracking-wide text-accent">
          Industrial predictive maintenance
        </span>
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">RULGuard</h1>
        <p className="max-w-xl text-lg leading-relaxed text-foreground-muted">
          Predict bearing degradation before failure. RULGuard analyzes vibration data to
          estimate Remaining Useful Life, and verifies whether the current model is even
          applicable to your signal before it reports a number.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href="/upload"
            className="inline-flex w-fit items-center rounded-lg bg-accent px-5 py-3 text-sm font-semibold text-background shadow-sm transition-colors hover:bg-accent-strong"
          >
            Analyze Bearing Data
          </Link>
          <Link
            href="/evaluation"
            className="inline-flex w-fit items-center rounded-lg border border-surface-border px-5 py-3 text-sm font-medium text-foreground transition-colors hover:border-accent/50 hover:text-accent"
          >
            View Model Reliability
          </Link>
        </div>
      </header>

      <section aria-label="Pipeline" className="flex flex-wrap items-center gap-2 text-xs text-foreground-muted">
        {["Vibration Data", "Feature Extraction", "Applicability Check", "RUL Prediction", "Maintenance Insight"].map(
          (step, i, arr) => (
            <span key={step} className="flex items-center gap-2">
              <span className="rounded-full border border-surface-border bg-surface px-3 py-1.5 font-medium text-foreground">
                {step}
              </span>
              {i < arr.length - 1 && <span aria-hidden>→</span>}
            </span>
          ),
        )}
      </section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {CAPABILITIES.map((c) => (
          <div
            key={c.title}
            className="rounded-xl border border-surface-border bg-surface p-5 shadow-sm transition-colors hover:border-accent/40"
          >
            <h2 className="text-sm font-semibold">{c.title}</h2>
            <p className="mt-1.5 text-sm leading-relaxed text-foreground-muted">{c.body}</p>
          </div>
        ))}
      </section>

      <section className="grid grid-cols-2 gap-4 rounded-xl border border-surface-border bg-surface p-5 text-sm sm:grid-cols-4">
        {[
          ["Supported dataset", "FEMTO"],
          ["Primary model", "Extra Trees"],
          ["Analysis", "Recorded acquisitions"],
          ["Safeguard", "Applicability / OOD check"],
        ].map(([label, value]) => (
          <div key={label}>
            <div className="text-xs uppercase tracking-wide text-foreground-muted">{label}</div>
            <div className="mt-1 font-medium">{value}</div>
          </div>
        ))}
      </section>

      <section className="rounded-lg border border-caution/30 bg-caution/10 p-5 text-sm">
        <h2 className="font-medium text-caution">Scope and limitations</h2>
        <ul className="mt-2 list-inside list-disc space-y-1 text-foreground">
          <li>The current model is trained on one public bearing dataset (FEMTO). Other kinds of data are refused, not silently adapted.</li>
          <li>This is offline analysis of recorded data, not a live/real-time deployment.</li>
          <li>No physical fault-type (inner/outer-race, ball, cage) diagnosis is made — only a severity band on the health indicator.</li>
        </ul>
      </section>

      <section className="rounded-lg border border-surface-border p-4 text-xs text-foreground-muted">
        Prediction service status:{" "}
        {health.status === "loading" && "checking…"}
        {health.status === "error" && <span className="text-danger">unreachable</span>}
        {health.status === "ready" && (
          <span className={health.data.status === "ok" ? "text-success" : "text-caution"}>
            {health.data.status}
          </span>
        )}
      </section>
    </main>
  );
}
