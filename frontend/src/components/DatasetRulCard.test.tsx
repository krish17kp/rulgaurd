import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DatasetRulCard } from "@/components/DatasetRulCard";

const pt = (i: number) => ({
  sequence_index: i, elapsed_s: i * 3600, actual_rul_seconds: (4 - i) * 3600,
  predicted_rul_seconds: (4 - i) * 3000, rul_lo: 0, rul_hi: 20000, naive_rul_seconds: 7200,
});

describe("DatasetRulCard", () => {
  it("shows held-out accuracy against the average-life guess when validated", () => {
    render(
      <DatasetRulCard
        rul={{
          status: "validated", n_bearings: 3, min_bearings: 3, model: "ExtraTrees",
          mae_seconds: 1800, naive_mae_seconds: 3600, skill_vs_naive: 0.5, interval_coverage: 0.9,
          per_bearing: [{ bearing: "b1", n: 5, mae_seconds: 1800, naive_mae_seconds: 3600, coverage: 0.9, total_life_s: 14400 }],
          trajectories: { b1: [0, 1, 2, 3, 4].map(pt) },
          ends_healthy: ["b3"],
        }}
      />
    );
    expect(screen.getByText(/RUL shown/)).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getAllByText("0.50 h").length).toBeGreaterThan(0);
    expect(screen.getByText("b3")).toBeInTheDocument();
  });

  it("explains why RUL is withheld", () => {
    render(<DatasetRulCard rul={{ status: "too_few_bearings", n_bearings: 2, min_bearings: 3, model: "x", ends_healthy: [] }} />);
    expect(screen.getByText(/fewer than 3 bearings ran until failure/)).toBeInTheDocument();
  });
});
