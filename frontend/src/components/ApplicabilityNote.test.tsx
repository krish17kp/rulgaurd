import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApplicabilityNote } from "./ApplicabilityNote";
import type { PredictRulResponse } from "@/lib/api";

function result(overrides: Partial<PredictRulResponse>): PredictRulResponse {
  return {
    model_name: "extra_trees",
    rul_seconds: 3600,
    rul_hours: 1,
    features_used: [],
    features_missing: [],
    compatibility: "FULLY_SUPPORTED",
    applicability_level: null,
    applicability_shift_ratio: null,
    applicability_reasons: [],
    ...overrides,
  };
}

describe("ApplicabilityNote", () => {
  it("shows a degrade-honestly message when applicability could not be assessed", () => {
    render(<ApplicabilityNote result={result({ applicability_level: null })} />);
    expect(screen.getByText(/could not be assessed/i)).toBeInTheDocument();
  });

  it("renders HIGH applicability without a shift-ratio caveat standing out as a warning", () => {
    render(<ApplicabilityNote result={result({ applicability_level: "HIGH", applicability_shift_ratio: 1.02 })} />);
    expect(screen.getByText(/Model applicability: HIGH/)).toBeInTheDocument();
    expect(screen.getByText(/1\.02x the in-domain reference/)).toBeInTheDocument();
  });

  it("surfaces MEDIUM applicability as a warning, not a rejection, with its reasons", () => {
    render(
      <ApplicabilityNote
        result={result({
          applicability_level: "MEDIUM",
          applicability_shift_ratio: 2.4,
          applicability_reasons: ["feature distribution shift (2.40x the in-domain reference)"],
        })}
      />
    );
    expect(screen.getByText(/Model applicability: MEDIUM/)).toBeInTheDocument();
    expect(screen.getByText(/feature distribution shift/)).toBeInTheDocument();
  });

  it("surfaces LOW applicability (out-of-domain) distinctly from MEDIUM", () => {
    render(
      <ApplicabilityNote
        result={result({
          applicability_level: "LOW",
          applicability_shift_ratio: 9.1,
          applicability_reasons: ["feature distribution shift (9.10x the in-domain reference)"],
        })}
      />
    );
    const note = screen.getByText(/Model applicability: LOW/);
    expect(note).toBeInTheDocument();
    // LOW uses the red/rejection styling, not the amber MEDIUM styling.
    expect(note.closest("div")).toHaveClass("border-red-300");
  });
});
