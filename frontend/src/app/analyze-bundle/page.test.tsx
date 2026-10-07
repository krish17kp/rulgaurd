import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import AnalyzeBundlePage from "./page";
import { ApiError } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, analyzeBundle: vi.fn() };
});

import { analyzeBundle } from "@/lib/api";

function zipFile(name = "bundle.rulguard.zip") {
  return new File([new Uint8Array([1, 2, 3])], name, { type: "application/zip" });
}

describe("AnalyzeBundlePage", () => {
  it("renders the FEMTO bundle via the bearing-ZIP result view", async () => {
    vi.mocked(analyzeBundle).mockResolvedValue({
      status: "ok",
      dataset_id: "femto:Bearing2_1",
      kind: "femto",
      payload: {
        bearing_run_id: "femto:Bearing2_1",
        acquisition_count: 3,
        sample_rate_hz: 25600,
        sequence_index: [0, 1, 2],
        representative_indices: {},
        representative_signals: null,
        representative_fft: null,
        feature_trajectory: null,
        reference_hi: [1, 0.9, 0.5],
        transparent_hi: null,
        pca_hi: null,
        stage: ["HEALTHY", "HEALTHY", "DEGRADING"],
        actual_rul_seconds: [20, 10, 0],
        held_out_predicted_rul_seconds: null,
        held_out_mae_seconds: null,
        held_out_unavailable_reason: null,
        warnings: [],
      },
    });

    render(<AnalyzeBundlePage />);
    await userEvent.upload(screen.getByTestId("file-input"), zipFile());

    await waitFor(() => expect(screen.getByText("femto:Bearing2_1")).toBeInTheDocument());
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("renders the college bundle's own trend/RUL/caveat view", async () => {
    vi.mocked(analyzeBundle).mockResolvedValue({
      status: "ok",
      dataset_id: "college",
      kind: "college",
      payload: {
        "college:nsk6205": {
          dataset_id: "college",
          n_source_files_in_cache: 129,
          n_raw_college_files_on_disk: 129,
          coverage_note: "Full coverage: all 129 raw LogFile_*.csv files are represented.",
          n_acquisitions: 2,
          sample_rate_hz: 25600,
          sequence_index: [0, 1],
          event_timestamp: ["2022-06-20T17:00:31", "2022-06-20T18:00:31"],
          temp_available_fraction: 1,
          feature_trends: { vibration_x_rms: [0.1, 0.2] },
          actual_rul_seconds: [10, 0],
          held_out_predicted_rul_seconds: { sequence_index: [0, 1], predicted_rul_seconds: [9, 1] },
          walk_forward_overall: {},
          naive_caveat: "College naive MAE is an algebraic oracle identity, not a real baseline.",
          domain_shift_note: "FEMTO-fit models are not applied to college data here (D11).",
        },
      },
    });

    render(<AnalyzeBundlePage />);
    await userEvent.upload(screen.getByTestId("file-input"), zipFile());

    await waitFor(() =>
      expect(screen.getByText(/algebraic oracle identity/)).toBeInTheDocument()
    );
    expect(screen.getByText(/D11/)).toBeInTheDocument();
    expect(screen.getByText(/Full coverage: all 129/)).toBeInTheDocument();
  });

  it("shows the rejection message for a corrupted/invalid bundle, not a crash", async () => {
    vi.mocked(analyzeBundle).mockRejectedValue(
      new ApiError(400, "invalid analysis bundle: dataset.json checksum mismatch")
    );

    render(<AnalyzeBundlePage />);
    await userEvent.upload(screen.getByTestId("file-input"), zipFile());

    await waitFor(() =>
      expect(screen.getByText(/checksum mismatch/)).toBeInTheDocument()
    );
  });

  it("degrades gracefully for an unrecognized bundle shape instead of guessing a chart", async () => {
    vi.mocked(analyzeBundle).mockResolvedValue({
      status: "ok",
      dataset_id: "mystery:1",
      kind: "unknown",
      payload: { something: "else" },
    });

    render(<AnalyzeBundlePage />);
    await userEvent.upload(screen.getByTestId("file-input"), zipFile());

    await waitFor(() =>
      expect(screen.getByText("No renderer available for this bundle.")).toBeInTheDocument()
    );
    expect(screen.getByText("mystery:1")).toBeInTheDocument();
  });
});
