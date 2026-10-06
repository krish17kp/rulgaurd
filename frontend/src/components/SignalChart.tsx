"use client";

/** Minimal inline-SVG line chart for real numeric arrays (no charting
 * dependency - a polyline is all this needs). Downsamples only for
 * rendering; the values plotted are never reconstructed/fabricated. */
function downsample(values: number[], maxPoints: number): number[] {
  if (values.length <= maxPoints) return values;
  const step = values.length / maxPoints;
  const out: number[] = [];
  for (let i = 0; i < maxPoints; i++) out.push(values[Math.floor(i * step)]);
  return out;
}

export function SignalChart({
  values,
  xValues,
  width = 600,
  height = 160,
  color = "#60a5fa",
  xLabel,
  yLabel,
}: {
  values: number[];
  xValues?: number[];
  width?: number;
  height?: number;
  color?: string;
  xLabel?: string;
  yLabel?: string;
}) {
  const plotted = downsample(values, 1200);
  const xs = xValues ? downsample(xValues, 1200) : plotted.map((_, i) => i);
  const min = Math.min(...plotted);
  const max = Math.max(...plotted);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const range = max - min || 1;
  const xRange = xMax - xMin || 1;
  const pad = 24;
  const toX = (x: number) => pad + ((x - xMin) / xRange) * (width - 2 * pad);
  const toY = (v: number) => height - pad - ((v - min) / range) * (height - 2 * pad);
  const points = plotted.map((v, i) => `${toX(xs[i]).toFixed(1)},${toY(v).toFixed(1)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label={yLabel ?? "signal chart"}>
      <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} stroke="currentColor" strokeOpacity={0.2} />
      <line x1={pad} y1={pad} x2={pad} y2={height - pad} stroke="currentColor" strokeOpacity={0.2} />
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.25} />
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
  );
}
