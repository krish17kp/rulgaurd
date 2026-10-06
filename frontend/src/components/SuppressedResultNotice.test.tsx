import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api";
import { SuppressedResultNotice, isSuppressedApplicability } from "./SuppressedResultNotice";

describe("isSuppressedApplicability", () => {
  it("is true when the backend sends the APPLICABILITY_LOW code", () => {
    expect(isSuppressedApplicability(new ApiError(422, "whatever", false, "APPLICABILITY_LOW"))).toBe(true);
  });

  it("is true for older backends without `code`, by detail text", () => {
    expect(isSuppressedApplicability(new ApiError(422, "RUL suppressed: model applicability is LOW", false))).toBe(
      true
    );
  });

  it("is false for an unrelated error", () => {
    expect(isSuppressedApplicability(new ApiError(500, "backend exploded", true))).toBe(false);
  });
});

describe("SuppressedResultNotice", () => {
  it("states the policy outcome plainly and shows the backend's own detail text", () => {
    render(<SuppressedResultNotice detail="RUL suppressed: model applicability is LOW (shift ratio 9.10x)." />);
    expect(screen.getByText(/not a failed request/i)).toBeInTheDocument();
    expect(screen.getByText(/intentionally suppressed/i)).toBeInTheDocument();
    expect(screen.getByText(/shift ratio 9\.10x/)).toBeInTheDocument();
  });
});
