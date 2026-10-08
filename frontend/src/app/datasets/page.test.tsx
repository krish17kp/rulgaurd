import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DatasetsPage from "./page";
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
    xjtu_sy: { status: "NOT_YET_AVAILABLE", reason: "Mirrors require interactive auth." },
  },
  cross_dataset_experiments: {
    schema_version: "cross-dataset-v2",
    generated_from: "reports/metrics/cross_dataset.json (scripts/run_cross_dataset.py)",
    summary: [
      {
        experiment: "ZS: FEMTO -> ims", category: "ZERO-SHOT", model: "raw_seconds",
        test_domain: "ims", n_bearings: 4, mae_seconds: 936139.7, naive_mae_seconds: 600000,
        fraction_mae: 0.4, fraction_skill: -0.555, overestimate_pct: 80,
      },
    ],
    routing_skill_by_dataset: {
      raw_seconds: { femto: 0.3, ims: -0.555, unseen: -0.555 },
    },
    applicability_vs_error: null,
  },
  fault_diagnosis_datasets: {
    cwru: {
      dataset: "CWRU (Case Western Reserve University Bearing Data Center)",
      dataset_type: "FAULT_DIAGNOSIS",
      source: "https://engineering.case.edu/bearingdatacenter/download-data-file",
      sampling_rate_hz: 12000,
      channels: ["vibration_x (drive-end accelerometer)"],
      conditions: [{ file_id: "97", label: "normal baseline" }],
      rul_supported: false,
      rul_unavailable_reason: "CWRU records single fixed-condition snapshots, not a trajectory.",
      applicability: {
        level: "LOW",
        shift_ratio: 1.92,
        reasons: ["feature distribution shift 1.92x the in-domain reference"],
        evaluated_against: "artifacts/models/cross_domain_bundle.joblib (frozen FEMTO model)",
      },
      representative: {
        condition: "normal baseline",
        signal: [0.1, 0.2, -0.1, 0.3],
        fft: { frequency_hz: [0, 100, 200], magnitude: [1, 2, 0.5] },
      },
    },
    paderborn: {
      dataset: "Paderborn University KAt-DataCenter",
      dataset_type: "FAULT_DIAGNOSIS",
      source: "https://groups.uni-paderborn.de/kat/BearingDataCenter/",
      sampling_rate_hz: 64000,
      channels: ["vibration_x (vibration_1 accelerometer)"],
      conditions: [{ file_id: "N15_M07_F10_K001_1", label: "healthy (K001)" }],
      rul_supported: false,
      rul_unavailable_reason: "Each Paderborn recording is a short fixed-condition snapshot.",
      applicability: {
        level: "LOW",
        shift_ratio: 5.84,
        reasons: ["feature distribution shift 5.84x the in-domain reference"],
        evaluated_against: "artifacts/models/cross_domain_bundle.joblib (frozen FEMTO model)",
      },
      representative: {
        condition: "healthy (K001)",
        signal: [0.05, -0.05, 0.1, -0.1],
        fft: { frequency_hz: [0, 100, 200], magnitude: [0.8, 1.5, 0.3] },
      },
    },
  },
  comparability_warning: "FEMTO and college MAE values must never be averaged.",
};

describe("DatasetsPage", () => {
  it("renders the FEMTO and College real run-to-failure cards", async () => {
    vi.mocked(getCrossDatasetComparison).mockResolvedValue(DATA);
    render(<DatasetsPage />);

    await waitFor(() => expect(screen.getByText("FEMTO/PRONOSTIA")).toBeInTheDocument());
    expect(screen.getByText("College run-to-failure (single physical bearing)")).toBeInTheDocument();
    expect(screen.getAllByText("REAL DATA").length).toBeGreaterThan(0);
  });

  it("shows the IMS zero-shot result honestly, including a negative skill", async () => {
    vi.mocked(getCrossDatasetComparison).mockResolvedValue(DATA);
    render(<DatasetsPage />);

    await waitFor(() => expect(screen.getByText(/IMS \/ NASA/)).toBeInTheDocument());
    expect(screen.getByText(/-0.555/)).toBeInTheDocument();
    expect(screen.getByText(/honest negative result/)).toBeInTheDocument();
  });

  it("shows CWRU and Paderborn cards with no fake RUL metric", async () => {
    vi.mocked(getCrossDatasetComparison).mockResolvedValue(DATA);
    render(<DatasetsPage />);

    await waitFor(() => expect(screen.getByText(/CWRU \(Case Western/)).toBeInTheDocument());
    expect(screen.getByText(/Paderborn University/)).toBeInTheDocument();
    expect(screen.getAllByText("FAULT DIAGNOSIS / CONDITION MONITORING")).toHaveLength(2);
    expect(screen.getAllByText("RUL evaluation unavailable.")).toHaveLength(2);
    expect(screen.queryByText(/mae_seconds/)).not.toBeInTheDocument();
    expect(screen.queryByText(/RUL MAE/)).not.toBeInTheDocument();
    expect(screen.queryByText(/RUL RMSE/)).not.toBeInTheDocument();
  });

  it("visibly labels the synthetic card as synthetic, separate from real data", async () => {
    vi.mocked(getCrossDatasetComparison).mockResolvedValue(DATA);
    render(<DatasetsPage />);

    await waitFor(() => expect(screen.getByText(/Synthetic bearing degradation simulator/)).toBeInTheDocument());
    expect(screen.getByText("SYNTHETIC")).toBeInTheDocument();
    expect(screen.getByText(/NOT REAL-WORLD VALIDATION/)).toBeInTheDocument();
  });

  it("shows an error message when the request fails", async () => {
    vi.mocked(getCrossDatasetComparison).mockRejectedValue(new Error("network down"));
    render(<DatasetsPage />);
    await waitFor(() => expect(screen.getByText(/network down/)).toBeInTheDocument());
  });
});
