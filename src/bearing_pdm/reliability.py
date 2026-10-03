"""Reliability information for one RUL prediction (Goal 21, docs/prediction-reliability.md).

Assembled ONLY from assets the project already produces; nothing is fitted
here and no score is invented:

1. held-out error    leave-one-bearing-out statistics for the served model,
                     read verbatim from reports/metrics/rul_evaluation.json
                     (scripts/evaluate_models.py).
2. tree disagreement std of the ExtraTrees' per-tree predictions for THIS row
                     (uncertainty.tree_predictions) - a diagnostic, not a
                     calibrated confidence (see uncertainty.py).
3. interval          normalised split-conformal interval, only when the cached
                     cross_domain_bundle.joblib holds a calibrator fitted for
                     exactly the served model, and only when applicability is
                     HIGH (the coverage target assumes the row is exchangeable
                     with the FEMTO calibration bearings).
4. applicability     applicability.assess of the submitted row against the
                     bundle's cached ApplicabilityModel.

Every unavailable part is None together with a plain-language reason. No field
is a percentage, a probability or a "confidence score".
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from bearing_pdm.applicability import HIGH, ApplicabilityModel, assess
from bearing_pdm.uncertainty import ConformalCalibrator, conformal_interval, tree_predictions

EVALUATION_SOURCE = "reports/metrics/rul_evaluation.json"
BUNDLE_SOURCE = "artifacts/models/cross_domain_bundle.joblib"
# The bundle entry whose model is the served FEMTO seconds-target ExtraTrees
# (experiments.cross_dataset: "the raw one IS the committed artifact").
BUNDLE_ENTRY = "raw_seconds"
TRAINED_DATASET_ID = "femto"
# A bundled model counts as the served one only if it reproduces the served
# prediction for this row; the tolerance only absorbs float summation order.
SAME_MODEL_REL_TOL = 1e-9

_OVERALL_FIELDS = ("mae_seconds", "rmse_seconds", "median_abs_error_seconds",
                   "mean_signed_error_seconds")


def _finite(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def held_out_error(path: Path, model_name: str) -> dict[str, Any]:
    """Leave-one-bearing-out error of `model_name` from rul_evaluation.json."""
    block: dict[str, Any] = {
        "available": False, "reason": None, "source": EVALUATION_SOURCE,
        "method": "leave-one-bearing-out over the FEMTO learning bearings",
        "model": model_name, "unit": "seconds",
    }
    if not path.exists():
        block["reason"] = (f"{EVALUATION_SOURCE} is not present; run scripts/evaluate_models.py "
                           "to produce held-out error statistics. None are reported without it.")
        return block
    try:
        data = json.loads(path.read_text())
        overall = data["femto_lobo_overall_by_model"][model_name]
        rows = [r for r in data["femto_lobo"] if r.get("model") == model_name]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        block["reason"] = (f"{EVALUATION_SOURCE} does not contain FEMTO leave-one-bearing-out "
                           f"results for {model_name!r}.")
        return block

    values = [overall.get(k) for k in (*_OVERALL_FIELDS, "n")] if isinstance(overall, dict) else []
    per_bearing = [
        {"held_out_bearing": str(r["held_out_bearing"]), "mae_seconds": float(r["mae_seconds"]),
         "n": int(r["n"])}
        for r in rows
        if "held_out_bearing" in r and _finite(r.get("mae_seconds")) and _finite(r.get("n"))
    ]
    if not values or not all(_finite(v) for v in values) or not per_bearing \
            or len(per_bearing) != len(rows):
        block["reason"] = (f"{EVALUATION_SOURCE} has incomplete or non-finite leave-one-bearing-out "
                           f"statistics for {model_name!r}; none are reported.")
        return block

    maes = [r["mae_seconds"] for r in per_bearing]
    block.update(
        available=True,
        n_held_out_rows=int(overall["n"]),
        n_held_out_bearings=len(per_bearing),
        **{k: float(overall[k]) for k in _OVERALL_FIELDS},
        per_bearing=per_bearing,
        per_bearing_mae_seconds_min=float(min(maes)),
        per_bearing_mae_seconds_max=float(max(maes)),
        note=("Pooled error over every held-out row, and each held-out bearing's own MAE. "
              "It describes the training procedure on FEMTO bearings it did not see, not an "
              "error bound for this particular prediction. mean_signed_error_seconds > 0 means "
              "the model over-estimated remaining life on average."),
    )
    return block


def tree_disagreement(forest: Any, x: pd.DataFrame) -> tuple[dict[str, Any], float | None]:
    """(block, sigma): spread of the per-tree predictions for the single row `x`."""
    block: dict[str, Any] = {
        "available": False, "reason": None, "kind": "diagnostic_not_calibrated",
        "unit": "seconds", "method": "std of the ExtraTrees' per-tree predictions "
                                    "(uncertainty.tree_predictions)",
    }
    if not getattr(forest, "estimators_", None):
        block["reason"] = "The served model does not expose per-tree predictions."
        return block, None
    per_tree = tree_predictions(forest, x)[:, 0]
    sigma = float(per_tree.std())
    if not math.isfinite(sigma):
        block["reason"] = "Per-tree predictions are not finite for this row."
        return block, None
    block.update(
        available=True, std_seconds=sigma, n_trees=int(len(per_tree)),
        note=("How much the trees disagree on this row. Every tree was fit on the same "
              "training bearings, so they can all agree and all be wrong on an unfamiliar "
              "bearing: this is a diagnostic, not a calibrated confidence or an error bound."),
    )
    return block, sigma


def applicability(bundle: Any, feature_columns: list[str], features: dict[str, float],
                  single_recording: bool = False) -> tuple[dict[str, Any] | None, str | None]:
    """applicability.assess of the submitted row against the bundle's cached model.

    `single_recording` is passed straight to assess(): the API scores one
    acquisition's row, so it uses the single-row missing-feature semantics the
    API's own applicability gate uses - one response never reports two
    different levels for the same row."""
    entry = bundle.get(BUNDLE_ENTRY) if isinstance(bundle, dict) else None
    app_model = entry.get("applicability") if isinstance(entry, dict) else None
    if bundle is None:
        return None, f"{BUNDLE_SOURCE} is not present, so no cached applicability model exists."
    if not isinstance(app_model, ApplicabilityModel) or entry.get("train") != TRAINED_DATASET_ID:
        return None, (f"{BUNDLE_SOURCE} has no FEMTO-fit applicability model for the served "
                      "model; applicability is not computed.")
    if list(app_model.feature_columns) != list(feature_columns):
        return None, ("The cached applicability model was fit on a different feature schema than "
                      "the served model; it is not applied.")
    row = pd.DataFrame([{c: features.get(c, np.nan) for c in app_model.feature_columns}],
                       dtype=float)
    result = assess(row, app_model, single_recording=single_recording)
    return {
        "level": result["level"],
        "shift_ratio": result["shift_ratio"],
        "median_distance": result["median_distance"],
        "in_domain_distance": result["in_domain_distance"],
        "reasons": result["reasons"],
        "missing_features": result["missing_features"],
        "method": ("applicability.assess: kNN distance of this row to the FEMTO training rows "
                   "in robust-z units, divided by the largest leave-one-bearing-out in-domain "
                   "distance (shift_ratio; dimensionless). HIGH <= 1.0 < MEDIUM <= 2.0 < LOW; "
                   "features not submitted count as unavailable."),
        "source": BUNDLE_SOURCE,
        "checks_not_performed": [
            "operating metadata (sampling rate, speed, radial load): not part of this request",
            "life time-scale (elapsed time vs the longest training life): elapsed time is not "
            "part of this request",
        ],
    }, None


def interval(bundle: Any, served: Any, x: pd.DataFrame, prediction: float,
             sigma: float | None, applicability_block: dict[str, Any] | None,
             ) -> tuple[dict[str, Any] | None, str | None]:
    """Conformal interval from the cached calibrator, or (None, reason)."""
    if bundle is None:
        return None, (f"{BUNDLE_SOURCE} is not present, so no fitted conformal calibrator is "
                      "available. The API never fits one.")
    entry = bundle.get(BUNDLE_ENTRY) if isinstance(bundle, dict) else None
    calibrators = entry.get("calibrators") if isinstance(entry, dict) else None
    cal = calibrators.get("conformal") if isinstance(calibrators, dict) else None
    if not isinstance(cal, ConformalCalibrator) or entry.get("train") != TRAINED_DATASET_ID:
        return None, f"{BUNDLE_SOURCE} holds no FEMTO-fit conformal calibrator."
    bundled = entry.get("model")
    if (list(getattr(bundled, "feature_columns", ())) != list(served.feature_columns)
            or not hasattr(bundled, "model")
            or not math.isclose(float(bundled.model.predict(x)[0]), prediction,
                                rel_tol=SAME_MODEL_REL_TOL)):
        return None, ("The cached calibrator belongs to a different model than the one served "
                      "(its model does not reproduce this prediction); it is not applied.")
    if cal.normalized and sigma is None:
        return None, "The calibrator scales by tree disagreement, which is unavailable here."
    if applicability_block is None:
        return None, ("Applicability could not be computed, so it cannot be checked that this "
                      "row resembles the calibration bearings; no interval is reported.")
    if applicability_block["level"] != HIGH:
        # MEDIUM is served as an experimental result (RETRAIN_REQUIRED) and LOW is
        # suppressed altogether; neither is evidence of exchangeability.
        return None, (f"Applicability is {applicability_block['level']} (not inside the "
                      "training distribution). The conformal coverage target assumes the row "
                      "is exchangeable with the FEMTO calibration bearings, so no interval is "
                      "reported.")
    lo, hi = conformal_interval(np.array([prediction]), np.array([sigma or 0.0]), cal,
                                lower_bound=0.0)
    lower, upper = float(lo[0]), float(hi[0])
    return {
        "lower_seconds": lower, "upper_seconds": upper,
        "lower_hours": lower / 3600.0, "upper_hours": upper / 3600.0,
        "unit": "seconds",
        "method": ("normalised split-conformal (uncertainty.conformal_interval)" if cal.normalized
                   else "absolute-residual split-conformal (uncertainty.conformal_interval)"),
        "target_miscoverage_alpha": float(cal.alpha),
        "n_calibration_bearings": int(cal.n_calibration_bearings),
        "n_calibration_rows": int(cal.n_calibration_rows),
        "source": f"{BUNDLE_SOURCE} ({BUNDLE_ENTRY} calibrator, fit offline on out-of-fold "
                  "predictions for FEMTO learning bearings)",
        "note": ("Calibrated so that, across bearings exchangeable with the FEMTO calibration "
                 "bearings, at most a fraction alpha of true RULs fall outside - a marginal "
                 "property of the method over few bearings, not a probability that this "
                 "prediction is right. Lower bound clipped at 0 s."),
    }, None


def build(evaluation_path: Path, bundle: Any, served: Any, model_name: str,
          x: pd.DataFrame, features: dict[str, float], prediction: float,
          single_recording: bool = False) -> dict[str, Any]:
    """The full reliability block for one prediction."""
    held_out = held_out_error(evaluation_path, model_name)
    trees, sigma = tree_disagreement(getattr(served, "model", None), x)
    app, app_reason = applicability(bundle, list(served.feature_columns), features,
                                    single_recording=single_recording)
    conf, conf_reason = interval(bundle, served, x, prediction, sigma, app)
    return {
        "held_out_error": held_out,
        "tree_disagreement": trees,
        "interval": conf, "interval_reason": conf_reason,
        "applicability": app, "applicability_reason": app_reason,
    }


def unavailable(reason: str) -> dict[str, Any]:
    """Same shape as build() with every part withheld, for an unexpected failure."""
    return {
        "held_out_error": {"available": False, "reason": reason, "source": EVALUATION_SOURCE,
                           "unit": "seconds"},
        "tree_disagreement": {"available": False, "reason": reason,
                              "kind": "diagnostic_not_calibrated", "unit": "seconds"},
        "interval": None, "interval_reason": reason,
        "applicability": None, "applicability_reason": reason,
    }
