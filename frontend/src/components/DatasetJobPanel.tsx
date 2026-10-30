"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  DatasetJob,
  DatasetJobResult,
  JOB_TERMINAL_STATES,
  JobPlan,
  JobStageName,
  cancelDatasetJob,
  createDatasetJob,
  getDatasetJob,
  getDatasetJobAllFiles,
  getDatasetJobFileOffset,
  getDatasetJobResult,
  planDatasetJob,
  startDatasetJob,
  uploadDatasetJobChunk,
} from "@/lib/api";
import { RoutingBundleResult } from "@/components/RoutingBundleResult";
import { MappingForm } from "@/components/MappingForm";
import { buildReportHtml, downloadText } from "@/lib/report";
import { HealthQualityCard } from "@/components/HealthQualityCard";

/** A selected file plus the name the server should see: the folder-relative
 * path for a folder upload, otherwise the file name. */
export interface PickedFile {
  file: File;
  name: string;
}

const CHUNK_BYTES = 16 * 1024 * 1024;
const MAX_CHUNK_RETRIES = 6;
const POLL_MS = 2000;
export const LAST_JOB_KEY = "rulguard:lastDatasetJob";

const KIND_LABEL: Record<JobPlan["kind"], string> = {
  zip: "ZIP archive",
  "7z": "7-Zip archive",
  rar: "RAR archive",
  multipart_rar: "multi-part RAR archive",
  multipart_7z: "multi-part 7-Zip archive",
  files: "folder / loose files",
};

const STAGE_LABEL: Record<JobStageName, string> = {
  upload: "Uploading",
  check: "Checking archive parts",
  extract: "Extracting",
  detect: "Detecting the dataset",
  process: "Processing bearings",
};

