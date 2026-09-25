"""RUL uncertainty: tree disagreement (diagnostic) and conformal intervals.

1. Tree disagreement. An ExtraTrees prediction is the mean of its trees; the
   spread of the individual trees says how much the ensemble disagrees. It is a
   useful *diagnostic* but NOT a calibrated confidence: every tree was fit on
   the same training bearings, so all trees can agree and all be wrong on a
   bearing unlike any of them. experiments.bearing_metrics measures exactly that.

2. Normalised split-conformal regression (Lei et al. 2018; Papadopoulos 2008):

       score_i = |y_i - yhat_i| / (sigma_i + beta)     on a CALIBRATION set
       q       = weighted (1 - alpha) quantile of the scores
       interval = yhat +/- q * (sigma + beta)

   sigma is the tree spread, so intervals widen where trees disagree. The
   calibration set must be disjoint from both the training data of the model
   and the bearing being evaluated - callers build it from out-of-fold
   predictions on OTHER bearings (experiments.py). The coverage guarantee
   needs calibration and test bearings to be exchangeable; across domains they
   are not, and the measured coverage there is the honest result, not a bug.

   Rows of one bearing are strongly autocorrelated, so each calibration
   bearing gets equal total weight (1/n_rows per row) - otherwise Bearing1_1's
   2,803 acquisitions would set the quantile on their own.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def tree_predictions(forest, x: pd.DataFrame | np.ndarray) -> np.ndarray:
    """(n_trees, n_rows) predictions of every estimator in a fitted forest."""
    x = np.asarray(x, dtype=float)
    return np.stack([tree.predict(x) for tree in forest.estimators_])


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cum = np.cumsum(w) / w.sum()
    return float(v[min(np.searchsorted(cum, q, side="left"), len(v) - 1)])


@dataclass(frozen=True)
class ConformalCalibrator:
    alpha: float            # target miscoverage (0.1 -> 90% intervals)
    quantile: float         # q on the normalised-score scale
    beta: float             # sigma floor: keeps intervals finite where trees agree exactly
    n_calibration_rows: int
    n_calibration_bearings: int
    normalized: bool = True


def fit_conformal(
    y_true: np.ndarray, y_pred: np.ndarray, sigma: np.ndarray, groups: np.ndarray,
    alpha: float = 0.1, normalized: bool = True,
) -> ConformalCalibrator:
    """Calibrate on out-of-fold predictions. `groups` = bearing id per row.

    `normalized=False` is plain absolute-residual split conformal (constant
    width): the comparison that shows whether tree disagreement actually
    carries information about the error (experiments report both)."""
    y_true, y_pred, sigma = (np.asarray(a, dtype=float) for a in (y_true, y_pred, sigma))
    groups = np.asarray(groups)
    if len(np.unique(groups)) < 2:
        raise ValueError("Conformal calibration needs out-of-fold rows from >= 2 bearings.")
    beta = float(np.median(sigma)) * 0.1 + 1e-9
    if not normalized:
        sigma, beta = np.zeros_like(sigma), 1.0
    scores = np.abs(y_true - y_pred) / (sigma + beta)
    counts = pd.Series(groups).map(pd.Series(groups).value_counts()).to_numpy(dtype=float)
    n_bearings = len(np.unique(groups))
    # Finite-sample correction on the effective sample size (number of bearings).
    level = min(1.0, (1 - alpha) * (n_bearings + 1) / n_bearings)
    q = _weighted_quantile(scores, 1.0 / counts, level)
    return ConformalCalibrator(alpha=alpha, quantile=q, beta=beta,
                               n_calibration_rows=len(scores), n_calibration_bearings=n_bearings,
                               normalized=normalized)


def conformal_interval(
    y_pred: np.ndarray, sigma: np.ndarray, cal: ConformalCalibrator, lower_bound: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    sigma = np.asarray(sigma, dtype=float) if cal.normalized else np.zeros(np.shape(y_pred))
    half = cal.quantile * (sigma + cal.beta)
    y_pred = np.asarray(y_pred, dtype=float)
    return np.maximum(y_pred - half, lower_bound), y_pred + half
