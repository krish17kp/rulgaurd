import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import TrajectoryPage from "./page";
import { TrajectoryResponse } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, getTrajectoryBearings: vi.fn(), getTrajectory: vi.fn() };
});

import { getTrajectory, getTrajectoryBearings } from "@/lib/api";

const TRAJECTORY: TrajectoryResponse = {
  bearing_run_id: "femto:Bearing2_1",
  sequence_index: [0, 1, 2],
  reference_hi: [0.95, 0.9, 0.1],
  transparent_hi: [1, 1, 0.2],
  pca_hi: [0.9, 0.8, 0.05],
  stage: ["HEALTHY", "HEALTHY", "CRITICAL"],
  stage_thresholds: { hi_warn: 0.6, hi_critical: 0.2, persistence: 3 },
  actual_rul_seconds: [9100, 9000, 0],
  held_out_predicted_rul_seconds: { sequence_index: [0, 1, 2], predicted_rul_seconds: [8800, 8700, 300] },
  held_out_metrics: { mae_seconds: 2396.6, n: 3, overestimate_rate: 0.37 },
};

describe("TrajectoryPage", () => {
  it("loads the bearing list, defaults to Bearing2_1, and renders real HI/RUL evidence", async () => {
    vi.mocked(getTrajectoryBearings).mockResolvedValue({
      bearings: ["femto:Bearing1_1", "femto:Bearing2_1"],
    });
    vi.mocked(getTrajectory).mockResolvedValue(TRAJECTORY);

    render(<TrajectoryPage />);

    await waitFor(() => expect(getTrajectory).toHaveBeenCalledWith("femto:Bearing2_1"));
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
    expect(screen.getByText(/not a physical fault/)).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument(); // acquisitions count
  });
});
