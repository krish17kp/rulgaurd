import { DatasetJob, DatasetJobResult, RoutingTrajectoryPoint } from "@/lib/api";
import { splitAtGaps } from "@/components/MultiSeriesChart";
import { modelName, withheldReason } from "@/components/RoutingBundleResult";

const esc = (s: unknown) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

const STATUS_TEXT: Record<string, string> = {
  RUL_SUPPRESSED: "withheld",
  RUL_EXPERIMENTAL: "experimental",
};

/** Health indicator over time as an inline SVG, broken where recordings are missing. */
function hiChart(t: RoutingTrajectoryPoint[]): string {
  const pts = t.map((p) => ({ x: p.elapsed_s / 3600, y: p.health_indicator ?? null }));
  const ys = pts.flatMap((p) => (p.y === null ? [] : [p.y]));
  if (ys.length < 2) return "<p class=muted>Not enough recordings for a trajectory.</p>";
  const W = 640, H = 150, L = 40, B = 20;
  const x0 = pts[0].x, x1 = pts[pts.length - 1].x;
  const y0 = Math.min(...ys), y1 = Math.max(...ys) === y0 ? y0 + 1 : Math.max(...ys);
  const sx = (x: number) => L + ((x - x0) / (x1 - x0 || 1)) * (W - L - 5);
  const sy = (y: number) => 5 + (1 - (y - y0) / (y1 - y0)) * (H - B - 5);
  const { segments, gaps } = splitAtGaps(pts);
  // ponytail: stride downsample per segment, keeps the file small for 10k-recording runs.
  const lines = segments.map((s) => {
    const step = Math.max(1, Math.ceil(s.length / 300));
    const d = s.filter((_, i) => i % step === 0 || i === s.length - 1).map((p) => `${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`);
    return `<polyline points="${d.join(" ")}" fill="none" stroke="#2563eb" stroke-width="1.5"/>`;
  });
  const shades = gaps.map(([a, b]) => `<rect x="${sx(a)}" y="5" width="${sx(b) - sx(a)}" height="${H - B - 5}" fill="#f59e0b22"/>`);
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Health indicator over time">
${shades.join("")}${lines.join("")}
<line x1="${L}" y1="${H - B}" x2="${W - 5}" y2="${H - B}" stroke="#999"/>
<text x="${L}" y="${H - 5}" font-size="10">${x0.toFixed(1)} h</text>
<text x="${W - 5}" y="${H - 5}" font-size="10" text-anchor="end">${x1.toFixed(1)} h</text>
<text x="${L - 4}" y="12" font-size="10" text-anchor="end">${y1.toFixed(2)}</text>
<text x="${L - 4}" y="${H - B}" font-size="10" text-anchor="end">${y0.toFixed(2)}</text>
</svg>${gaps.length ? `<p class=muted>Shaded: no recordings.</p>` : ""}`;
}

/** A self-contained HTML report of one dataset job: what was uploaded, how complete it was,
 * each bearing's health trajectory and stage, and the RUL decision with its reason. It only
 * restates the numeric results the server returned. */
export function buildReportHtml(job: DatasetJob, result: DatasetJobResult): string {
  const s = result.summary;
  const ps = s.partial_set;
  const q = result.health_quality;
  const r = result.dataset_rul;
  const notValidated = job.validation?.status === "not_validated";
  const incomplete = ps?.incomplete_bearings.map((b) => b.bearing) ?? [];
  const ids = Object.keys(result.decisions).sort();
  const completeness = [
    s.display_name,
    ps && `Parts ${ps.uploaded.length}/${ps.uploaded.length + ps.missing.length}`,
    `Bearings ${s.bearings_processed}/${s.bearings_found}`,
    `Files ${s.files_processed.toLocaleString()}`,
    ps ? "Partial" : s.bearings_failed === 0 && s.files_failed === 0 ? "Complete" : "Completed with errors",
  ].filter(Boolean).join(" | ");

  const rows = ids.map((id) => {
    const t = result.trajectories?.[id] ?? [];
    const last = t[t.length - 1];
    return `<tr><td class=mono>${esc(id)}</td><td>${t.length.toLocaleString()}</td><td>${last?.health_indicator != null ? last.health_indicator.toFixed(3) : "—"}</td><td>${esc(last?.stage ?? "—")}${incomplete.includes(id) ? " (partial trajectory)" : ""}</td><td>${esc(STATUS_TEXT[result.decisions[id].current.status] ?? "available")}</td></tr>`;
  });

  const bearings = ids.map((id) => {
    const d = result.decisions[id];
    const t = result.trajectories?.[id] ?? [];
    const last = t[t.length - 1];
    const rul =
      d.current.status === "RUL_SUPPRESSED" || last?.predicted_rul_seconds == null
        ? `<p><strong>${r?.status === "validated" ? "Pretrained models: RUL withheld (RUL learned from this dataset is in the dataset table)." : "RUL intentionally withheld."}</strong> ${esc(withheldReason(d, notValidated))}</p>`
        : `<p><strong>RUL at last recording: ${(last.predicted_rul_seconds / 3600).toFixed(2)} h</strong>${
            last.rul_lo != null && last.rul_hi != null ? ` (interval ${(last.rul_lo / 3600).toFixed(2)} to ${(last.rul_hi / 3600).toFixed(2)} h)` : ""
          } from the ${esc(modelName(d.current.model ?? ""))}${d.current.status === "RUL_EXPERIMENTAL" ? ", experimental" : ""}.</p>`;
    const apps = Object.entries(d.applicability)
      .map(([m, a]) => `<li>${esc(modelName(m))}: ${esc(a.level)} (${a.shift_ratio.toFixed(2)}x feature shift)</li>`)
      .join("");
    return `<section><h3 class=mono>${esc(id)}${incomplete.includes(id) ? " (partial trajectory)" : ""}</h3>
${hiChart(t)}
<p>Stage at last recording: <strong>${esc(last?.stage ?? "—")}</strong>. Status: <span class=mono>${esc(d.current.status)}</span></p>
${rul}<p>Does each model apply to this bearing?</p><ul>${apps}</ul></section>`;
  });

  return `<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>RULGuard report ${esc(s.display_name ?? result.dataset_id)}</title>
<style>body{font:14px/1.5 system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 16px;color:#111;background:#fff}
h1{font-size:1.5rem;margin:0}h2{font-size:1.1rem;margin-top:2rem}h3{font-size:.95rem;margin-bottom:.25rem}
table{border-collapse:collapse;width:100%;font-size:12px}td,th{border-top:1px solid #ddd;padding:3px 6px;text-align:left}
.mono{font-family:ui-monospace,monospace}.muted{color:#666;font-size:12px}.box{border:1px solid #ddd;border-radius:8px;padding:8px 12px}
.warn{border-color:#f59e0b;background:#fffbeb}section{break-inside:avoid;border-top:1px solid #eee;margin-top:1rem}</style></head><body>
<h1>RULGuard analysis report</h1>
<p class=muted>Job ${esc(job.id)}, generated ${esc(new Date().toISOString())} on forevue.tech</p>
<p class="box${ps ? " warn" : ""}">${esc(completeness)}</p>
${ps ? `<p class="box warn">Partial dataset: ${ps.uploaded.length} of ${ps.uploaded.length + ps.missing.length} archive parts uploaded. Not included: <span class=mono>${esc(ps.missing.join(", "))}</span>.</p>` : ""}
${job.validation ? `<p class="box${notValidated ? " warn" : ""}"><strong>${notValidated ? "Not validated for RUL on this dataset" : "RUL validation on this dataset"}.</strong> ${esc(job.validation.note)}</p>` : ""}
<h2>Dataset</h2><table>
<tr><td>Detected as</td><td>${esc(result.profile.known_datasets.map((d) => d.dataset_id).join(", ") || "custom / generic")}</td></tr>
<tr><td>Sampling rate</td><td>${result.profile.sampling_rate_hz != null ? `${result.profile.sampling_rate_hz.toLocaleString()} Hz` : "unknown"}</td></tr>
<tr><td>Channels</td><td>${esc(result.profile.channels_found.join(", ") || "none")}</td></tr>
<tr><td>Files found / processed / skipped / failed</td><td>${s.files_found} / ${s.files_processed} / ${s.files_skipped} / ${s.files_failed}</td></tr>
<tr><td>Bearing runs found / processed / failed</td><td>${s.bearings_found} / ${s.bearings_processed} / ${s.bearings_failed}</td></tr>${q ? `<tr><td>Health rating reliability</td><td><strong>${esc(q.rating)}</strong>${q.trend != null ? `, trend with time ${q.trend.toFixed(2)}, smoothness ${Math.round(q.smoothness! * 100)}%` : ""}${q.weak_bearings?.length ? `. Weak: <span class=mono>${esc(q.weak_bearings.join(", "))}</span>` : ""}</td></tr>` : ""}${r ? `<tr><td>RUL learned from this dataset</td><td><strong>${esc(r.status.replaceAll("_", " "))}</strong> (${r.n_bearings} run-to-failure bearing(s), held-out test)${r.mae_seconds != null ? `: average error ${(r.mae_seconds / 3600).toFixed(2)} h vs ${(r.naive_mae_seconds! / 3600).toFixed(2)} h for the average-life guess` : ""}</td></tr>` : ""}</table>
${s.failed.length ? `<p class="box warn">Not processed: ${s.failed.map((f) => `<span class=mono>${esc(f.bearing)}</span> (${esc(f.reason)})`).join("; ")}</p>` : ""}
<h2>Per bearing, at the last recording</h2>
<table><tr><th>Bearing</th><th>Recordings</th><th>Health indicator</th><th>Stage</th><th>RUL (pretrained models)</th></tr>${rows.join("")}</table>
<h2>Bearing details</h2>${bearings.join("\n")}
<p class=muted>Stages are severity bands on the health indicator, not a physical fault diagnosis. RUL is shown only when a model is applicable and validated; numbers come from the numeric models, never from generated text.</p>
</body></html>`;
}

export function downloadText(text: string, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
