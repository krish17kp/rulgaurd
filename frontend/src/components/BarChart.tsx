"use client";

/** Inline-SVG grouped bar chart (no charting dependency) for comparing a
 * small number of named series across categories, e.g. per-bearing MAE
 * ExtraTrees vs naive. Values are plotted exactly as given - no smoothing,
 * no fabricated bars. */
export interface BarSeries {
  label: string;
  color: string;
  values: number[];
}

export function BarChart({
  categories,
  series,
  width = 640,
  height = 220,
  yLabel,
  zeroLine = true,
}: {
  categories: string[];
  series: BarSeries[];
  width?: number;
  height?: number;
  yLabel?: string;
  /** Draw a line at y=0 - useful for signed-error charts with negative bars. */
  zeroLine?: boolean;
}) {
  const allValues = series.flatMap((s) => s.values);
  if (categories.length === 0 || allValues.length === 0) {
    return <p className="text-xs text-foreground-muted">No data to plot.</p>;
  }
  const yMin = Math.min(0, ...allValues);
  const yMax = Math.max(0, ...allValues);
  const yRange = yMax - yMin || 1;
  const padLeft = 36;
  const padBottom = 28;
  const padTop = 8;
  const plotW = width - padLeft - 8;
  const plotH = height - padBottom - padTop;
  const toY = (v: number) => padTop + plotH - ((v - yMin) / yRange) * plotH;
  const zeroY = toY(0);
  const groupWidth = plotW / categories.length;
  const barWidth = groupWidth / (series.length + 1);

  return (
    <div className="flex flex-col gap-2">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label={yLabel ?? "bar chart"}>
        <line x1={padLeft} y1={zeroY} x2={width - 8} y2={zeroY} stroke="currentColor" strokeOpacity={0.3} />
        {zeroLine && yMin < 0 && (
          <line x1={padLeft} y1={toY(yMin)} x2={padLeft} y2={toY(yMax)} stroke="currentColor" strokeOpacity={0.15} />
        )}
        {categories.map((cat, ci) => (
          <g key={cat}>
            {series.map((s, si) => {
              const v = s.values[ci] ?? 0;
              const x = padLeft + ci * groupWidth + (si + 0.5) * barWidth;
              const y0 = toY(0);
              const y1 = toY(v);
              const top = Math.min(y0, y1);
              const h = Math.abs(y1 - y0);
              return (
                <rect
                  key={s.label}
                  x={x - barWidth / 2}
                  y={top}
                  width={Math.max(barWidth - 2, 1)}
                  height={Math.max(h, 0.5)}
                  fill={s.color}
                />
              );
            })}
            <text
              x={padLeft + (ci + 0.5) * groupWidth}
              y={height - 6}
              textAnchor="middle"
              fontSize="9"
              fill="currentColor"
              opacity={0.6}
            >
              {cat}
            </text>
          </g>
        ))}
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
