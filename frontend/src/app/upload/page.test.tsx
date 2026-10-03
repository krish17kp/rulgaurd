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

describe("UploadPage", () => {
  beforeEach(() => {
    vi.mocked(inspectDataset).mockReset();
    vi.mocked(inspectDatasetBlob).mockReset();
    vi.mocked(predictRulFromFemtoAcquisition).mockReset();
    vi.mocked(predictRulFromFemtoAcquisitionBlob).mockReset();
    vi.mocked(uploadFileToBlob).mockReset();
  });

  it("defaults to generic mode and switches to femto mode on radio selection", async () => {
    render(<UploadPage />);
    expect(screen.getByLabelText(/Unknown \/ other dataset/)).toBeChecked();

    await userEvent.click(screen.getByLabelText(/FEMTO \/ supported bearing/));
    expect(screen.getByLabelText(/FEMTO \/ supported bearing/)).toBeChecked();
    expect(screen.getByLabelText(/Unknown \/ other dataset/)).not.toBeChecked();
  });

  it("inspects a small generic file directly, without uploading to blob storage", async () => {
    vi.mocked(inspectDataset).mockResolvedValue(genericProfile("FULLY_SUPPORTED"));
    render(<UploadPage />);

    const input = screen.getByTestId("file-input") as HTMLInputElement;
    await userEvent.upload(input, smallFile());

    await waitFor(() => expect(screen.getByText("FULLY SUPPORTED")).toBeInTheDocument());
    expect(inspectDataset).toHaveBeenCalledTimes(1);
    expect(uploadFileToBlob).not.toHaveBeenCalled();
  });

  it("shows RETRAIN_REQUIRED as a distinct badge from FULLY_SUPPORTED", async () => {
    vi.mocked(inspectDataset).mockResolvedValue(
      genericProfile("RETRAIN_REQUIRED", ["sampling rate matches, but model applicability is LOW"])
    );
    render(<UploadPage />);
    await userEvent.upload(screen.getByTestId("file-input") as HTMLInputElement, smallFile());

    await waitFor(() => expect(screen.getByText("RETRAIN REQUIRED")).toBeInTheDocument());
    expect(screen.getByText(/model applicability is LOW/)).toBeInTheDocument();
  });

  it("shows an UNSUPPORTED badge and reasons for an unrecognised dataset", async () => {
    vi.mocked(inspectDataset).mockResolvedValue(
      genericProfile("UNSUPPORTED", ["no vibration channel recognised in the header"])
    );
    render(<UploadPage />);
    await userEvent.upload(screen.getByTestId("file-input") as HTMLInputElement, smallFile());

    await waitFor(() => expect(screen.getByText("UNSUPPORTED")).toBeInTheDocument());
    expect(screen.getByText(/no vibration channel recognised/)).toBeInTheDocument();
  });

  it("shows an error with a working retry button when inspection fails", async () => {
    vi.mocked(inspectDataset)
      .mockRejectedValueOnce(new ApiError(500, "backend exploded"))
      .mockResolvedValueOnce(genericProfile("FULLY_SUPPORTED"));

    render(<UploadPage />);
    await userEvent.upload(screen.getByTestId("file-input") as HTMLInputElement, smallFile());

    await waitFor(() => expect(screen.getByText("backend exploded")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));

    await waitFor(() => expect(screen.getByText("FULLY SUPPORTED")).toBeInTheDocument());
    expect(inspectDataset).toHaveBeenCalledTimes(2);
  });

  it("predicts RUL directly for a small FEMTO upload", async () => {
    vi.mocked(predictRulFromFemtoAcquisition).mockResolvedValue({
      model_name: "extra_trees",
      rul_seconds: 3600,
      rul_hours: 1,
      features_used: [],
      features_missing: [],
      compatibility: "FULLY_SUPPORTED",
      applicability_level: "HIGH",
      applicability_shift_ratio: 1.0,
      applicability_reasons: [],
    });

    render(<UploadPage />);
    await userEvent.click(screen.getByLabelText(/FEMTO \/ supported bearing/));
    await userEvent.upload(screen.getByTestId("file-input") as HTMLInputElement, smallFile("acc_00001.csv"));

    await waitFor(() => expect(screen.getByText(/1\.00 hours/)).toBeInTheDocument());
    expect(predictRulFromFemtoAcquisition).toHaveBeenCalledTimes(1);
  });

  it("routes a large FEMTO upload through direct-to-storage, showing upload progress then processing", async () => {
    let progressCb!: (f: number) => void;
    vi.mocked(uploadFileToBlob).mockImplementation(async (_file, onProgress) => {
      progressCb = onProgress!;
      progressCb(0.5);
      return "https://example.public.blob.vercel-storage.com/acc-123.csv";
    });
    vi.mocked(predictRulFromFemtoAcquisitionBlob).mockResolvedValue({
      model_name: "extra_trees",
      rul_seconds: 1800,
      rul_hours: 0.5,
      features_used: [],
      features_missing: [],
      compatibility: "FULLY_SUPPORTED",
      applicability_level: "MEDIUM",
      applicability_shift_ratio: 2.1,
      applicability_reasons: ["feature distribution shift (2.10x the in-domain reference)"],
    });

    render(<UploadPage />);
    await userEvent.click(screen.getByLabelText(/FEMTO \/ supported bearing/));
    await userEvent.upload(screen.getByTestId("file-input") as HTMLInputElement, bigFile("acc_big.csv"));

    await waitFor(() => expect(screen.getByText(/0\.50 hours/)).toBeInTheDocument());
    expect(uploadFileToBlob).toHaveBeenCalledTimes(1);
    expect(predictRulFromFemtoAcquisitionBlob).toHaveBeenCalledWith(
      "https://example.public.blob.vercel-storage.com/acc-123.csv"
    );
    expect(predictRulFromFemtoAcquisition).not.toHaveBeenCalled();
    // The MEDIUM applicability warning must still be surfaced for a large upload.
    expect(screen.getByText(/Model applicability: MEDIUM/)).toBeInTheDocument();
  });

  it("switching modes mid-request discards the stale in-flight result", async () => {
    let resolveInspect!: (v: unknown) => void;
    vi.mocked(inspectDataset).mockReturnValue(new Promise((r) => (resolveInspect = r)) as never);

    render(<UploadPage />);
    await userEvent.upload(screen.getByTestId("file-input") as HTMLInputElement, smallFile());
    await userEvent.click(screen.getByLabelText(/FEMTO \/ supported bearing/));

    resolveInspect(genericProfile("FULLY_SUPPORTED"));
    await new Promise((r) => setTimeout(r, 0));

    expect(screen.queryByText("FULLY SUPPORTED")).not.toBeInTheDocument();
  });
});
