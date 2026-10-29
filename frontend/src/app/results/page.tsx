"use client";

import { useEffect, useState } from "react";
import { AnalysisBundleResponse, ApiError, RoutingBundlePayload } from "@/lib/api";
import { getRoutingResult, listRoutingResults } from "@/lib/labApi";
import { RoutingBundleResult } from "@/components/RoutingBundleResult";

const NAMES: Record<string, string> = { femto: "FEMTO / PRONOSTIA", xjtu: "XJTU-SY", ims: "IMS", college: "College rig" };

/** The research lab's Universal Machine Analysis: whole-dataset runs done offline on the
 * full raw data (profile, applicability, health, routing, RUL or suppression), shown with
 * the same renderer as an uploaded Analysis Bundle. */
export default function ResultsPage() {
  const [datasets, setDatasets] = useState<string[] | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisBundleResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRoutingResults()
      .then((list) => {
        setDatasets(list);
        if (list.length) setActive(list[0]);
      })
      .catch((err) => setError((err as ApiError).detail ?? String(err)));
  }, []);

  useEffect(() => {
    if (!active) return;
    getRoutingResult(active)
      .then(setResult)
      .catch((err) => setError((err as ApiError).detail ?? String(err)));
  }, [active]);

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-6 py-16">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Full dataset results</h1>
        <p className="mt-1 text-sm text-foreground-muted">
          Whole run-to-failure datasets analyzed on their full raw data: what was recognized, whether
          the model applies, each bearing&apos;s health, and whether an RUL estimate is given or
          withheld (and why). To run your own dataset, use{" "}
          <a href="/upload" className="text-accent underline">
            Analyze
          </a>
          .
        </p>
      </header>

      {datasets && (
        <div className="flex flex-wrap gap-2" role="tablist">
          {datasets.map((d) => (
            <button
              key={d}
              type="button"
              role="tab"
              aria-selected={active === d}
              onClick={() => {
                setResult(null);
                setActive(d);
              }}
              className={`rounded-full border-2 border-surface-border px-4 py-1.5 text-sm font-semibold ${
                active === d ? "bg-foreground text-background" : "bg-surface hover:bg-mint"
              }`}
            >
              {NAMES[d] ?? d}
            </button>
          ))}
        </div>
      )}

      {error && <p className="text-sm text-danger">{error}</p>}
      {active && !result && !error && <p className="text-sm text-foreground-muted">Loading results…</p>}
      {result?.payload && <RoutingBundleResult data={result.payload as RoutingBundlePayload} />}
    </main>
  );
}
