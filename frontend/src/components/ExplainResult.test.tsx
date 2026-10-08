import { describe, expect, it } from "vitest";
import { stripMarkdown } from "./ExplainResult";

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
