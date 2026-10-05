import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import UploadPage from "./page";
import { ApiError, Compatibility, DatasetProfileResponse } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    inspectDataset: vi.fn(),
    inspectDatasetBlob: vi.fn(),
    predictRulFromFemtoAcquisition: vi.fn(),
    predictRulFromFemtoAcquisitionBlob: vi.fn(),
  };
});

vi.mock("@/lib/blobUpload", async () => {
  const actual = await vi.importActual<typeof import("@/lib/blobUpload")>("@/lib/blobUpload");
  return { ...actual, uploadFileToBlob: vi.fn() };
});

import {
  inspectDataset,
  inspectDatasetBlob,
  predictRulFromFemtoAcquisition,
  predictRulFromFemtoAcquisitionBlob,
} from "@/lib/api";
import { DIRECT_UPLOAD_THRESHOLD_BYTES, uploadFileToBlob } from "@/lib/blobUpload";

function smallFile(name = "small.csv") {
  return new File(["a,b\n1,2\n"], name, { type: "text/csv" });
}

function bigFile(name = "big.csv") {
  const bytes = new Uint8Array(DIRECT_UPLOAD_THRESHOLD_BYTES + 1024);
  return new File([bytes], name, { type: "text/csv" });
}

const genericProfile = (compatibility: Compatibility, reasons: string[] = []): DatasetProfileResponse => ({
  compatibility,
  reasons,
  profile: { file: "x.csv", readable: true, warnings: [] },
});

const femtoResult = {
  model_name: "extra_trees",
  rul_seconds: 3600,
  rul_hours: 1,
  features_used: [],
  features_missing: [],
  compatibility: "FULLY_SUPPORTED" as const,
  applicability_level: "HIGH" as const,
  applicability_shift_ratio: 1.0,
  applicability_reasons: [],
};