const STAGE_PILL: Record<string, string> = {
  pending: "bg-surface text-foreground-muted border border-surface-border",
  running: "bg-accent/15 text-accent",
  done: "bg-success/15 text-success",
  skipped: "bg-surface text-foreground-muted border border-surface-border",
  partial: "bg-caution/15 text-caution",
  failed: "bg-danger/15 text-danger",
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

function normalize(name: string): string {
  return name.replace(/\\/g, "/").replace(/^\.\//, "");
}

function baseName(name: string): string {
  const parts = normalize(name).split("/");
  return parts[parts.length - 1];
}

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.detail : "Something went wrong. Please try again.";
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function rememberJob(id: string | null) {
  try {
    if (id) localStorage.setItem(LAST_JOB_KEY, id);
    else localStorage.removeItem(LAST_JOB_KEY);
  } catch {
    /* storage unavailable: the job id stays in the URL */
  }
  const url = new URL(window.location.href);
  if (id) url.searchParams.set("job", id);
  else url.searchParams.delete("job");
  window.history.replaceState(null, "", url.toString());
}

/** Map every server-side file (in the server's upload order) to the picked
 * File with the same name and size; null where it was not (re-)selected.
 * Archive parts are stored by base name; folder files by relative path only
 * (base names repeat across bearings, e.g. every bearing has a 1.csv). */
function matchFiles(job: DatasetJob, picked: PickedFile[]): Array<File | null> {
  const byName = new Map<string, File>();
  for (const p of picked) {
    byName.set(normalize(p.name), p.file);
    if (job.plan.kind !== "files" && !byName.has(baseName(p.name))) byName.set(baseName(p.name), p.file);
  }
  return job.files.map((f) => {
    const file = byName.get(f.name);
    return file && file.size === f.size ? file : null;
  });
}

type Phase =
  | { kind: "planning" }
  | { kind: "plan"; plan: JobPlan }
  | { kind: "plan-error"; error: string }
  | { kind: "uploading"; job: DatasetJob; sent: number; total: number }
  | { kind: "needs-files"; job: DatasetJob }
  | { kind: "server"; job: DatasetJob }
  | { kind: "error"; error: string };

export function DatasetJobPanel({
  picked,
  resumeJobId,
  onReset,
  onPick,
  onAdd,
}: {
  picked: PickedFile[] | null;
  resumeJobId: string | null;
  onReset: () => void;
  onPick: (files: File[], fromFolder: boolean) => void;
  /** Add files (e.g. the missing archive parts) to the current selection. */
  onAdd: (files: File[]) => void;
}) {
  const [phase, setPhase] = useState<Phase>({ kind: "planning" });
  const [result, setResult] = useState<DatasetJobResult | null>(null);
  const stopped = useRef(false);
  const jobRef = useRef<DatasetJob | null>(null);

  const poll = useCallback(async (id: string) => {
    while (!stopped.current) {
      let job: DatasetJob;
      try {
        job = await getDatasetJob(id);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          rememberJob(null);
          setPhase({ kind: "error", error: "This analysis job no longer exists (results are kept for 7 days)." });
          return;
        }
        await sleep(POLL_MS * 2); // transient: keep polling
        continue;
      }
      jobRef.current = job;
      setPhase({ kind: "server", job });
      if (job.state === "needs_mapping") return; // resumes after the user confirms the mapping
      if (JOB_TERMINAL_STATES.includes(job.state)) {
        if (job.has_result) {
          try {
            setResult(await getDatasetJobResult(id));
          } catch (err) {
            setPhase({ kind: "error", error: errorText(err) });
          }
        }
        return;
      }
      await sleep(POLL_MS);
    }
  }, []);

  const runUpload = useCallback(
    async (job: DatasetJob, files: Array<File | null>) => {
      try {
        const total = job.files.reduce((s, f) => s + f.size, 0);
        let sent = job.files.reduce((s, f) => s + f.received, 0);
        setPhase({ kind: "uploading", job, sent, total });
        for (let i = 0; i < job.files.length; i++) {
          const file = files[i];
          if (!file) throw new ApiError(400, `${job.files[i].name} is missing from the selection.`, false);
          let offset = job.files[i].received;
          let failures = 0;
          while (offset < file.size) {
            if (stopped.current) return;
            const chunk = file.slice(offset, Math.min(offset + CHUNK_BYTES, file.size));
            try {
              const received = await uploadDatasetJobChunk(job.id, i, offset, chunk);
              sent += received - offset;
              offset = received;
              failures = 0;
              setPhase({ kind: "uploading", job, sent, total });
            } catch (err) {
              const transient = !(err instanceof ApiError) || err.status === 0 || err.status >= 500;
              const resync = err instanceof ApiError && err.code === "OFFSET_MISMATCH";
              if (!(transient || resync) || ++failures > MAX_CHUNK_RETRIES) throw err;
              await sleep(Math.min(2 ** failures * 1000, 30000));
              const server = await getDatasetJobFileOffset(job.id, i);
              sent += server - offset;
              offset = server;
            }
          }
        }
        await startDatasetJob(job.id);
        void poll(job.id);
      } catch (err) {
        if (!stopped.current) setPhase({ kind: "error", error: errorText(err) });
      }
    },
    [poll]
  );

  // Resume an existing job (from the URL or this browser's last job).
  useEffect(() => {
    if (!resumeJobId) return;
    stopped.current = false;
    void (async () => {
      try {
        const job = await getDatasetJob(resumeJobId);
        jobRef.current = job;
        if (job.state !== "awaiting_upload") {
          void poll(job.id);
          return;
        }
        const full = await getDatasetJobAllFiles(job.id);
        const files = picked ? matchFiles(full, picked) : [];
        if (picked && files.every((f) => f !== null)) void runUpload(full, files);
        else setPhase({ kind: "needs-files", job: full });
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) rememberJob(null);
        setPhase({ kind: "error", error: errorText(err) });
      }
    })();
    return () => {
      stopped.current = true;
    };
  }, [resumeJobId, picked, poll, runUpload]);

  // New selection: dry-run plan first, so the user sees what will happen.
  useEffect(() => {
    if (resumeJobId || !picked) return;
    stopped.current = false; // the page re-mounts this panel (key) for every new selection
    planDatasetJob(picked.map((p) => ({ name: normalize(p.name), size: p.file.size })))
      .then((plan) => setPhase({ kind: "plan", plan }))
      .catch((err) => setPhase({ kind: "plan-error", error: errorText(err) }));
    return () => {
      stopped.current = true;
    };
  }, [picked, resumeJobId]);

  async function begin() {
    if (!picked) return;
    try {
      const job = await createDatasetJob(picked.map((p) => ({ name: normalize(p.name), size: p.file.size })));
      jobRef.current = job;
      rememberJob(job.id);
      void runUpload(job, matchFiles(job, picked));
    } catch (err) {
      setPhase({ kind: "plan-error", error: errorText(err) });
    }
  }

  async function cancel() {
    stopped.current = true;
    const job = jobRef.current;
    if (job) {
      try {
        await cancelDatasetJob(job.id);
      } catch {
        /* already gone */
      }
    }
    rememberJob(null);
    onReset();
  }

  function startOver() {
    stopped.current = true;
    rememberJob(null);
    onReset();
  }

  return (
    <section className="flex flex-col gap-4" aria-live="polite">
      {phase.kind === "planning" && <p className="text-sm text-foreground-muted">Checking your selection…</p>}

      {phase.kind === "plan-error" && (
        <div className="flex flex-col gap-2 rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm text-danger">
          <p className="font-medium">This selection can&apos;t be analyzed as it is.</p>
          <p>{phase.error}</p>
          <button type="button" onClick={startOver} className="self-start rounded border border-danger/50 px-2 py-1 text-xs font-medium">
            Choose different files
          </button>
        </div>
      )}

      {phase.kind === "plan" && picked && (
        <PlanSummary
          plan={phase.plan}
          count={picked.length}
          onStart={() => void begin()}
          onCancel={startOver}
          onAdd={onAdd}
        />
      )}

      {phase.kind === "uploading" && (
        <div className="flex flex-col gap-3 rounded-xl border border-surface-border bg-surface p-5">
          <StageList
            job={{
              ...phase.job,
              stages: { ...phase.job.stages, upload: { status: "running", done: phase.sent, total: phase.total, detail: "" } },
            }}
          />
          <p className="text-xs text-foreground-muted">
            Keep this page open until the upload finishes. If the connection drops, select the same files again and the
            upload continues where it stopped.
          </p>
          <button type="button" onClick={() => void cancel()} className="self-start rounded-lg border border-surface-border px-3 py-2 text-xs font-medium">
            Cancel and delete upload
          </button>
        </div>
      )}

      {phase.kind === "needs-files" && (
        <div className="flex flex-col gap-2 rounded-lg border border-caution/40 bg-caution/10 p-4 text-sm text-caution">
          <p className="font-medium">The upload was interrupted.</p>
          <p>
            {formatBytes(phase.job.files.reduce((s, f) => s + f.received, 0))} of {formatBytes(phase.job.plan.total_bytes)}{" "}
            arrived. Select the same {phase.job.file_count.toLocaleString()} file(s) again to continue from where it
            stopped.
          </p>
          <div className="flex gap-3 text-xs">
            <label className="cursor-pointer underline">
              {phase.job.plan.kind === "files" ? "Choose the same folder" : "Choose the same files"}
              <input
                type="file"
                multiple
                className="sr-only"
                {...(phase.job.plan.kind === "files" ? ({ webkitdirectory: "" } as Record<string, string>) : {})}
                onChange={(e) => {
                  onPick(Array.from(e.target.files ?? []), phase.job.plan.kind === "files");
                  e.target.value = "";
                }}
              />
            </label>
          </div>
          <button type="button" onClick={() => void cancel()} className="self-start rounded border border-caution/50 px-2 py-1 text-xs font-medium">
            Discard this upload
          </button>
        </div>
      )}

      {phase.kind === "server" && (
        <>
          <JobStatusBanner job={phase.job} />
          <div className="rounded-xl border border-surface-border bg-surface p-5">
            <StageList job={phase.job} />
            {!JOB_TERMINAL_STATES.includes(phase.job.state) && (
              <p className="mt-3 text-xs text-foreground-muted">
                Processing runs on the server: you can close this page and come back to this address (or to the upload
                page in the same browser) for the result.
              </p>
            )}
          </div>
          {phase.job.state === "needs_mapping" && phase.job.mapping_proposal && (
            <MappingForm
              key={phase.job.id}
              job={phase.job}
              onSubmitted={(job) => {
                setPhase({ kind: "server", job });
                void poll(job.id);
              }}
            />
          )}
          {phase.job.validation && <ValidationNote validation={phase.job.validation} />}
          {phase.job.summary && <SummaryCard job={phase.job} />}
          {result && result.outcome === "analyzed" && (
            <>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => downloadText(buildReportHtml(phase.job, result), `rulguard-report-${phase.job.id}.html`, "text/html")}
                  className="rounded-full border-2 border-surface-border bg-mint px-4 py-1.5 font-display text-sm font-bold"
                >
                  Download analysis report
                </button>
                <button
                  type="button"
                  onClick={() => downloadText(JSON.stringify(result, null, 2), `rulguard-results-${phase.job.id}.json`, "application/json")}
                  className="rounded-full border-2 border-surface-border bg-surface px-4 py-1.5 text-sm font-semibold hover:bg-mint"
                >
                  Download raw results (JSON)
                </button>
              </div>
              {result.health_quality && <HealthQualityCard quality={result.health_quality} />}
              <BearingTable result={result} incomplete={incompleteOf(phase.job)} />
              <RoutingBundleResult
                data={result}
                incompleteBearings={incompleteOf(phase.job)}
                notValidated={phase.job.validation?.status === "not_validated"}
                signalNote="Raw signal is not kept: uploaded and extracted files are deleted as soon as processing ends. Only these derived results remain, for 7 days."
              />
            </>
          )}
          {JOB_TERMINAL_STATES.includes(phase.job.state) ? (
            <button type="button" onClick={startOver} className="self-start rounded-lg border border-surface-border px-3 py-2 text-xs font-medium">
              Analyze another dataset
            </button>
          ) : (
            <button type="button" onClick={() => void cancel()} className="self-start rounded-lg border border-surface-border px-3 py-2 text-xs font-medium">
              Cancel processing
            </button>
          )}
        </>
      )}

      {phase.kind === "error" && (
        <div className="flex flex-col gap-2 rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm text-danger">
          <p>{phase.error}</p>
          <button type="button" onClick={startOver} className="self-start rounded border border-danger/50 px-2 py-1 text-xs font-medium">
            Start over
          </button>
        </div>
      )}
    </section>
  );
}

