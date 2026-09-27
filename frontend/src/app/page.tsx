"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, HealthResponse, ModelsInfoResponse, getHealth, getModelsInfo } from "@/lib/api";

type LoadState<T> =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: T };

export default function Home() {
  const [health, setHealth] = useState<LoadState<HealthResponse>>({ status: "loading" });
  const [info, setInfo] = useState<LoadState<ModelsInfoResponse>>({ status: "loading" });

  useEffect(() => {
    getHealth()
      .then((data) => setHealth({ status: "ready", data }))
      .catch((err: ApiError) => setHealth({ status: "error", error: err.detail }));
    getModelsInfo()
      .then((data) => setInfo({ status: "ready", data }))
      .catch((err: ApiError) => setInfo({ status: "error", error: err.detail }));
  }, []);

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-16">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">RULGuard</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Bearing degradation and Remaining Useful Life estimation from vibration data.
          </p>
        </div>
        <nav className="flex gap-4 text-sm">
          <Link className="underline" href="/upload">Upload</Link>
          <Link className="underline" href="/degradation">Degradation</Link>
          <Link className="underline" href="/predict">Predict</Link>
        </nav>
      </header>

      <section className="rounded-lg border border-zinc-200 p-5 dark:border-zinc-800">
        <h2 className="text-sm font-medium text-zinc-500">Prediction service</h2>
        {health.status === "loading" && <p className="mt-2 text-sm">Checking service status…</p>}
        {health.status === "error" && (
          <p className="mt-2 text-sm text-red-600">
            Unreachable: {health.error}. The FastAPI backend must be running separately
            (see backend README) — this page never fabricates a status.
          </p>
        )}
        {health.status === "ready" && (
          <div className="mt-2 space-y-1 text-sm">
            <p>
              Status:{" "}
              <span className={health.data.status === "ok" ? "text-green-600" : "text-amber-600"}>
                {health.data.status}
              </span>
            </p>
            {Object.entries(health.data.models_loaded).map(([name, loaded]) => (
              <p key={name}>
                {name}: <span className={loaded ? "text-green-600" : "text-red-600"}>
                  {loaded ? "loaded" : "not found"}
                </span>
              </p>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-lg border border-zinc-200 p-5 dark:border-zinc-800">
        <h2 className="text-sm font-medium text-zinc-500">Model info</h2>
        {info.status === "loading" && <p className="mt-2 text-sm">Loading…</p>}
        {info.status === "error" && (
          <p className="mt-2 text-sm text-red-600">Unavailable: {info.error}</p>
        )}
        {info.status === "ready" && (
          <div className="mt-2 space-y-1 text-sm">
            <p>
              Selected model:{" "}
              <span className="font-mono">{info.data.selected_model?.selected ?? "none"}</span>
            </p>
            <p>Supported datasets: {info.data.supported_datasets.join(", ")}</p>
            <p className="text-zinc-500">{info.data.note}</p>
          </div>
        )}
      </section>

      <section className="rounded-lg border border-amber-300 bg-amber-50 p-5 text-sm dark:border-amber-900 dark:bg-amber-950">
        <h2 className="font-medium text-amber-900 dark:text-amber-200">Scope and limitations</h2>
        <ul className="mt-2 list-inside list-disc space-y-1 text-amber-900 dark:text-amber-200">
          <li>Every cached model is trained on FEMTO learning bearings only. Other datasets are refused, not adapted silently.</li>
          <li>This is offline analysis of recorded data, not a live/real-time deployment.</li>
          <li>No physical fault-type (inner/outer-race, ball, cage) diagnosis is made — only a severity band on the health indicator.</li>
          <li>The RUL endpoint currently accepts a pre-extracted feature row, not a raw CSV upload — see <Link className="underline" href="/predict">Predict</Link>.</li>
        </ul>
      </section>
    </main>
  );
}