describe("UploadPage", () => {
  beforeEach(() => {
    vi.mocked(inspectDataset).mockReset();
    vi.mocked(inspectDatasetBlob).mockReset();
    vi.mocked(predictRulFromFemtoAcquisition).mockReset();
    vi.mocked(predictRulFromFemtoAcquisitionBlob).mockReset();
    vi.mocked(uploadFileToBlob).mockReset();
  });

  it("defaults to FEMTO analysis (not generic inspection)", async () => {
    render(<UploadPage />);
    expect(screen.getByText(/Analyze Bearing Data/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/dataset-inspection workflow/)).not.toBeChecked();
  });

  it("selecting a file shows its name and size without launching analysis yet", async () => {
    render(<UploadPage />);
    const input = screen.getByTestId("file-input") as HTMLInputElement;
    await userEvent.upload(input, smallFile("acc_00001.csv"));

    expect(screen.getByText("acc_00001.csv")).toBeInTheDocument();
    expect(predictRulFromFemtoAcquisition).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /analyze bearing/i })).toBeEnabled();
  });

  it("clicking Analyze Bearing launches the FEMTO prediction and shows the result", async () => {
    vi.mocked(predictRulFromFemtoAcquisition).mockResolvedValue(femtoResult);
    render(<UploadPage />);

    await userEvent.upload(screen.getByTestId("file-input") as HTMLInputElement, smallFile("acc_00001.csv"));
    await userEvent.click(screen.getByRole("button", { name: /analyze bearing/i }));

    await waitFor(() => expect(screen.getByText(/1\.00 hours/)).toBeInTheDocument());
    expect(predictRulFromFemtoAcquisition).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/can be trusted at face value/)).toBeInTheDocument();
  });

  it("shows an error with a working retry button when prediction fails, then succeeds", async () => {
    vi.mocked(predictRulFromFemtoAcquisition)
      .mockRejectedValueOnce(new ApiError(500, "backend exploded"))
      .mockResolvedValueOnce(femtoResult);

    render(<UploadPage />);
    await userEvent.upload(screen.getByTestId("file-input") as HTMLInputElement, smallFile());
    await userEvent.click(screen.getByRole("button", { name: /analyze bearing/i }));

    await waitFor(() => expect(screen.getByText("backend exploded")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));

    await waitFor(() => expect(screen.getByText(/1\.00 hours/)).toBeInTheDocument());
    expect(predictRulFromFemtoAcquisition).toHaveBeenCalledTimes(2);
  });

  it("'Analyze another file' clears the result and returns to file selection", async () => {
    vi.mocked(predictRulFromFemtoAcquisition).mockResolvedValue(femtoResult);
    render(<UploadPage />);

    await userEvent.upload(screen.getByTestId("file-input") as HTMLInputElement, smallFile());
    await userEvent.click(screen.getByRole("button", { name: /analyze bearing/i }));
    await waitFor(() => expect(screen.getByText(/1\.00 hours/)).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: /analyze another file/i }));

    expect(screen.queryByText(/1\.00 hours/)).not.toBeInTheDocument();
    expect(screen.getByText(/Try sample data/)).toBeInTheDocument();
  });

  it("'Remove' clears a selected file before analyzing", async () => {
    render(<UploadPage />);
    await userEvent.upload(screen.getByTestId("file-input") as HTMLInputElement, smallFile("acc_00001.csv"));
    expect(screen.getByText("acc_00001.csv")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /remove/i }));

    expect(screen.queryByText("acc_00001.csv")).not.toBeInTheDocument();
    expect(predictRulFromFemtoAcquisition).not.toHaveBeenCalled();
  });

  it("routes a large FEMTO upload through direct-to-storage, showing upload progress then processing", async () => {
    let progressCb!: (f: number) => void;
    vi.mocked(uploadFileToBlob).mockImplementation(async (_file, onProgress) => {
      progressCb = onProgress!;
      progressCb(0.5);
      return "https://example.public.blob.vercel-storage.com/acc-123.csv";
    });
    vi.mocked(predictRulFromFemtoAcquisitionBlob).mockResolvedValue({
      ...femtoResult,
      rul_seconds: 1800,
      rul_hours: 0.5,
      applicability_level: "MEDIUM",
      applicability_shift_ratio: 2.1,
      applicability_reasons: ["feature distribution shift (2.10x the in-domain reference)"],
    });

    render(<UploadPage />);
    await userEvent.upload(screen.getByTestId("file-input") as HTMLInputElement, bigFile("acc_big.csv"));
    await userEvent.click(screen.getByRole("button", { name: /analyze bearing/i }));

    await waitFor(() => expect(screen.getByText(/0\.50 hours/)).toBeInTheDocument());
    expect(uploadFileToBlob).toHaveBeenCalledTimes(1);
    expect(predictRulFromFemtoAcquisitionBlob).toHaveBeenCalledWith(
      "https://example.public.blob.vercel-storage.com/acc-123.csv"
    );
    expect(predictRulFromFemtoAcquisition).not.toHaveBeenCalled();
    expect(screen.getByText(/Model applicability: MEDIUM/)).toBeInTheDocument();
  });

  it("the Advanced section provides generic dataset inspection, off by default", async () => {
    vi.mocked(inspectDataset).mockResolvedValue(genericProfile("UNSUPPORTED", ["no vibration channel recognised in the header"]));
    render(<UploadPage />);

    await userEvent.click(screen.getByText(/Advanced: inspect another/));
    await userEvent.click(screen.getByLabelText(/dataset-inspection workflow/));
    await userEvent.upload(screen.getByTestId("file-input") as HTMLInputElement, smallFile());
    await userEvent.click(screen.getByRole("button", { name: /inspect dataset/i }));

    await waitFor(() => expect(screen.getByText("UNSUPPORTED")).toBeInTheDocument());
    expect(screen.getByText(/no vibration channel recognised/)).toBeInTheDocument();
    expect(inspectDataset).toHaveBeenCalledTimes(1);
  });
});
