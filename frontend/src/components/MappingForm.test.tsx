import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MappingForm } from "@/components/MappingForm";
import { DatasetJob } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, submitDatasetJobMapping: vi.fn(async (id: string) => ({ id, state: "queued" })) };
});
import { submitDatasetJobMapping } from "@/lib/api";

const job = {
  id: "J1",
  state: "needs_mapping",
  mapping_proposal: {
    sample_file: "rig_a/rec1.csv",
    has_header: true,
    rows_per_file: 2000,
    columns: [
      { name: "time_s", role: null, confidence: "none", usable: true },
      { name: "acc_x", role: "vibration_x", confidence: "high", usable: true },
      { name: "label", role: null, confidence: "none", usable: false },
    ],
    roles: ["vibration_x", "vibration_y", "temperature_bearing", "temperature_ambient"],
    runs: [{ id: "rig_a", files: 12 }],
    sampling_rate_hz: 2000,
    needs_interval: true,
    warnings: [],
  },
} as unknown as DatasetJob;

describe("MappingForm", () => {
  it("needs a vibration column and the recording interval, then posts the confirmed mapping", async () => {
    const onSubmitted = vi.fn();
    render(<MappingForm job={job} onSubmitted={onSubmitted} />);
    expect(screen.getByText("from the column name")).toBeInTheDocument();
    expect(screen.getByText(/not numeric/)).toBeInTheDocument();
    const go = screen.getByRole("button", { name: "Analyse with these settings" });
    expect(go).toBeDisabled(); // interval still missing

    await userEvent.type(screen.getByLabelText(/Time between recordings/), "600");
    expect(go).toBeEnabled();
    await userEvent.selectOptions(screen.getByLabelText("Role of acc_x"), "");
    expect(go).toBeDisabled();
    expect(screen.getByText("Choose at least one vibration column.")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Role of acc_x"), "vibration_x");

    await userEvent.click(screen.getByLabelText(/Every bearing ran until it failed/));
    await userEvent.click(go);
    expect(submitDatasetJobMapping).toHaveBeenCalledWith("J1", {
      columns: { acc_x: "vibration_x" },
      sampling_rate_hz: 2000,
      recording_interval_s: 600,
      ran_to_failure: true,
    });
    expect(onSubmitted).toHaveBeenCalled();
  });
});
