"use client";

import { useRef, useState } from "react";
import {
  ApiError,
  Compatibility,
  DatasetProfileResponse,
  PredictRulResponse,
  inspectDataset,
  inspectDatasetBlob,
  predictRulFromFemtoAcquisition,
  predictRulFromFemtoAcquisitionBlob,
} from "@/lib/api";
import { ApplicabilityNote } from "@/components/ApplicabilityNote";
import { ExplainResult } from "@/components/ExplainResult";
import { SignalAndFeatures } from "@/components/SignalAndFeatures";
import { SuppressedResultNotice, isSuppressedApplicability } from "@/components/SuppressedResultNotice";
import { BlobUploadError, DIRECT_UPLOAD_THRESHOLD_BYTES, uploadFileToBlob } from "@/lib/blobUpload";

type DatasetType = "femto" | "generic";

// "uploading" is the direct-to-storage leg (browser -> Blob, has real
// progress); "loading" is the backend processing leg once the upload is
// done or the file was small enough to send directly - kept distinct so
// the UI never claims "processing" while bytes are still in flight.
type InspectState =
  | { status: "idle" }
  | { status: "uploading"; progress: number }
  | { status: "loading" }
  | { status: "error"; error: string; retryable: boolean; retry: () => void }
  | { status: "ready"; data: DatasetProfileResponse };

type PredictState =
  | { status: "idle" }
  | { status: "uploading"; progress: number }
  | { status: "loading" }
  | { status: "error"; error: string; retryable: boolean; retry: () => void; suppressed: boolean }
  | { status: "ready"; data: PredictRulResponse };

