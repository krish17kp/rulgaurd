import { PredictRulResponse } from "@/lib/api";

const LEVEL_STYLE: Record<string, string> = {
  HIGH: "border-green-300 bg-green-50 text-green-800 dark:border-green-900 dark:bg-green-950 dark:text-green-300",
  MEDIUM: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200",
  LOW: "border-red-300 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300",
};

/**
 * Shown alongside a RUL prediction (/predict and /upload FEMTO mode) -
 * real model-domain compatibility (applicability.py), not just a
 * sampling-rate/structural check. A HIGH-applicability prediction and a
 * MEDIUM one look identical as numbers; this is what tells them apart.
 */
export function ApplicabilityNote({ result }: { result: PredictRulResponse }) {
  if (!result.applicability_level) {
    return (
      <p className="mt-3 text-xs text-zinc-500">
        Model applicability could not be assessed (reference data unavailable) - this result
        reflects the prediction only, not a domain-fit check.
      </p>
    );
  }
  const style = LEVEL_STYLE[result.applicability_level] ?? LEVEL_STYLE.MEDIUM;
  return (
    <div className={`mt-3 rounded-lg border p-3 text-xs ${style}`}>
      <p className="font-medium">
        Model applicability: {result.applicability_level}
        {result.applicability_shift_ratio !== null &&
          ` (${result.applicability_shift_ratio.toFixed(2)}x the in-domain reference)`}
      </p>
      {result.applicability_reasons.length > 0 && (
        <ul className="mt-1 list-inside list-disc">
          {result.applicability_reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
