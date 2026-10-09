import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { stripMarkdown, ExplainResult } from "./ExplainResult";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, explainPrediction: vi.fn() };
});

import { explainPrediction } from "@/lib/api";

const RESULT = {
  rul_seconds: 4610,
  rul_hours: 1.28,
  applicability_level: "HIGH" as const,
  compatibility: "FULLY_SUPPORTED" as const,
};

describe("stripMarkdown", () => {
  it("removes bold, headings, bullets, and lettered points", () => {
    const raw =
      "## Summary\n**Model result (a):** RUL is 4610 seconds.\n(b) Evidence: - supports this.";
    const clean = stripMarkdown(raw);
    expect(clean).not.toContain("**");
    expect(clean).not.toContain("##");
    expect(clean).not.toMatch(/\(a\)|\(b\)/);
    expect(clean).toContain("4610 seconds");
  });

  it("removes inline citation brackets some providers inject, found live on Preview", () => {
    const raw =
      "RUL was suppressed because applicability is LOW【Dataset Compatibility | chunk doc_x:0012:abc123】.";
    const clean = stripMarkdown(raw);
    expect(clean).not.toContain("【");
    expect(clean).not.toContain("】");
    expect(clean).toContain("RUL was suppressed because applicability is LOW");
  });

  it("leaves plain text untouched", () => {
    const plain = "RUL is 4610 seconds, about 1.28 hours, applicability is high.";
    expect(stripMarkdown(plain)).toBe(plain);
  });
});

describe("ExplainResult", () => {
  it("renders a provider-backed explanation and its citations without exposing provider identity", async () => {
    vi.mocked(explainPrediction).mockResolvedValue({
      explanation: "RUL is suppressed because applicability is LOW.",
      citations: [
        { chunk_id: "doc_x:0012:abc123", document_title: "Dataset Compatibility", source: "docs/dataset-compatibility.md", relevance_score: 0.91 },
      ],
      status: "complete",
      provider: "openrouter",
      fallback_used: false,
    });
    render(<ExplainResult result={RESULT} />);

    await userEvent.click(screen.getByRole("button", { name: /explain this result/i }));

    await waitFor(() => expect(screen.getByText(/RUL is suppressed/)).toBeInTheDocument());
    expect(screen.getByText("Dataset Compatibility (relevance 0.91)")).toBeInTheDocument();
    // Provider identity is an implementation detail, not shown to the user.
    expect(screen.queryByText(/openrouter/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/provider/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/doc_x:0012:abc123/)).not.toBeInTheDocument();
  });

  it("renders the deterministic fallback explanation the same way as a provider response", async () => {
    vi.mocked(explainPrediction).mockResolvedValue({
      explanation: "Deterministic summary: RUL is 4610 seconds, applicability HIGH.",
      citations: [],
      status: "complete",
      provider: "deterministic",
      fallback_used: true,
    });
    render(<ExplainResult result={RESULT} />);

    await userEvent.click(screen.getByRole("button", { name: /explain this result/i }));

    await waitFor(() => expect(screen.getByText(/Deterministic summary/)).toBeInTheDocument());
    expect(screen.queryByText(/fallback/i)).not.toBeInTheDocument();
  });

  it("shows a retryable error when the provider request fails, without altering the displayed result", async () => {
    vi.mocked(explainPrediction).mockRejectedValueOnce(new Error("network down"));
    render(<ExplainResult result={RESULT} />);

    await userEvent.click(screen.getByRole("button", { name: /explain this result/i }));

    await waitFor(() => expect(screen.getByText(/network down/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    // The prop this component was given is untouched by a failed explanation -
    // ExplainResult never writes back into the caller's result object.
    expect(RESULT.rul_seconds).toBe(4610);
  });
});
