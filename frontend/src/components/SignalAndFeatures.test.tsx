import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SignalAndFeatures } from "./SignalAndFeatures";
import { FemtoSignalResponse } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, analyzeFemtoSignal: vi.fn() };
});

import { analyzeFemtoSignal } from "@/lib/api";

const RESPONSE: FemtoSignalResponse = {
  sample_rate_hz: 25600,
  samples: 4,
  vibration_x: { waveform: [1, 2, 3, 4], fft_frequency_hz: [0, 6400], fft_magnitude: [1, 2] },
  vibration_y: { waveform: [4, 3, 2, 1], fft_frequency_hz: [0, 6400], fft_magnitude: [3, 4] },
  features: { vibration_x_rms: 2.5, vibration_y_rms: 2.5 },
};

describe("SignalAndFeatures", () => {
  it("renders real waveform/feature data from analyzeFemtoSignal, not placeholders", async () => {
    vi.mocked(analyzeFemtoSignal).mockResolvedValue(RESPONSE);
    const file = new File(["x"], "acc_00450.csv");
    render(<SignalAndFeatures file={file} />);

    await waitFor(() => expect(screen.getByText(/4 samples at 25,600 Hz/)).toBeInTheDocument());
    expect(analyzeFemtoSignal).toHaveBeenCalledWith(file);

    const user = (await import("@testing-library/user-event")).default.setup();
    await user.click(screen.getByText("Features"));
    expect(screen.getAllByText("2.5000").length).toBeGreaterThan(0);
  });

  it("shows an error message when the signal request fails", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(analyzeFemtoSignal).mockRejectedValue(new ApiError(500, "backend unavailable"));
    render(<SignalAndFeatures file={new File(["x"], "bad.csv")} />);
    await waitFor(() => expect(screen.getByText("backend unavailable")).toBeInTheDocument());
  });
});
