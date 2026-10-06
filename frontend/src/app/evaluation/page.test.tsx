import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import EvaluationPage from "./page";
import { EvaluationResponse, HealthIndicatorComparisonResponse, HiddenSetEvaluationResponse, TrajectoryResponse } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getModelEvaluation: vi.fn(),
    getHiddenSetEvaluation: vi.fn(),
    getHealthIndicatorComparison: vi.fn(),
    getTrajectoryBearings: vi.fn(),
    getTrajectory: vi.fn(),
  };
});

import {
  getHealthIndicatorComparison,
  getHiddenSetEvaluation,
  getModelEvaluation,
  getTrajectory,
  getTrajectoryBearings,
} from "@/lib/api";

const EVALUATION: EvaluationResponse = {
  femto_lobo_mean_mae_by_model: { extra_trees: 5061.0, naive: 6584.8 },
  femto_lobo_overall_by_model: {
    extra_trees: { mae_seconds: 5577.2, rmse_seconds: 7265.6, median_abs_error_seconds: 4366.7, n: 7534, overestimate_rate: 0.52 },
    naive: { mae_seconds: 7702.9, rmse_seconds: 9416.7, median_abs_error_seconds: 4616.0, n: 7534, overestimate_rate: 0.41 },
  },
  femto_lobo: [
    { model: "extra_trees", held_out_bearing: "femto:Bearing2_1", mae_seconds: 2396.6, rmse_seconds: 2974.4, median_abs_error_seconds: 2054.8, mean_signed_error_seconds: -806.9, n: 911 },
    { model: "naive", held_out_bearing: "femto:Bearing2_1", mae_seconds: 4136.0, rmse_seconds: 4136.0, median_abs_error_seconds: 4136.0, mean_signed_error_seconds: 4136.0, n: 911 },
  ],
  college_mean_mae_by_model: { extra_trees: 122441.3, naive: 0.0 },
  college_overall_by_model: {
    extra_trees: { mae_seconds: 122442.4, rmse_seconds: 139525.3, median_abs_error_seconds: 117241.2, n: 3023, overestimate_rate: 1.0 },
    naive: { mae_seconds: 0.0, rmse_seconds: 0.0, median_abs_error_seconds: 0.0, n: 3023, overestimate_rate: 0.0 },
  },
  college_naive_caveat: "naive scores MAE=0.0 by construction - it is an oracle, not a fair comparison.",
};

const HIDDEN_SET: HiddenSetEvaluationResponse = {
  convention: "One prediction per bearing at the last acquisition of the censored prefix.",
  scoring_function: "PHM2012",
  ground_truth_variants: { official: "Table 3", archive_derived: "derived" },
  lower_mae_model_official: "extra_trees",
  results: {
    official: {
      per_bearing: [
        { model: "extra_trees", bearing: "Bearing1_3", actual_rul_seconds: 5730, predicted_rul_seconds: 7678.2, error_seconds: 1948.2, percent_error: -34, phm2012_score: 0.009 },
        { model: "naive", bearing: "Bearing1_3", actual_rul_seconds: 5730, predicted_rul_seconds: 0, error_seconds: -5730, percent_error: 100, phm2012_score: 0.031 },
      ],
    },
    archive_derived: { per_bearing: [] },
  },
};

const HI_COMPARISON: HealthIndicatorComparisonResponse = {
  transparent_hi: { status: "legacy", mean_spearman: -0.41, pinning: { mean_pct_at_one: 47.5, worst_pct_at_one: 88.9, mean_usable_range_p05_p95: 0.68 }, per_bearing: [] },
  pca_hi: { status: "legacy", mean_spearman: -0.4, pinning: { mean_pct_at_one: 0.02, worst_pct_at_one: 0.13, mean_usable_range_p05_p95: 0.11 }, per_bearing: [] },
  reference_hi: { status: "current", mean_spearman: -0.53, pinning: { mean_pct_at_one: 0.0, worst_pct_at_one: 0.0, mean_usable_range_p05_p95: 0.76 }, per_bearing: [] },
  selected: "reference_hi",
  selection_reason: "worst per-bearing pct_at_one < 5.0%, then strongest mean rank trend",
};

const TRAJECTORY: TrajectoryResponse = {
  bearing_run_id: "femto:Bearing2_1",
  sequence_index: [0, 1],
  reference_hi: [0.95, 0.1],
  transparent_hi: null,
  pca_hi: null,
  stage: ["HEALTHY", "CRITICAL"],
  stage_thresholds: { hi_warn: 0.6, hi_critical: 0.2, persistence: 3 },
  actual_rul_seconds: [9100, 0],
  held_out_predicted_rul_seconds: { sequence_index: [0, 1], predicted_rul_seconds: [8800, 300] },
  held_out_metrics: { mae_seconds: 2396.6, n: 2, overestimate_rate: 0.37 },
};

describe("EvaluationPage", () => {
  it("renders FEMTO headline, hidden-set, HI comparison, and the college caveat", async () => {
    vi.mocked(getModelEvaluation).mockResolvedValue(EVALUATION);
    vi.mocked(getHiddenSetEvaluation).mockResolvedValue(HIDDEN_SET);
    vi.mocked(getHealthIndicatorComparison).mockResolvedValue(HI_COMPARISON);
    vi.mocked(getTrajectoryBearings).mockResolvedValue({ bearings: ["femto:Bearing2_1"] });
    vi.mocked(getTrajectory).mockResolvedValue(TRAJECTORY);

    render(<EvaluationPage />);

    await waitFor(() => expect(screen.getByText("FEMTO headline (leave-one-bearing-out)")).toBeInTheDocument());
    expect(screen.getByText("Hidden FEMTO challenge (Full_Test_Set, scored once post-freeze)")).toBeInTheDocument();
    expect(screen.getByText("Health indicator comparison")).toBeInTheDocument();
    expect(screen.getByText(/naive scores MAE=0.0 by construction/)).toBeInTheDocument();
    expect(screen.getByText(/oracle, not a fair comparison/)).toBeInTheDocument();
    expect(screen.getByText(/never applied to college data as if validated/)).toBeInTheDocument();
  });
});
