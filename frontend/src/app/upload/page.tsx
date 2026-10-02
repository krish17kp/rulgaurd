"use client";

import { useRef, useState } from "react";
import {
  ApiError,
  Compatibility,
  DatasetProfileResponse,
  PredictRulResponse,
  inspectDataset,
  predictRulFromFemtoAcquisition,
} from "@/lib/api";

type DatasetType = "generic" | "femto";

type InspectState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: DatasetProfileResponse };

type PredictState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: PredictRulResponse };

const BADGE: Record<Compatibility, string> = {
  FULLY_SUPPORTED: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300",
  RETRAIN_REQUIRED: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  ADAPTER_REQUIRED: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  UNSUPPORTED: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  INVALID_INPUT: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
};

export default function UploadPage() {
  const [datasetType, setDatasetType] = useState<DatasetType>("generic");
  const [inspectState, setInspectState] = useState<InspectState>({ status: "idle" });
  const [predictState, setPredictState] = useState<PredictState>({ status: "idle" });
  const [declaredSamplingRateHz, setDeclaredSamplingRateHz] = useState("");
  const [declaredUnits, setDeclaredUnits] = useState("");
  // Bumped on every mode switch/new upload so an in-flight request whose
  // caller has since moved on can't overwrite the current state with a
  // stale result (found in review: switching modes mid-request, then
  // switching back, could resurrect an old response).
  const requestSeq = useRef(0);

  async function handleGenericFile(file: File) {
    const seq = ++requestSeq.current;
    setInspectState({ status: "loading" });
    try {
      const data = await inspectDataset(file, {
        declaredSamplingRateHz: declaredSamplingRateHz ? Number(declaredSamplingRateHz) : undefined,
        declaredUnits: declaredUnits || undefined,
      });
      if (seq === requestSeq.current) setInspectState({ status: "ready", data });
    } catch (err) {
      if (seq === requestSeq.current) setInspectState({ status: "error", error: (err as ApiError).detail });
    }
  }

  async function handleFemtoFile(file: File) {
    const seq = ++requestSeq.current;
    setPredictState({ status: "loading" });
    try {
      const data = await predictRulFromFemtoAcquisition(file);
      if (seq === requestSeq.current) setPredictState({ status: "ready", data });
    } catch (err) {
      if (seq === requestSeq.current) setPredictState({ status: "error", error: (err as ApiError).detail });
    }
  }

  function handleFile(file: File) {
    if (datasetType === "femto") {
      void handleFemtoFile(file);
    } else {
      void handleGenericFile(file);
    }
  }

  function switchDatasetType(next: DatasetType) {
    requestSeq.current++; // invalidate any in-flight request from the mode being left
    setDatasetType(next);
    // Each mode's result belongs to a specific uploaded file under a specific
    // mode - leaving it visible after switching modes (or re-uploading) could
    // show a stale RUL/compatibility result next to a file it wasn't computed
    // from. Found in review.
    setInspectState({ status: "idle" });
    setPredictState({ status: "idle" });
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-16">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Upload a dataset</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Choose what kind of file you&apos;re uploading. The system never guesses this from a
          headerless file&apos;s contents — you tell it, and it validates your claim before
          doing anything with it.
        </p>
      </header>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium">Dataset type</legend>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="radio"
            name="dataset-type"
            checked={datasetType === "femto"}
            onChange={() => switchDatasetType("femto")}
            className="mt-1"
          />
          <span>
            <span className="font-medium">FEMTO / supported bearing acquisition</span>
            <br />
            <span className="text-zinc-500">
              A raw <code>acc_*.csv</code> file in FEMTO&apos;s known fixed format (headerless,
              6 columns, 25.6kHz). Runs feature extraction and RUL prediction directly — no
              separate inspection step.
            </span>
          </span>
        </label>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="radio"
            name="dataset-type"
            checked={datasetType === "generic"}
            onChange={() => switchDatasetType("generic")}
            className="mt-1"
          />
          <span>
            <span className="font-medium">Unknown / other dataset (inspect only)</span>
            <br />
            <span className="text-zinc-500">
              Inspects the file&apos;s structure (delimiter, header, column meanings) and
              reports compatibility — it does not run a prediction. Optionally declare the
              sampling rate and units below if the file has no timestamp column; they are never
              guessed.
            </span>
          </span>
        </label>
      </fieldset>

      {datasetType === "generic" && (
        <div className="flex flex-col gap-3 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
          <label className="flex flex-col gap-1 text-sm">
            Declared sampling rate (Hz) — optional. Used only if no timestamp column is found; if
            the file has one and it disagrees with this value, the upload is rejected rather than
            silently preferring either source.
            <input
              type="number"
              min="0"
              step="any"
              value={declaredSamplingRateHz}
              onChange={(e) => setDeclaredSamplingRateHz(e.target.value)}
              placeholder="e.g. 25600"
              className="rounded border border-zinc-300 px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Declared units — optional
            <input
              type="text"
              value={declaredUnits}
              onChange={(e) => setDeclaredUnits(e.target.value)}
              placeholder="e.g. g, m/s^2"
              className="rounded border border-zinc-300 px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>
        </div>
      )}

      <input
        key={datasetType}
        type="file"
        accept={datasetType === "femto" ? ".csv" : ".csv,.txt,.tsv,.dat"}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          // Reset so picking the same file again (e.g. after switching modes
          // and back) still fires onChange instead of being a no-op.
          e.target.value = "";
        }}
        className="text-sm"
      />

      {datasetType === "femto" && (
        <>
          {predictState.status === "loading" && <p className="text-sm">Extracting features and predicting…</p>}

          {predictState.status === "error" && (
            <p className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
              {predictState.error}
            </p>
          )}

          {predictState.status === "ready" && (
            <div className="flex flex-col gap-2 rounded-lg border border-green-300 bg-green-50 p-4 dark:border-green-900 dark:bg-green-950">
              <p className="text-sm text-zinc-500">Predicted Remaining Useful Life</p>
              <p className="text-3xl font-semibold tracking-tight">
                {predictState.data.rul_hours.toFixed(2)} hours
              </p>
              <p className="text-xs text-zinc-500">
                ({predictState.data.rul_seconds.toFixed(0)} s) — model: {predictState.data.model_name}
              </p>
            </div>
          )}
        </>
      )}

      {datasetType === "generic" && (
        <>
          {inspectState.status === "loading" && <p className="text-sm">Inspecting…</p>}

          {inspectState.status === "error" && (
            <p className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
              {inspectState.error}
            </p>
          )}

          {inspectState.status === "ready" && (
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-3">
                <span className={`rounded-full px-3 py-1 text-xs font-medium ${BADGE[inspectState.data.compatibility]}`}>
                  {inspectState.data.compatibility.replace(/_/g, " ")}
                </span>
                <span className="text-sm text-zinc-500">{inspectState.data.profile.file}</span>
              </div>

              {inspectState.data.reasons.length > 0 && (
                <ul className="list-inside list-disc text-sm text-zinc-700 dark:text-zinc-300">
                  {inspectState.data.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              )}

              {inspectState.data.profile.columns && (
                <table className="w-full text-left text-xs">
                  <thead className="text-zinc-500">
                    <tr>
                      <th className="py-1 pr-3">Column</th>
                      <th className="py-1 pr-3">Mapped to</th>
                      <th className="py-1 pr-3">Confidence</th>
                      <th className="py-1 pr-3">Missing %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inspectState.data.profile.columns.map((c) => (
                      <tr key={c.name} className="border-t border-zinc-200 dark:border-zinc-800">
                        <td className="py-1 pr-3 font-mono">{c.name}</td>
                        <td className="py-1 pr-3">{c.canonical ?? "—"}</td>
                        <td className="py-1 pr-3">{c.confidence}</td>
                        <td className="py-1 pr-3">{(c.nan_fraction * 100).toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {inspectState.data.profile.warnings.length > 0 && (
                <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
                  {inspectState.data.profile.warnings.map((w) => (
                    <p key={w}>{w}</p>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </main>
  );
}