const BADGE: Record<Compatibility, string> = {
  FULLY_SUPPORTED: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300",
  RETRAIN_REQUIRED: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  ADAPTER_REQUIRED: "bg-caution/15 text-caution",
  UNSUPPORTED: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  INVALID_INPUT: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function applicabilityInterpretation(level: "HIGH" | "MEDIUM" | "LOW" | null): string {
  if (level === "HIGH") {
    return "This signal looks like the data the model was trained on — the RUL estimate above can be trusted at face value.";
  }
  if (level === "MEDIUM") {
    return "This signal differs somewhat from the model's training data. The RUL estimate is reported as experimental, not suppressed.";
  }
  if (level === "LOW") {
    return "This signal differs substantially from the data used to train the current model. RUL is intentionally suppressed rather than guessed.";
  }
  return "Applicability could not be checked for this result (reference data unavailable) — treat the number with extra caution.";
}

export default function UploadPage() {
  const [datasetType, setDatasetType] = useState<DatasetType>("femto");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [inspectState, setInspectState] = useState<InspectState>({ status: "idle" });
  const [predictState, setPredictState] = useState<PredictState>({ status: "idle" });
  const [declaredSamplingRateHz, setDeclaredSamplingRateHz] = useState("");
  const [declaredUnits, setDeclaredUnits] = useState("");
  // Bumped on every mode switch/new analysis so an in-flight request whose
  // caller has since moved on can't overwrite the current state with a
  // stale result (found in review: switching modes mid-request, then
  // switching back, could resurrect an old response).
  const requestSeq = useRef(0);

  async function handleGenericFile(file: File) {
    const seq = ++requestSeq.current;
    const retry = () => handleGenericFile(file);
    const options = {
      declaredSamplingRateHz: declaredSamplingRateHz ? Number(declaredSamplingRateHz) : undefined,
      declaredUnits: declaredUnits || undefined,
    };
    // Mirror the backend's declared-field bounds (MAX_SAMPLING_RATE_HZ, 40-char units) here,
    // before any upload starts - otherwise a >=4MB file reaches Vercel Blob storage and only
    // then gets rejected by the backend, leaving the blob behind until the finally cleanup
    // runs (review finding: a value failing *request validation* on /dataset/inspect/blob
    // used to skip that finally entirely; the backend now validates inside it, but it's still
    // wasted upload bandwidth to let an obviously-bad value get that far).
    if (
      options.declaredSamplingRateHz !== undefined &&
      (!Number.isFinite(options.declaredSamplingRateHz) ||
        options.declaredSamplingRateHz <= 0 ||
        options.declaredSamplingRateHz > 1_000_000)
    ) {
      setInspectState({
        status: "error",
        error: "Declared sampling rate must be a positive number up to 1,000,000 Hz.",
        retryable: false,
        retry,
      });
      return;
    }
    if (options.declaredUnits !== undefined && options.declaredUnits.length > 40) {
      setInspectState({
        status: "error",
        error: "Declared units must be at most 40 characters.",
        retryable: false,
        retry,
      });
      return;
    }
    try {
      let data: DatasetProfileResponse;
      if (file.size >= DIRECT_UPLOAD_THRESHOLD_BYTES) {
        setInspectState({ status: "uploading", progress: 0 });
        const blobUrl = await uploadFileToBlob(file, (progress) => {
          if (seq === requestSeq.current) setInspectState({ status: "uploading", progress });
        });
        if (seq !== requestSeq.current) return;
        setInspectState({ status: "loading" });
        data = await inspectDatasetBlob(blobUrl, options);
      } else {
        setInspectState({ status: "loading" });
        data = await inspectDataset(file, options);
      }
      if (seq === requestSeq.current) setInspectState({ status: "ready", data });
    } catch (err) {
      if (seq !== requestSeq.current) return;
      const message = err instanceof BlobUploadError ? err.message : (err as ApiError).detail;
      const retryable = err instanceof BlobUploadError ? true : (err as ApiError).retryable;
      setInspectState({ status: "error", error: message, retryable, retry });
    }
  }

  async function handleFemtoFile(file: File) {
    const seq = ++requestSeq.current;
    const retry = () => handleFemtoFile(file);
    try {
      let data: PredictRulResponse;
      if (file.size >= DIRECT_UPLOAD_THRESHOLD_BYTES) {
        setPredictState({ status: "uploading", progress: 0 });
        const blobUrl = await uploadFileToBlob(file, (progress) => {
          if (seq === requestSeq.current) setPredictState({ status: "uploading", progress });
        });
        if (seq !== requestSeq.current) return;
        setPredictState({ status: "loading" });
        data = await predictRulFromFemtoAcquisitionBlob(blobUrl);
      } else {
        setPredictState({ status: "loading" });
        data = await predictRulFromFemtoAcquisition(file);
      }
      if (seq === requestSeq.current) setPredictState({ status: "ready", data });
    } catch (err) {
      if (seq !== requestSeq.current) return;
      const message = err instanceof BlobUploadError ? err.message : (err as ApiError).detail;
      const retryable = err instanceof BlobUploadError ? true : (err as ApiError).retryable;
      const suppressed = err instanceof ApiError && isSuppressedApplicability(err);
      setPredictState({ status: "error", error: message, retryable, retry, suppressed });
    }
  }

  function analyze() {
    if (!selectedFile) return;
    if (datasetType === "femto") {
      void handleFemtoFile(selectedFile);
    } else {
      void handleGenericFile(selectedFile);
    }
  }

  function resetForNewFile() {
    requestSeq.current++; // invalidate any in-flight request
    setSelectedFile(null);
    setInspectState({ status: "idle" });
    setPredictState({ status: "idle" });
  }

  function switchDatasetType(next: DatasetType) {
    setDatasetType(next);
    resetForNewFile();
  }

  async function trySampleData() {
    switchDatasetType("femto");
    const response = await fetch("/sample-data/femto-acc-sample.csv");
    const blob = await response.blob();
    const file = new File([blob], "femto-acc-sample.csv", { type: "text/csv" });
    setSelectedFile(file);
    void handleFemtoFile(file);
  }

  const activeState = datasetType === "femto" ? predictState : inspectState;
  const isBusy = activeState.status === "uploading" || activeState.status === "loading";

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-16">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Analyze Bearing Data</h1>
        <p className="mt-2 text-sm leading-relaxed text-foreground-muted">
          Upload a raw vibration acquisition from a supported bearing (FEMTO, headerless
          <code className="mx-1 rounded bg-surface px-1 py-0.5 text-xs">acc_*.csv</code>,
          6 columns, 25.6kHz) to get a Remaining Useful Life estimate.
        </p>
      </header>

      {!selectedFile && (
        <div
          className="flex flex-col gap-3 rounded-xl border-2 border-dashed border-surface-border bg-surface/50 p-10 text-center transition-colors hover:border-accent/50"
        >
          <label
            htmlFor="file-input"
            className="cursor-pointer text-sm text-foreground-muted"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const file = e.dataTransfer.files?.[0];
              if (file) setSelectedFile(file);
            }}
          >
            Drag and drop a <span className="font-medium">.csv</span> file here, or{" "}
            <span className="font-medium text-accent underline">choose a file</span>.
          </label>
          <input
            id="file-input"
            data-testid="file-input"
            type="file"
            accept=".csv"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) setSelectedFile(file);
              e.target.value = "";
            }}
            className="sr-only"
          />
          <button
            type="button"
            onClick={() => void trySampleData()}
            className="self-center text-xs text-foreground-muted underline hover:text-accent"
          >
            Try sample data
          </button>
        </div>
      )}

      {selectedFile && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-surface-border bg-surface p-4 shadow-sm ">
          <div className="text-sm">
            <p className="font-medium">{selectedFile.name}</p>
            <p className="text-foreground-muted">{formatBytes(selectedFile.size)}</p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={resetForNewFile}
              disabled={isBusy}
              className="rounded-lg border border-surface-border px-3 py-2 text-xs font-medium transition-colors hover:bg-surface disabled:opacity-50"
            >
              Remove
            </button>
            {activeState.status !== "ready" && (
              <button
                type="button"
                onClick={analyze}
                disabled={isBusy}
                className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white shadow-sm transition-colors hover:bg-accent/90 disabled:opacity-50"
              >
                {isBusy ? "Analyzing…" : datasetType === "femto" ? "Analyze Bearing" : "Inspect Dataset"}
              </button>
            )}
          </div>
        </div>
      )}

      {datasetType === "femto" && (
        <>
          {predictState.status === "uploading" && (
            <p className="text-sm">Uploading… {Math.round(predictState.progress * 100)}%</p>
          )}
          {predictState.status === "loading" && <p className="text-sm">Extracting features and predicting…</p>}

          {predictState.status === "error" && predictState.suppressed && (
            <>
              <SuppressedResultNotice detail={predictState.error} />
              <ExplainResult
                result={{
                  applicability_level: "LOW",
                  compatibility: "RETRAIN_REQUIRED",
                  applicability_reasons: [predictState.error],
                }}
              />
            </>
          )}

          {predictState.status === "error" && !predictState.suppressed && (
            <div className="flex flex-col gap-2 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
              <p>{predictState.error}</p>
              {predictState.retryable ? (
                <button
                  type="button"
                  onClick={predictState.retry}
                  className="self-start rounded border border-red-400 px-2 py-1 text-xs font-medium"
                >
                  Retry
                </button>
              ) : (
                <p className="text-xs text-danger">
                  This file won&apos;t succeed on retry as-is — use &quot;Remove&quot; above and choose a
                  different file.
                </p>
              )}
            </div>
          )}

          {predictState.status === "ready" && (
            <div
              className={`flex flex-col gap-4 rounded-xl border p-6 shadow-sm ${
                predictState.data.compatibility === "FULLY_SUPPORTED" &&
                predictState.data.applicability_level === "HIGH"
                  ? "border-green-300 bg-green-50 dark:border-green-900 dark:bg-green-950"
                  : "border-caution/30 bg-caution/10"
              }`}
            >
              <div>
                <p className="text-sm text-foreground-muted">Predicted Remaining Useful Life</p>
                <p className="text-4xl font-semibold tracking-tight">
                  {predictState.data.rul_hours.toFixed(2)} hours
                </p>
                <p className="mt-1 text-xs text-foreground-muted">
                  ({predictState.data.rul_seconds.toFixed(0)} s) — model: {predictState.data.model_name}
                </p>
              </div>
              <ApplicabilityNote result={predictState.data} />
              <p className="text-xs leading-relaxed text-foreground-muted">
                {applicabilityInterpretation(predictState.data.applicability_level)}
              </p>
              {selectedFile && (
                <SignalAndFeatures key={`${selectedFile.name}-${selectedFile.size}`} file={selectedFile} />
              )}
              <ExplainResult result={predictState.data} />
              <button
                type="button"
                onClick={resetForNewFile}
                className="self-start rounded-lg border border-surface-border bg-surface px-3 py-2 text-xs font-medium transition-colors hover:bg-background"
              >
                Analyze another file
              </button>
            </div>
          )}
        </>
      )}

      {datasetType === "generic" && (
        <>
          {inspectState.status === "uploading" && (
            <p className="text-sm">Uploading… {Math.round(inspectState.progress * 100)}%</p>
          )}
          {inspectState.status === "loading" && <p className="text-sm">Inspecting…</p>}

          {inspectState.status === "error" && (
            <div className="flex flex-col gap-2 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
              <p>{inspectState.error}</p>
              {inspectState.retryable ? (
                <button
                  type="button"
                  onClick={inspectState.retry}
                  className="self-start rounded border border-red-400 px-2 py-1 text-xs font-medium"
                >
                  Retry
                </button>
              ) : (
                <p className="text-xs text-danger">
                  This file won&apos;t succeed on retry as-is — use &quot;Remove&quot; above and choose a
                  different file.
                </p>
              )}
            </div>
          )}

          {inspectState.status === "ready" && (
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-3">
                <span className={`rounded-full px-3 py-1 text-xs font-medium ${BADGE[inspectState.data.compatibility]}`}>
                  {inspectState.data.compatibility.replace(/_/g, " ")}
                </span>
                <span className="text-sm text-foreground-muted">{inspectState.data.profile.file}</span>
              </div>

              {inspectState.data.reasons.length > 0 && (
                <ul className="list-inside list-disc text-sm text-foreground-muted">
                  {inspectState.data.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              )}

              {inspectState.data.profile.columns && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="text-foreground-muted">
                      <tr>
                        <th className="py-1 pr-3">Column</th>
                        <th className="py-1 pr-3">Mapped to</th>
                        <th className="py-1 pr-3">Confidence</th>
                        <th className="py-1 pr-3">Missing %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {inspectState.data.profile.columns.map((c) => (
                        <tr key={c.name} className="border-t border-surface-border  ">
                          <td className="py-1 pr-3 font-mono">{c.name}</td>
                          <td className="py-1 pr-3">{c.canonical ?? "—"}</td>
                          <td className="py-1 pr-3">{c.confidence}</td>
                          <td className="py-1 pr-3">{(c.nan_fraction * 100).toFixed(1)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {inspectState.data.profile.warnings.length > 0 && (
                <div className="rounded-lg border border-caution/30 bg-caution/10 p-4 text-xs text-caution">
                  {inspectState.data.profile.warnings.map((w) => (
                    <p key={w}>{w}</p>
                  ))}
                </div>
              )}

              <button
                type="button"
                onClick={resetForNewFile}
                className="self-start rounded-lg border border-surface-border px-3 py-2 text-xs font-medium"
              >
                Inspect another file
              </button>
            </div>
          )}
        </>
      )}

      <details
        className="rounded-lg border border-surface-border p-4  "
        open={advancedOpen}
        onToggle={(e) => setAdvancedOpen((e.target as HTMLDetailsElement).open)}
      >
        <summary className="cursor-pointer text-sm font-medium text-foreground-muted">
          Advanced: inspect another (non-FEMTO) dataset
        </summary>
        <div className="mt-3 flex flex-col gap-3 text-sm text-foreground-muted">
          <p>
            Inspects a file&apos;s structure (delimiter, header, column meanings) and reports
            compatibility — it does not run a prediction. Switching here clears any in-progress
            FEMTO analysis.
          </p>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="dataset-type"
              checked={datasetType === "generic"}
              onChange={() => switchDatasetType("generic")}
            />
            Use the dataset-inspection workflow for my next file
          </label>
          {datasetType === "generic" && (
            <div className="flex flex-col gap-3 rounded-lg border border-surface-border p-3  ">
              <label className="flex flex-col gap-1 text-xs">
                Declared sampling rate (Hz) — optional, only used if the file has no regular
                timestamps in seconds.
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={declaredSamplingRateHz}
                  onChange={(e) => setDeclaredSamplingRateHz(e.target.value)}
                  placeholder="e.g. 25600"
                  className="rounded border border-surface-border bg-surface px-2 py-1 text-xs"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs">
                Declared units — optional
                <input
                  type="text"
                  value={declaredUnits}
                  onChange={(e) => setDeclaredUnits(e.target.value)}
                  placeholder="e.g. g, m/s^2"
                  className="rounded border border-surface-border bg-surface px-2 py-1 text-xs"
                />
              </label>
              <button
                type="button"
                onClick={() => switchDatasetType("femto")}
                className="self-start text-xs underline"
              >
                Back to FEMTO analysis
              </button>
            </div>
          )}
        </div>
      </details>
    </main>
  );
}
