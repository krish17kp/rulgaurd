import { describe, expect, it } from "vitest";
import { splitAtGaps } from "@/components/MultiSeriesChart";

describe("splitAtGaps", () => {
  it("breaks the line where recordings are missing and at nulls, never across them", () => {
    const pts: Array<{ x: number; y: number | null }> = [0, 1, 2, 3, 50, 51, 52].map((x) => ({ x, y: 1 }));
    pts.splice(6, 0, { x: 51.5, y: null });
    const { segments, gaps } = splitAtGaps(pts);
    expect(gaps).toEqual([[3, 50]]);
    expect(segments.map((s) => s.map((p) => p.x))).toEqual([[0, 1, 2, 3], [50, 51], [52]]);
  });

  it("leaves evenly spaced data as one segment", () => {
    const { segments, gaps } = splitAtGaps([0, 1, 2, 3].map((x) => ({ x, y: 0.5 })));
    expect(gaps).toEqual([]);
    expect(segments).toHaveLength(1);
  });
});
