import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HealthQualityCard } from "@/components/HealthQualityCard";

const base = { n_bearings: 3, trend: 0.64, smoothness: 0.52, thresholds: { strong: 0.7, moderate: 0.4 } };

describe("HealthQualityCard", () => {
  it("names the weak bearings and says accuracy can't be measured without failure points", () => {
    render(
      <HealthQualityCard
        quality={{ ...base, rating: "moderate", prognosability: null, end_of_life_known: false, weak_bearings: ["b2"] }}
      />
    );
    expect(screen.getByText(/^Moderate:/)).toBeInTheDocument();
    expect(screen.getByText("0.64")).toBeInTheDocument();
    expect(screen.getByText("unknown, no failure points")).toBeInTheDocument();
    expect(screen.getByText(/accuracy against real failures can't be measured/)).toBeInTheDocument();
    expect(screen.getByText("b2")).toBeInTheDocument();
  });

  it("shows agreement at failure when end of life is known", () => {
    render(
      <HealthQualityCard
        quality={{ ...base, rating: "strong", prognosability: 0.81, end_of_life_known: true, weak_bearings: [] }}
      />
    );
    expect(screen.getByText("81%")).toBeInTheDocument();
    expect(screen.queryByText(/does not fall clearly/)).not.toBeInTheDocument();
  });
});
