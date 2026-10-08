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
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-14 px-6 py-16 sm:py-20">
      <header className="grid grid-cols-1 items-center gap-10 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="flex flex-col gap-5">
          <span className="w-fit rounded-full bg-accent/10 px-3 py-1 text-sm font-medium tracking-wide text-accent">
            Industrial predictive maintenance
          </span>
          <h1 className="text-5xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">
            Know when a bearing is running out of time.
          </h1>
          <p className="max-w-xl text-lg leading-relaxed text-foreground-muted">
            RULGuard estimates Remaining Useful Life from vibration data, and checks whether
            the model even applies to your signal before it reports a number.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Link
              href="/upload"
              className="inline-flex w-fit items-center rounded-lg bg-accent px-5 py-3 text-base font-semibold text-background shadow-sm transition-colors hover:bg-accent-strong"
            >
              Analyze Bearing Data
            </Link>
            <Link
              href="/datasets"
              className="inline-flex w-fit items-center rounded-lg border border-surface-border px-5 py-3 text-base font-medium text-foreground transition-colors hover:border-accent/50 hover:text-accent"
            >
              Explore Datasets
            </Link>
          </div>
        </div>

        <svg
          viewBox="0 0 320 220"
          role="img"
          aria-label="A degrading vibration signal trending from healthy to critical"
          className="hidden w-full max-w-sm justify-self-center text-accent lg:block"
        >
          <defs>
            <linearGradient id="hiCurve" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="var(--success)" />
              <stop offset="55%" stopColor="var(--caution)" />
              <stop offset="100%" stopColor="var(--danger)" />
            </linearGradient>
          </defs>
          <rect x="0" y="0" width="320" height="220" rx="16" fill="var(--surface)" stroke="var(--surface-border)" />
          <polyline
            points="20,70 55,60 90,75 125,55 160,95 195,80 230,130 265,110 300,165"
            fill="none"
            stroke="currentColor"
            strokeOpacity="0.35"
            strokeWidth="2"
          />
          <path
            d="M20,180 C 80,170 120,150 160,120 C 210,85 260,70 300,40"
            fill="none"
            stroke="url(#hiCurve)"
            strokeWidth="4"
            strokeLinecap="round"
          />
          <circle cx="300" cy="40" r="5" fill="var(--danger)" />
        </svg>
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
            <h2 className="text-lg font-semibold">{c.title}</h2>
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