function PlanSummary({
  plan,
  count,
  onStart,
  onCancel,
  onAdd,
}: {
  plan: JobPlan;
  count: number;
  onStart: () => void;
  onCancel: () => void;
  onAdd: (files: File[]) => void;
}) {
  const archive = plan.kind !== "files";
  const missing = plan.missing ?? [];
  const partial = missing.length > 0;
  const multipart = plan.kind.startsWith("multipart");
  const selectedParts = plan.files?.map((f) => f.name) ?? [];
  const expected = plan.expected_parts ?? selectedParts.length;
  const addInput = (label: string, primary: boolean) => (
    <label
      className={`cursor-pointer rounded-lg px-4 py-2 text-xs font-medium ${
        primary ? "bg-accent text-white shadow-sm hover:bg-accent/90" : "border border-surface-border"
      }`}
    >
      {label}
      <input
        type="file"
        multiple
        accept=".rar,.7z,.001,.002,.003,.004,.005,.006,.007,.008,.009"
        className="sr-only"
        onChange={(e) => {
          onAdd(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
    </label>
  );
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-surface-border bg-surface p-5 text-sm">
      <h2 className="text-base font-semibold">What will happen</h2>
      <p>
        {count.toLocaleString()} file{count === 1 ? "" : "s"}, {formatBytes(plan.total_bytes)}, recognised as a{" "}
        <span className="font-medium">{KIND_LABEL[plan.kind]}</span>
        {multipart && plan.first && !partial && (
          <>
            {" "}
            with every part present; extraction starts from <span className="font-mono">{plan.first}</span>
          </>
        )}
        .
      </p>
      {multipart && (
        <div
          className={`rounded-lg border p-3 ${
            partial ? "border-caution/40 bg-caution/10 text-caution" : "border-success/40 bg-success/10 text-success"
          }`}
        >
          <p className="font-medium">
            {partial
              ? `${selectedParts.length} of ${expected} parts selected: ${missing.length} missing`
              : `${selectedParts.length}/${expected} parts selected ✓`}
          </p>
          <ul className="mt-2 grid grid-cols-1 gap-x-4 gap-y-0.5 font-mono text-xs sm:grid-cols-2">
            {[...selectedParts.map((n) => [n, true] as const), ...missing.map((n) => [n, false] as const)]
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([name, ok]) => (
                <li key={name}>
                  {ok ? "✓" : "✗"} {name}
                  {!ok && " (missing)"}
                </li>
              ))}
          </ul>
        </div>
      )}
      <ol className="list-inside list-decimal text-foreground-muted">
        <li>Upload to the RULGuard server in resumable 16 MB pieces.</li>
        {archive && <li>Check every part against the archive headers and safety-check the contents.</li>}
        {archive && <li>Extract on the server, then delete the uploaded archive.</li>}
        <li>Detect the dataset format and every bearing run in it.</li>
        <li>
          Extract features from every recording, then compute the health indicator, degradation stage and applicability
          per bearing. RUL is shown only where a model has measured skill on this dataset.
        </li>
        <li>Delete the raw data. Results are kept for 7 days.</li>
      </ol>
      {plan.notes.map((n) => (
        <p key={n} className="rounded-lg border border-caution/30 bg-caution/10 p-3 text-xs text-caution">
          {n}
        </p>
      ))}
      <div className="flex flex-wrap gap-2">
        {partial ? (
          <>
            {addInput("Add the missing parts", true)}
            <button type="button" onClick={onStart} className="rounded-lg border border-surface-border px-4 py-2 text-xs font-medium">
              Analyze only these parts (partial)
            </button>
          </>
        ) : (
          <>
            <button type="button" onClick={onStart} className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white shadow-sm hover:bg-accent/90">
              Upload and analyze
            </button>
            {multipart && addInput("Add more parts", false)}
          </>
        )}
        <button type="button" onClick={onCancel} className="rounded-lg border border-surface-border px-3 py-2 text-xs font-medium">
          Remove
        </button>
      </div>
    </div>
  );
}

function StageList({ job }: { job: DatasetJob }) {
  const order: JobStageName[] = ["upload", "check", "extract", "detect", "process"];
  return (
    <ol className="flex flex-col gap-3">
      {order.map((name) => {
        const s = job.stages[name];
        const pct = s.total > 0 ? Math.min(100, Math.round((s.done / s.total) * 100)) : null;
        const bytes = name === "upload" || name === "extract";
        const counts =
          s.status === "running" && s.total > 0
            ? bytes
              ? `${formatBytes(s.done)} of ${formatBytes(s.total)}`
              : name === "process"
                ? `${s.done.toLocaleString()} of ~${s.total.toLocaleString()} files`
                : `${s.done} of ${s.total}`
            : "";
        return (
          <li key={name} className="flex flex-col gap-1">
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="font-medium">{STAGE_LABEL[name]}</span>
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STAGE_PILL[s.status] ?? STAGE_PILL.pending}`}>
                {s.status === "running" && pct !== null ? `${pct}%` : s.status}
              </span>
            </div>
            {s.status === "running" && pct !== null && (
              <div
                className="h-1.5 w-full overflow-hidden rounded-full bg-background"
                role="progressbar"
                aria-label={STAGE_LABEL[name]}
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div className="h-full bg-accent transition-[width]" style={{ width: `${pct}%` }} />
              </div>
            )}
            {(counts || s.detail) && (
              <p className="text-xs text-foreground-muted">{[counts, s.detail].filter(Boolean).join(" · ")}</p>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function incompleteOf(job: DatasetJob): string[] {
  return job.summary?.partial_set?.incomplete_bearings.map((b) => b.bearing) ?? [];
}

function JobStatusBanner({ job }: { job: DatasetJob }) {
  const tone =
    job.state === "completed" && job.summary?.bearings_processed
      ? "border-success/40 bg-success/10 text-success"
      : job.state === "failed" || job.state === "cancelled"
        ? "border-danger/40 bg-danger/10 text-danger"
        : job.state === "partial" || job.state === "completed"
          ? "border-caution/40 bg-caution/10 text-caution"
          : "border-surface-border bg-surface text-foreground";
  const ps = job.summary?.partial_set;
  const headline =
    ps && JOB_TERMINAL_STATES.includes(job.state) && job.state !== "failed" && job.state !== "cancelled"
      ? `Partial analysis completed: ${job.summary!.bearings_processed} bearing run(s) found in ${ps.uploaded.length} of ${
          ps.uploaded.length + ps.missing.length
        } archive parts.`
      : null;
  return (
    <div className={`rounded-lg border p-4 text-sm ${ps && headline ? "border-caution/40 bg-caution/10 text-caution" : tone}`}>
      {headline && <p className="text-base font-semibold">{headline}</p>}
      <p className={headline ? "mt-1" : "font-medium"}>{job.message}</p>
      <p className="mt-1 text-xs opacity-80">Job {job.id}</p>
    </div>
  );
}

function ValidationNote({ validation }: { validation: NonNullable<DatasetJob["validation"]> }) {
  const ok = validation.status === "validated";
  return (
    <div className={`rounded-lg border p-4 text-sm ${ok ? "border-surface-border bg-surface" : "border-caution/40 bg-caution/10 text-caution"}`}>
      <p className="font-medium">{ok ? "RUL validation on this dataset" : "Not validated for RUL on this dataset"}</p>
      <p className="mt-1">{validation.note}</p>
    </div>
  );
}

function SummaryCard({ job }: { job: DatasetJob }) {
  const s = job.summary!;
  const cells: Array<[string, number]> = [
    ["Files found", s.files_found],
    ["Files processed", s.files_processed],
    ["Files skipped", s.files_skipped],
    ["Files failed", s.files_failed],
    ["Bearing runs found", s.bearings_found],
    ["Runs processed", s.bearings_processed],
    ["Runs failed", s.bearings_failed],
  ];
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-surface-border bg-surface p-5 text-sm">
      <h2 className="text-base font-semibold">Processing summary{s.display_name ? `: ${s.display_name}` : ""}</h2>
      <p
        className={`rounded-lg border px-3 py-2 text-xs font-medium ${
          s.partial_set ? "border-caution/40 bg-caution/10 text-caution" : "border-success/40 bg-success/10 text-success"
        }`}
      >
        {[
          s.display_name,
          s.partial_set && `Parts ${s.partial_set.uploaded.length}/${s.partial_set.uploaded.length + s.partial_set.missing.length}`,
          `Bearings ${s.bearings_processed}/${s.bearings_found}`,
          `Files ${s.files_processed.toLocaleString()}`,
          s.partial_set ? "Partial" : s.bearings_failed === 0 && s.files_failed === 0 ? "Complete ✓" : "Completed with errors",
        ]
          .filter(Boolean)
          .join("  |  ")}
      </p>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-4">
        {cells.map(([label, value]) => (
          <div key={label} className="flex flex-col">
            <dt className="text-xs text-foreground-muted">{label}</dt>
            <dd className="tabular-nums">{value.toLocaleString()}</dd>
          </div>
        ))}
      </dl>
      {s.failed.length > 0 && (
        <div className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-xs text-danger">
          <p className="font-medium">Bearing runs that could not be processed (not included in the results):</p>
          <ul className="mt-1 list-inside list-disc">
            {s.failed.map((f) => (
              <li key={f.bearing}>
                <span className="font-mono">{f.bearing}</span> ({f.files} files): {f.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {s.partial_set && (
        <div className="rounded-lg border border-caution/40 bg-caution/10 p-3 text-xs text-caution">
          <p className="font-medium">
            Partial dataset: {s.partial_set.uploaded.length} of{" "}
            {s.partial_set.uploaded.length + s.partial_set.missing.length} archive parts uploaded.
          </p>
          <p className="mt-1">
            Not included (not uploaded): <span className="font-mono">{s.partial_set.missing.join(", ")}</span>. Upload every
            part together to analyse the whole dataset.
          </p>
          {s.partial_set.incomplete_bearings.length > 0 && (
            <ul className="mt-1 list-inside list-disc">
              {s.partial_set.incomplete_bearings.map((b) => (
                <li key={b.bearing}>
                  <span className="font-mono">{b.bearing}</span> is incomplete: {b.reason}. Its health indicator uses
                  the earliest uploaded recordings as the reference, and it has no end-of-life label.
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {s.skipped.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer text-foreground-muted">
            {s.files_skipped.toLocaleString()} skipped file{s.files_skipped === 1 ? "" : "s"} and why
          </summary>
          <ul className="mt-2 flex flex-col gap-1">
            {s.skipped.map((f) => (
              <li key={f.path}>
                <span className="font-mono">{f.path}</span>: {f.reason}
              </li>
            ))}
            {s.files_skipped > s.skipped.length && <li>and {s.files_skipped - s.skipped.length} more</li>}
          </ul>
        </details>
      )}
    </div>
  );
}

function BearingTable({ result, incomplete }: { result: DatasetJobResult; incomplete: string[] }) {
  const rows = Object.keys(result.decisions)
    .sort()
    .map((id) => {
      const t = result.trajectories?.[id] ?? [];
      const last = t[t.length - 1];
      return { id, n: t.length, hi: last?.health_indicator, stage: last?.stage, status: result.decisions[id].current.status };
    });
  return (
    <div className="overflow-x-auto rounded-xl border border-surface-border bg-surface p-5">
      <h2 className="mb-2 text-base font-semibold">Per bearing, at the last recording</h2>
      <table className="w-full text-left text-xs">
        <thead className="text-foreground-muted">
          <tr>
            <th className="py-1 pr-3">Bearing</th>
            <th className="py-1 pr-3">Recordings</th>
            <th className="py-1 pr-3">Health indicator</th>
            <th className="py-1 pr-3">Stage</th>
            <th className="py-1 pr-3">RUL</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-surface-border">
              <td className="py-1 pr-3 font-mono">{r.id}</td>
              <td className="py-1 pr-3 tabular-nums">{r.n.toLocaleString()}</td>
              <td className="py-1 pr-3 tabular-nums">{r.hi != null ? r.hi.toFixed(3) : "—"}</td>
              <td className="py-1 pr-3">
                {r.stage ?? "—"}
                {incomplete.includes(r.id) && <span className="text-caution"> (partial trajectory)</span>}
              </td>
              <td className="py-1 pr-3">
                {r.status === "RUL_SUPPRESSED" ? "withheld" : r.status === "RUL_EXPERIMENTAL" ? "experimental" : "available"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
