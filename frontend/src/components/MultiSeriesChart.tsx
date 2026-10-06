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

function downsamplePoints(points: Array<{ x: number; y: number | null }>, maxPoints: number) {
  if (points.length <= maxPoints) return points;
  const step = points.length / maxPoints;
  const out: Array<{ x: number; y: number | null }> = [];
  for (let i = 0; i < maxPoints; i++) out.push(points[Math.floor(i * step)]);
  return out;
}

export function MultiSeriesChart({
  series,
  width = 640,
  height = 220,
  xLabel,
  yLabel,
  referenceLine,
}: {
  series: ChartSeries[];
  width?: number;
  height?: number;
  xLabel?: string;
  yLabel?: string;
  /** Optional y=x style reference line, e.g. perfect actual==predicted. */
  referenceLine?: boolean;
}) {
  const downsampled = series.map((s) => ({ ...s, points: downsamplePoints(s.points, 1200) }));
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
        {downsampled.map((s) => {
          // Break the polyline at null gaps instead of drawing through them.
          const segments: string[] = [];
          let current: string[] = [];
          for (const p of s.points) {
            if (p.y === null) {
              if (current.length) segments.push(current.join(" "));
              current = [];
              continue;
            }
            current.push(`${toX(p.x).toFixed(1)},${toY(p.y).toFixed(1)}`);
          }
          if (current.length) segments.push(current.join(" "));
          return segments.map((points, i) => (
            <polyline key={`${s.label}-${i}`} points={points} fill="none" stroke={s.color} strokeWidth={1.5} />
          ));
        })}
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
