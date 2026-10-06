import { ApiError } from "@/lib/api";

/** True when the backend intentionally withheld a prediction because the
 * input doesn't resemble the training population (api.py's APPLICABILITY_LOW
 * on /predict/rul* - raised as a 422, not a transient failure). Checked by
 * `code` first (stable), falling back to the detail text for older backends
 * that don't send `code` yet. */
export function isSuppressedApplicability(err: ApiError): boolean {
  return err.code === "APPLICABILITY_LOW" || err.detail.includes("RUL suppressed");
}

/**
 * Shown instead of the generic error box when a prediction was withheld by
 * backend policy (LOW applicability / RETRAIN_REQUIRED), not because the
 * request failed. Renders only the backend's own detail text - no fabricated
 * confidence value, no retry (retrying the same signal returns the same
 * policy outcome).
 */
export function SuppressedResultNotice({ detail }: { detail: string }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-caution/40 bg-caution/10 p-4 text-sm text-caution">
      <p className="font-semibold">Prediction withheld — signal outside the training distribution</p>
      <p>
        This is not a failed request. The uploaded signal differs substantially from the data
        the model was trained on, so the Remaining Useful Life estimate is intentionally
        suppressed rather than guessed, per the backend&apos;s applicability policy.
      </p>
      <p className="text-xs opacity-90">{detail}</p>
    </div>
  );
}
