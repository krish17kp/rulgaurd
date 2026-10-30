import { HealthQuality } from "@/lib/api";

const RATING_TEXT: Record<HealthQuality["rating"], string> = {
  strong: "Strong: health falls steadily as the bearings run, so the rating tracks wear well.",
  moderate: "Moderate: health mostly falls over time, but some bearings are noisy or flat.",
  weak: "Weak: health does not fall consistently over time, so read the rating with care.",
  insufficient: "Not enough recordings to judge.",
};

const pct = (v: number) => `${Math.round(v * 100)}%`;

/** How far to trust the health rating, measured on the uploaded data itself. */
export function HealthQualityCard({ quality }: { quality: HealthQuality }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface p-5 text-sm">
      <h2 className="text-base font-semibold">How reliable is this health rating?</h2>
      <p className={`mt-1 ${quality.rating === "strong" ? "" : "text-caution"}`}>{RATING_TEXT[quality.rating]}</p>
      {quality.rating === "insufficient" ? (
        <p className="mt-1 text-foreground-muted">{quality.note}</p>
      ) : (
        <>
          <dl className="mt-3 grid gap-2 sm:grid-cols-3">
            <div>
              <dt className="text-foreground-muted">Trend with time</dt>
              <dd className="tabular-nums">{quality.trend!.toFixed(2)}</dd>
            </div>
            <div>
              <dt className="text-foreground-muted">Smoothness</dt>
              <dd className="tabular-nums">{pct(quality.smoothness!)}</dd>
            </div>
            <div>
              <dt className="text-foreground-muted">Agreement at failure</dt>
              <dd className="tabular-nums">
                {quality.prognosability != null ? pct(quality.prognosability) : "unknown, no failure points"}
              </dd>
            </div>
          </dl>
          <p className="mt-3 text-xs text-foreground-muted">
            Trend is how strongly health falls as time passes (1 = always falls, 0 = no link, below 0 = rises), averaged
            over {quality.n_bearings} bearing(s); strong from {quality.thresholds!.strong}, moderate from{" "}
            {quality.thresholds!.moderate}. Smoothness is how rarely it jumps back up.
            {quality.end_of_life_known
              ? " Agreement at failure is how similar the final health value is across bearings."
              : " This dataset has no known failure points, so accuracy against real failures can't be measured, only consistency."}
          </p>
          {quality.weak_bearings!.length > 0 && (
            <p className="mt-2 text-xs text-caution">
              Health does not fall clearly for: <span className="font-mono">{quality.weak_bearings!.join(", ")}</span>
            </p>
          )}
        </>
      )}
    </div>
  );
}
