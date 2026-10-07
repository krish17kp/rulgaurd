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
  not_yet_available: {
    ims: { status: "NOT_YET_AVAILABLE", reason: "RAR tooling missing, sudo unavailable." },
    xjtu_sy: { status: "NOT_YET_AVAILABLE", reason: "Mirrors require interactive auth." },
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
    expect(screen.getByText("IMS — not yet available")).toBeInTheDocument();
    expect(screen.getByText("XJTU-SY — not yet available")).toBeInTheDocument();
  });

  it("shows an error message when the request fails", async () => {
    vi.mocked(getCrossDatasetComparison).mockRejectedValue(new Error("network down"));
    render(<CrossDatasetPage />);
    await waitFor(() => expect(screen.getByText(/network down/)).toBeInTheDocument());
  });
});
