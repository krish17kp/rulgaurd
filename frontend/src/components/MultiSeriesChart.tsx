"use client";

/** Inline-SVG multi-line chart (no charting dependency) for comparing several
 * real numeric series against one shared x-axis - e.g. reference/transparent/
 * pca HI, or actual vs. held-out-predicted RUL. Downsamples only for
 * rendering; values are never fabricated or resampled numerically. */
export interface ChartSeries {
  label: string;
  color: string;
  /** x,y pairs; null y values are skipped (gap in the line), never 0-filled. */
  points: Array<{ x: number; y: number | null }>;
}

type Pt = { x: number; y: number | null };

function downsamplePoints<T>(points: T[], maxPoints: number): T[] {
  if (points.length <= maxPoints) return points;
  const step = points.length / maxPoints;
  const out: T[] = [];
  for (let i = 0; i < maxPoints; i++) out.push(points[Math.floor(i * step)]);
  return out;
}

/** Split a line at null values and at x gaps much wider than the usual spacing (e.g.
 * recordings missing because an archive part was not uploaded), so the chart never draws a
 * straight line across data that does not exist. Returns the segments and the gap spans. */
export function splitAtGaps(points: Pt[], gapFactor = 10) {
  const xs = points.filter((p) => p.y !== null).map((p) => p.x);
  const steps = xs.slice(1).map((x, i) => x - xs[i]).filter((d) => d > 0).sort((a, b) => a - b);
  const median = steps.length ? steps[Math.floor(steps.length / 2)] : 0;
  const segments: Array<Array<{ x: number; y: number }>> = [];
  const gaps: Array<[number, number]> = [];
  let current: Array<{ x: number; y: number }> = [];
  for (const p of points) {
    if (p.y === null) {
      if (current.length) segments.push(current);
      current = [];
      continue;
    }
    const prev = current[current.length - 1];
    if (prev && median > 0 && p.x - prev.x > gapFactor * median) {
      segments.push(current);
      gaps.push([prev.x, p.x]);
      current = [];
    }
    current.push({ x: p.x, y: p.y });
  }
  if (current.length) segments.push(current);
  return { segments, gaps };
}

export function MultiSeriesChart({
  series,
  width = 640,
  height = 220,
  xLabel,
  yLabel,
  referenceLine,
  mode = "line",
  markers = [],
}: {
  series: ChartSeries[];
  width?: number;
  height?: number;
  xLabel?: string;
  yLabel?: string;
  /** Optional y=x style reference line, e.g. perfect actual==predicted. */
  referenceLine?: boolean;
  /** "line" connects points (trajectories); "points" draws dots only (scatter). */
  mode?: "line" | "points";
  /** Labelled vertical lines, e.g. where the degradation stage changes. */
  markers?: Array<{ x: number; label: string }>;
}) {
  const downsampled = series.map((s) => ({ ...s, points: downsamplePoints(s.points, 1200) }));
  // Lines are split before downsampling so a gap can never be sampled away.
  const lines = series.map((s) => {
    const { segments, gaps } = splitAtGaps(s.points);
    const total = segments.reduce((n, seg) => n + seg.length, 0) || 1;
    return {
      ...s,
      gaps,
      segments: segments.map((seg) => downsamplePoints(seg, Math.max(2, Math.round((1200 * seg.length) / total)))),
    };
  });
  const allX = downsampled.flatMap((s) => s.points.map((p) => p.x));
  const allY = downsampled.flatMap((s) => s.points.map((p) => p.y).filter((y): y is number => y !== null));
  if (allX.length === 0 || allY.length === 0) {
    return <p className="text-xs text-foreground-muted">No data to plot.</p>;
  }
  const xMin = Math.min(...allX);
  const xMax = Math.max(...allX);
  const yMin = Math.min(0, ...allY);
  const yMax = Math.max(...allY);
  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;
  const pad = 28;
  const toX = (x: number) => pad + ((x - xMin) / xRange) * (width - 2 * pad);
  const toY = (y: number) => height - pad - ((y - yMin) / yRange) * (height - 2 * pad);

  return (
    <div className="flex flex-col gap-2">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label={yLabel ?? "trajectory chart"}>
        <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} stroke="currentColor" strokeOpacity={0.2} />
        <line x1={pad} y1={pad} x2={pad} y2={height - pad} stroke="currentColor" strokeOpacity={0.2} />
        {referenceLine && (
          <line
            x1={toX(xMin)} y1={toY(xMin)} x2={toX(xMax)} y2={toY(xMax)}
            stroke="currentColor" strokeOpacity={0.25} strokeDasharray="4 3"
          />
        )}
        {mode === "points"
          ? downsampled.map((s) =>
              s.points
                .filter((p): p is { x: number; y: number } => p.y !== null)
                .map((p, i) => (
                  <circle key={`${s.label}-${i}`} cx={toX(p.x)} cy={toY(p.y)} r={2} fill={s.color} fillOpacity={0.6} />
                ))
            )
          : lines.map((s) =>
              s.segments.map((seg, i) =>
                seg.length === 1 ? (
                  <circle key={`${s.label}-${i}`} cx={toX(seg[0].x)} cy={toY(seg[0].y)} r={1.5} fill={s.color} />
                ) : (
                  <polyline
                    key={`${s.label}-${i}`}
                    points={seg.map((p) => `${toX(p.x).toFixed(1)},${toY(p.y).toFixed(1)}`).join(" ")}
                    fill="none"
                    stroke={s.color}
                    strokeWidth={1.5}
                  />
                )
              )
            )}
        {mode === "line" &&
          lines.flatMap((s) =>
            s.gaps.map(([a, b], i) => {
              const x = toX(a);
              const w = toX(b) - x;
              return (
                <g key={`gap-${s.label}-${i}`}>
                  <rect x={x} y={pad} width={w} height={height - 2 * pad} fill="currentColor" fillOpacity={0.06} />
                  {w > 60 && (
                    <text x={x + w / 2} y={pad + 12} textAnchor="middle" fontSize="9" fill="currentColor" opacity={0.55}>
                      no recordings
                    </text>
                  )}
                </g>
              );
            })
          )}
        {markers.map((m) => (
          <g key={`${m.label}-${m.x}`}>
            <line x1={toX(m.x)} y1={pad} x2={toX(m.x)} y2={height - pad} stroke="currentColor" strokeOpacity={0.35} strokeDasharray="3 3" />
            <text x={toX(m.x) + 3} y={height - pad - 4} fontSize="9" fill="currentColor" opacity={0.7}>
              {m.label}
            </text>
          </g>
        ))}
        {xLabel && (
          <text x={width / 2} y={height - 4} textAnchor="middle" fontSize="10" fill="currentColor" opacity={0.6}>
            {xLabel}
          </text>
        )}
        {yLabel && (
          <text x={4} y={12} fontSize="10" fill="currentColor" opacity={0.6}>
            {yLabel}
          </text>
        )}
      </svg>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-foreground-muted">
        {series.map((s) => (
          <span key={s.label} className="flex items-center gap-1.5">
            <span className="inline-block size-2 rounded-full" style={{ backgroundColor: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
