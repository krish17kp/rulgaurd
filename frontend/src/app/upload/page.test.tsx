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
    analyzeFemtoSignal: vi.fn().mockRejectedValue(new actual.ApiError(0, "not mocked in this test")),
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

// 6 numeric columns, no header - FEMTO's acc_*.csv shape (hour, minute,
// second, microsecond, accel_horizontal, accel_vertical).
const FEMTO_ROW = "9,29,5,884410,-0.1,0.329\n";

function smallFile(name = "small.csv") {
  return new File([FEMTO_ROW], name, { type: "text/csv" });
}

function bigFile(name = "big.csv") {
  const repeats = Math.ceil((DIRECT_UPLOAD_THRESHOLD_BYTES + 1024) / FEMTO_ROW.length);
  return new File([FEMTO_ROW.repeat(repeats)], name, { type: "text/csv" });
}

// College's LogFile_*.csv: 4 numeric columns, no header - a different,
// real dataset shape that must never reach the FEMTO prediction path.
function collegeFile(name = "LogFile_2022-06-20-17-00-31.csv") {
  return new File(["0.0485752270259481,-0.0638247022912424,41.6149124793233,24.8173535597786\n"], name, {
    type: "text/csv",
  });
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

  it("a non-retryable error (e.g. a malformed file) hides Retry and tells the user to pick a different file", async () => {
    vi.mocked(predictRulFromFemtoAcquisition).mockRejectedValueOnce(
      new ApiError(422, "Not a numeric, headerless FEMTO acc_*.csv file.", false)
    );
    render(<UploadPage />);

    await userEvent.upload(screen.getByTestId("file-input") as HTMLInputElement, smallFile());
    await userEvent.click(screen.getByRole("button", { name: /analyze bearing/i }));

    await waitFor(() => expect(screen.getByText(/Not a numeric, headerless/)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /^retry$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/won't succeed on retry as-is/)).toBeInTheDocument();
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

  it("shows the policy-suppressed warning, not a generic error, when applicability is LOW", async () => {
    vi.mocked(predictRulFromFemtoAcquisition).mockRejectedValueOnce(
      new ApiError(
        422,
        "RUL suppressed: model applicability is LOW (shift ratio 9.10x the in-domain reference) - " +
          "this signal does not look like the model's training population.",
        false,
        "APPLICABILITY_LOW"
      )
    );
    render(<UploadPage />);

    await userEvent.upload(screen.getByTestId("file-input") as HTMLInputElement, smallFile());
    await userEvent.click(screen.getByRole("button", { name: /analyze bearing/i }));

    await waitFor(() => expect(screen.getByText(/not a failed request/i)).toBeInTheDocument());
    expect(screen.getByText(/shift ratio 9\.10x/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^retry$/i })).not.toBeInTheDocument();
  });

  it("detects a college LogFile and refuses to send it to FEMTO prediction", async () => {
    render(<UploadPage />);

    await userEvent.upload(screen.getByTestId("file-input") as HTMLInputElement, collegeFile());
    await userEvent.click(screen.getByRole("button", { name: /analyze bearing/i }));

    await waitFor(() => expect(screen.getByText(/doesn't look like a FEMTO/)).toBeInTheDocument());
    expect(predictRulFromFemtoAcquisition).not.toHaveBeenCalled();
    expect(predictRulFromFemtoAcquisitionBlob).not.toHaveBeenCalled();
    expect(uploadFileToBlob).not.toHaveBeenCalled();
    expect(screen.getByText(/inspect another dataset/i)).toBeInTheDocument();
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
