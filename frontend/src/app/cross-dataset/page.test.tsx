import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CrossDatasetPage from "./page";
import { CrossDatasetResponse } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, getCrossDatasetComparison: vi.fn() };
});

import { getCrossDatasetComparison } from "@/lib/api";

const DATA: CrossDatasetResponse = {
  in_domain_trained_results: {
    femto: {
      dataset: "FEMTO/PRONOSTIA",
      sampling_rate_hz: 25600,
      bearings: 6,
      channels: ["vibration_x", "vibration_y"],
      evaluation_method: "leave-one-bearing-out",
      model: "ExtraTreesRegressor",
      extra_trees_mae_seconds: 5577.2,
      naive_mae_seconds: 7702.9,
      n: 7534,
      overestimate_rate: 0.52,
      health_indicator_selected: "reference_hi",
    },
  },
  not_zero_shot_single_dataset_results: {
    college: {
      dataset: "College run-to-failure (single physical bearing)",
      sampling_rate_hz: 25600,
      bearings: 1,
      channels: ["vibration_x", "vibration_y", "bearing_temp", "ambient_temp"],
      evaluation_method: "chronological walk-forward (own split, not a FEMTO zero-shot application)",
      model: "ExtraTreesRegressor",
      extra_trees_mae_seconds: 122442.4,
      naive_mae_seconds: 0.0,
      naive_caveat: "College naive MAE=0.0 is an algebraic oracle identity, not a real baseline.",
      n: 3023,
      overestimate_rate: 1.0,
    },
  },
  // IMS is real and scored now (nightshift Phase 7) - only XJTU-SY, which
  // genuinely has no archive on this machine, stays NOT_YET_AVAILABLE.
  not_yet_available: {
    xjtu_sy: { status: "NOT_YET_AVAILABLE", reason: "Mirrors require interactive auth." },
  },
  cross_dataset_experiments: {
    schema_version: "cross-dataset-v2",
    generated_from: "reports/metrics/cross_dataset.json (scripts/run_cross_dataset.py)",
    summary: [
      {
        experiment: "A: FEMTO -> FEMTO (LOBO)", category: "WITHIN-DOMAIN", model: "raw_seconds",
        test_domain: "femto", n_bearings: 6, mae_seconds: 4899.5, naive_mae_seconds: 7000,
        fraction_mae: 0.1, fraction_skill: 0.3, overestimate_pct: 40,
      },
      {
        experiment: "ZS: FEMTO -> ims", category: "ZERO-SHOT", model: "raw_seconds",
        test_domain: "ims", n_bearings: 4, mae_seconds: 936139.7, naive_mae_seconds: 600000,
        fraction_mae: 0.4, fraction_skill: -0.555, overestimate_pct: 80,
      },
    ],
    routing_skill_by_dataset: {
      raw_seconds: { femto: 0.3, ims: -0.555, unseen: -0.555 },
      sn_fraction_multi: { femto: -0.001, ims: 0.135, unseen: -0.44 },
    },
    applicability_vs_error: null,
  },
  comparability_warning: "FEMTO and college MAE values must never be averaged.",
};

describe("CrossDatasetPage", () => {
  it("renders separated in-domain and not-zero-shot sections plus pending datasets", async () => {
    vi.mocked(getCrossDatasetComparison).mockResolvedValue(DATA);
    render(<CrossDatasetPage />);

    await waitFor(() => expect(screen.getByText("FEMTO/PRONOSTIA")).toBeInTheDocument());

    expect(screen.getByText("College run-to-failure (single physical bearing)")).toBeInTheDocument();
    expect(screen.getByText(DATA.comparability_warning)).toBeInTheDocument();
    expect(screen.getByText(DATA.not_zero_shot_single_dataset_results.college.naive_caveat!)).toBeInTheDocument();
    expect(screen.getByText("XJTU_SY — not yet available")).toBeInTheDocument();
    // IMS is no longer "not yet available" - it has real zero-shot numbers instead.
    expect(screen.queryByText(/IMS — not yet available/)).not.toBeInTheDocument();
  });

  it("shows zero-shot transfer honestly, including a negative (worse-than-guessing) skill", async () => {
    vi.mocked(getCrossDatasetComparison).mockResolvedValue(DATA);
    render(<CrossDatasetPage />);

    await waitFor(() => expect(screen.getByText("ZS: FEMTO -> ims")).toBeInTheDocument());
    expect(screen.getByText("-0.555")).toBeInTheDocument();
    expect(screen.getAllByText(/worse than guessing/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Zero-shot transfer/)).toBeInTheDocument();
  });

  it("shows an error message when the request fails", async () => {
    vi.mocked(getCrossDatasetComparison).mockRejectedValue(new Error("network down"));
    render(<CrossDatasetPage />);
    await waitFor(() => expect(screen.getByText(/network down/)).toBeInTheDocument());
  });
});
