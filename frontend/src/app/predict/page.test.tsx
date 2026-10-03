import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PredictPage from "./page";
import { ApiError } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, predictRul: vi.fn() };
});

import { predictRul } from "@/lib/api";

describe("PredictPage", () => {
  beforeEach(() => {
    vi.mocked(predictRul).mockReset();
  });

  it("renders a successful RUL prediction in hours and seconds", async () => {
    vi.mocked(predictRul).mockResolvedValue({
      model_name: "extra_trees",
      rul_seconds: 7200,
      rul_hours: 2,
      features_used: ["a"],
      features_missing: [],
      compatibility: "FULLY_SUPPORTED",
      applicability_level: "HIGH",
      applicability_shift_ratio: 1.0,
      applicability_reasons: [],
    });

    render(<PredictPage />);
    await userEvent.click(screen.getByRole("button", { name: /predict/i }));

    await waitFor(() => expect(screen.getByText("2.0")).toBeInTheDocument());
    expect(screen.getByText(/7200 seconds/)).toBeInTheDocument();
    expect(screen.getByText(/extra_trees/)).toBeInTheDocument();
  });

  it("shows a loading state while the request is in flight", async () => {
    let resolve!: (v: unknown) => void;
    vi.mocked(predictRul).mockReturnValue(new Promise((r) => (resolve = r)) as never);

    render(<PredictPage />);
    await userEvent.click(screen.getByRole("button", { name: /predict/i }));
    expect(screen.getByRole("button", { name: /predicting/i })).toBeDisabled();

    resolve({
      model_name: "extra_trees",
      rul_seconds: 1,
      rul_hours: 0,
      features_used: [],
      features_missing: [],
      compatibility: "FULLY_SUPPORTED",
      applicability_level: null,
      applicability_shift_ratio: null,
      applicability_reasons: [],
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "Predict" })).toBeEnabled());
  });

  it("shows the backend's error detail on failure", async () => {
    vi.mocked(predictRul).mockRejectedValue(new ApiError(422, "dataset_id is not supported"));

    render(<PredictPage />);
    await userEvent.click(screen.getByRole("button", { name: /predict/i }));

    await waitFor(() => expect(screen.getByText(/dataset_id is not supported/)).toBeInTheDocument());
  });

  it("rejects invalid JSON client-side without calling the API", async () => {
    render(<PredictPage />);
    const textarea = screen.getByRole("textbox");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "{{not json");
    await userEvent.click(screen.getByRole("button", { name: /predict/i }));

    expect(await screen.findByText(/must be valid JSON/)).toBeInTheDocument();
    expect(predictRul).not.toHaveBeenCalled();
  });
});
