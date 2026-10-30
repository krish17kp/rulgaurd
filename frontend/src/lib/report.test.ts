import { describe, expect, it } from "vitest";
import { buildReportHtml } from "@/lib/report";
import { DatasetJob, DatasetJobResult } from "@/lib/api";

const result = {
  dataset_id: "xjtu",
  outcome: "analyzed",
  validation: null,
  profile: { n_files: 3, sampling_rate_hz: 25600, sampling_rate_source: "known", known_datasets: [{ dataset_id: "xjtu" }], channels_found: ["h", "v"], warnings: [] },
  summary: {
    dataset_id: "xjtu", display_name: "XJTU-SY", files_found: 6, files_processed: 6, files_skipped: 0, files_failed: 0,
    bearings_found: 1, bearings_processed: 1, bearings_failed: 0, skipped: [], failed: [],
    partial_set: { uploaded: ["a.part01.rar"], missing: ["a.part02.rar"], incomplete_bearings: [{ bearing: "<b>1_1", reason: "cut" }] },
  },
  decisions: {
    "<b>1_1": {
      status: "RUL_SUPPRESSED", scope: "", quality_ok: true, quality_reasons: [],
      applicability: { raw_seconds: { level: "LOW", shift_ratio: 3.2, reasons: [] } },
      current: { status: "RUL_SUPPRESSED", model: null, validated_skill: null, scope: "" },
    },
  },
  trajectories: {
    "<b>1_1": [0, 60, 120, 6000, 6060].map((t, i) => ({ sequence_index: i, elapsed_s: t, health_indicator: i / 4, stage: i > 2 ? "CRITICAL" : "HEALTHY" })),
  },
} as unknown as DatasetJobResult;

const job = { id: "J1", validation: { status: "not_validated", note: "No skill.", skills: {}, trained_on: [] } } as unknown as DatasetJob;

describe("buildReportHtml", () => {
  it("states partial coverage, the withheld RUL reason and breaks the chart at the gap", () => {
    const html = buildReportHtml(job, result);
    expect(html).toContain("Parts 1/2");
    expect(html).toContain("a.part02.rar");
    expect(html).toContain("RUL intentionally withheld");
    expect(html).toContain("FEMTO RUL model: LOW");
    expect(html).toContain("&lt;b&gt;1_1 (partial trajectory)");
    expect(html).not.toContain("<b>1_1");
    expect(html.match(/<polyline/g)).toHaveLength(2);
  });
});
