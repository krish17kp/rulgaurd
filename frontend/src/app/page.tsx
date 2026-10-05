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
    <main className="mx-auto flex max-w-3xl flex-col gap-10 px-6 py-16">
      <header className="flex flex-col gap-4">
        <h1 className="text-3xl font-semibold tracking-tight">RULGuard</h1>
        <p className="max-w-xl text-base text-zinc-600 dark:text-zinc-400">
          Predict bearing degradation and Remaining Useful Life from vibration data.
        </p>
        <Link
          href="/upload"
          className="inline-flex w-fit items-center rounded-lg bg-zinc-900 px-5 py-3 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          Analyze Bearing Data
        </Link>
      </header>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {CAPABILITIES.map((c) => (
          <div key={c.title} className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
            <h2 className="text-sm font-medium">{c.title}</h2>
            <p className="mt-1 text-sm text-zinc-500">{c.body}</p>
          </div>
        ))}
      </section>

      <section className="rounded-lg border border-amber-300 bg-amber-50 p-5 text-sm dark:border-amber-900 dark:bg-amber-950">
        <h2 className="font-medium text-amber-900 dark:text-amber-200">Scope and limitations</h2>
        <ul className="mt-2 list-inside list-disc space-y-1 text-amber-900 dark:text-amber-200">
          <li>The current model is trained on one public bearing dataset (FEMTO). Other kinds of data are refused, not silently adapted.</li>
          <li>This is offline analysis of recorded data, not a live/real-time deployment.</li>
          <li>No physical fault-type (inner/outer-race, ball, cage) diagnosis is made — only a severity band on the health indicator.</li>
        </ul>
      </section>

      <section className="rounded-lg border border-zinc-200 p-4 text-xs text-zinc-500 dark:border-zinc-800">
        Prediction service status:{" "}
        {health.status === "loading" && "checking…"}
        {health.status === "error" && <span className="text-red-600">unreachable</span>}
        {health.status === "ready" && (
          <span className={health.data.status === "ok" ? "text-green-600" : "text-amber-600"}>
            {health.data.status}
          </span>
        )}
      </section>
    </main>
  );
}
