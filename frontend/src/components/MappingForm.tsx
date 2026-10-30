"use client";

import { useState } from "react";
import { ApiError, DatasetJob, MappingProposal, MappingRole, submitDatasetJobMapping } from "@/lib/api";

const ROLE_LABELS: Record<MappingRole, string> = {
  vibration_x: "Vibration (first axis)",
  vibration_y: "Vibration (second axis)",
  temperature_bearing: "Bearing temperature",
  temperature_ambient: "Ambient temperature",
};

const CONFIDENCE_TEXT: Record<string, string> = {
  high: "from the column name",
  low: "from the column name, please check",
  guess: "guessed, please check",
};

/** A custom-format dataset is not processed until the user confirms how to read it:
 * which columns are vibration, the sampling rate, and the time between recordings. */
export function MappingForm({ job, onSubmitted }: { job: DatasetJob; onSubmitted: (job: DatasetJob) => void }) {
  const p = job.mapping_proposal as MappingProposal;
  const [roles, setRoles] = useState<Record<string, string>>(
    Object.fromEntries(p.columns.map((c) => [c.name, c.role ?? ""]))
  );
  const [rate, setRate] = useState(p.sampling_rate_hz ? String(Math.round(p.sampling_rate_hz)) : "");
  const [interval, setIntervalS] = useState("");
  const [ranToFailure, setRanToFailure] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const chosen = Object.values(roles).filter(Boolean);
  const vibration = chosen.filter((r) => r.startsWith("vibration"));
  const ready =
    vibration.length > 0 &&
    new Set(chosen).size === chosen.length &&
    Number(rate) > 0 &&
    (!p.needs_interval || Number(interval) > 0);
  const files = p.runs.reduce((s, r) => s + r.files, 0);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const columns = Object.fromEntries(Object.entries(roles).filter(([, r]) => r));
      onSubmitted(
        await submitDatasetJobMapping(job.id, {
          columns,
          sampling_rate_hz: Number(rate),
          recording_interval_s: p.needs_interval ? Number(interval) : null,
          ran_to_failure: ranToFailure,
        })
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-4 rounded-xl border border-surface-border bg-surface p-5 text-sm">
      <div>
        <h2 className="text-base font-semibold">Tell RULGuard how to read this dataset</h2>
        <p className="mt-1 text-foreground-muted">
          This isn&apos;t a dataset RULGuard knows, so nothing has been analysed yet. Found {p.runs.length} bearing
          run(s) in {files.toLocaleString()} file(s): one run per folder, recordings in file-name order. Columns below
          are from <span className="font-mono">{p.sample_file}</span> ({p.rows_per_file.toLocaleString()} rows).
        </p>
      </div>

      <table className="w-full text-left text-xs">
        <thead className="text-foreground-muted">
          <tr>
            <th className="py-1 pr-3">Column</th>
            <th className="py-1 pr-3">What it measures</th>
          </tr>
        </thead>
        <tbody>
          {p.columns.map((c) => (
            <tr key={c.name} className="border-t border-surface-border">
              <td className="py-1.5 pr-3 font-mono">{p.has_header ? c.name : `column ${Number(c.name) + 1}`}</td>
              <td className="py-1.5 pr-3">
                {c.usable ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <select
                      aria-label={`Role of ${c.name}`}
                      value={roles[c.name]}
                      onChange={(e) => setRoles({ ...roles, [c.name]: e.target.value })}
                      className="rounded-md border border-surface-border bg-background px-2 py-1"
                    >
                      <option value="">Not used</option>
                      {p.roles.map((r) => (
                        <option key={r} value={r}>
                          {ROLE_LABELS[r]}
                        </option>
                      ))}
                    </select>
                    {c.role && roles[c.name] === c.role && CONFIDENCE_TEXT[c.confidence] && (
                      <span className={c.confidence === "high" ? "text-foreground-muted" : "text-caution"}>
                        {CONFIDENCE_TEXT[c.confidence]}
                      </span>
                    )}
                  </div>
                ) : (
                  <span className="text-foreground-muted">not numeric, can&apos;t be used</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 font-medium">
          Sampling rate (samples per second)
          <input
            type="number"
            min={1}
            step="any"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            placeholder="e.g. 25600"
            className="rounded-lg border border-surface-border bg-background px-3 py-2 font-normal"
          />
          <span className="text-xs font-normal text-foreground-muted">
            {p.sampling_rate_hz
              ? "Worked out from the file's time column."
              : "Required. Look it up in the dataset's documentation; it is never guessed."}
          </span>
        </label>
        {p.needs_interval && (
          <label className="flex flex-col gap-1 font-medium">
            Time between recordings (seconds)
            <input
              type="number"
              min={0}
              step="any"
              value={interval}
              onChange={(e) => setIntervalS(e.target.value)}
              placeholder="e.g. 600 for one file every 10 minutes"
              className="rounded-lg border border-surface-border bg-background px-3 py-2 font-normal"
            />
            <span className="text-xs font-normal text-foreground-muted">
              How often a new file was recorded. Sets the time axis of the health chart.
            </span>
          </label>
        )}
      </div>

      <label className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={ranToFailure}
          onChange={(e) => setRanToFailure(e.target.checked)}
          className="mt-1"
        />
        <span>
          <span className="font-medium">Every bearing ran until it failed</span>
          <span className="block text-xs text-foreground-muted">
            Tick only if each folder&apos;s last file was recorded at failure. RULGuard then learns remaining life from
            these bearings and tests it on each one in turn. With {p.runs.length < 3 ? "fewer than 3 bearings, as here," : "fewer than 3 bearings"} RUL is still withheld.
          </span>
        </span>
      </label>

      {p.warnings.length > 0 && (
        <ul className="list-inside list-disc text-xs text-caution">
          {p.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      {vibration.length === 0 && <p className="text-xs text-caution">Choose at least one vibration column.</p>}
      {new Set(chosen).size !== chosen.length && (
        <p className="text-xs text-caution">Each measurement can be chosen for one column only.</p>
      )}
      {error && <p className="text-xs text-danger">{error}</p>}

      <button
        type="submit"
        disabled={!ready || busy}
        className="self-start rounded-full border-2 border-surface-border bg-mint px-5 py-2 font-display text-sm font-bold disabled:opacity-60"
      >
        {busy ? "Starting…" : "Analyse with these settings"}
      </button>
    </form>
  );
}
