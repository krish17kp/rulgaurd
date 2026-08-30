"""Degradation-stage classification (M5, docs/milestone.md; docs/decisions.md D19).

A stage is a **severity band on the health indicator, not a fault diagnosis**.
No inner-race / outer-race / ball / cage / lubrication claim is made or implied:
bearing geometry is not verified in this project and BPFO/BPFI/BSF/FTF are not
derivable from the available data (.claude/rules/ml-data.md).

Method: a statistical alarm band with a persistence rule, in the spirit of
classical condition-monitoring practice (ISO 13373-style alarm bands).
`hi_warn` is a genuine fitted quantile of the training bearings' HEALTHY
window - it moves with the data. `hi_critical`, by contrast, is a quantile of
HI values that are themselves produced by `apply_reference_hi`'s fixed /6
logistic steepness (health.py), which was specifically calibrated to pin the
end-of-life anchor near HI ~ 0.047 (`1/(1+exp(3))`) regardless of the
underlying raw score. So `hi_critical` measurably clusters near that constant
across every leave-one-bearing-out fold (`reports/metrics/health_indicator_
comparison.json`: 0.0474-0.0477 across all 6 holds) - it is a threshold
computed from the data, but one substantially determined by the fixed score
mapping upstream of it, not an independent fit. Do not describe both
boundaries as equally "fitted, never chosen" (docs/decisions.md D20).

Leakage-safe by the same argument as the reference HI (health.py): thresholds
are fitted on the training fold and applied to the held-out bearing, and
`rul_seconds` never enters the fit. RUL is used only afterwards, to *score* the
stages (`summarize_stages`) - that is evaluation, not fitting.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

HEALTHY = "HEALTHY"
DEGRADING = "DEGRADING"
CRITICAL = "CRITICAL"

# Ordered least to most severe. A stage index is only ever compared, never
# used as a numeric feature.
STAGE_ORDER: tuple[str, ...] = (HEALTHY, DEGRADING, CRITICAL)

# Not a severity level - deliberately excluded from STAGE_ORDER. Emitted when
# no valid HI reading has ever been seen yet for a bearing (leading missing
# values) or none exists at all (entirely missing HI). Must never be conflated
# with HEALTHY: a green "healthy" badge implies a measurement was actually
# taken and looked fine, which is not true here.
UNKNOWN = "UNKNOWN"

# A stage change is committed only after this many consecutive acquisitions
# agree, so a single noise spike cannot trip an alarm. Backward-looking, so the
# rule stays causal.
DEFAULT_PERSISTENCE = 5

# Quantile of the training bearings' healthy-window HI used as the
# HEALTHY/DEGRADING boundary: below the healthy band's lower edge means the
# bearing has left the condition its own reference window established.
HEALTHY_QUANTILE = 0.05

# Fraction of each training bearing's run treated as end-of-life when setting
# the DEGRADING/CRITICAL boundary. Matches health.REFERENCE_HI_EOL_FRACTION.
EOL_FRACTION = 0.05


@dataclass(frozen=True)
class StageThresholds:
    """Fitted boundaries. Frozen, and carried with the model the same way
    `TreeBaseline.median_fill` and `ReferenceHIModel.scales` are."""

    hi_warn: float          # HEALTHY below this -> DEGRADING
    hi_critical: float      # DEGRADING below this -> CRITICAL
    persistence: int
    n_train_bearings: int


def fit_stage_thresholds(
    df_train: pd.DataFrame,
    hi_train: pd.Series,
    reference_skip: int,
    reference_n: int,
    persistence: int = DEFAULT_PERSISTENCE,
    healthy_quantile: float = HEALTHY_QUANTILE,
    eol_fraction: float = EOL_FRACTION,
) -> StageThresholds:
    """Calibrate both boundaries from the training bearings' HI distribution.

    `hi_warn`: the `healthy_quantile` percentile of HI over the training
    bearings' healthy reference windows - i.e. the lower edge of the band a
    healthy bearing actually occupies.

    `hi_critical`: the median HI over the training bearings' end-of-life
    windows - i.e. the level bearings are actually at when they fail. Reading
    the training bearings' end-of-life is legitimate (complete runs inside the
    fit fold); the held-out bearing's future is never read.
    """
    from bearing_pdm.evaluation import assert_no_leakage

    assert_no_leakage(df_train)

    healthy_chunks, failure_points = [], []
    tmp = df_train.assign(_hi=hi_train.to_numpy())
    for _bearing, group in tmp.groupby("bearing_run_id"):
        values = group.sort_values("sequence_index")["_hi"].to_numpy()
        window = values[reference_skip : reference_skip + reference_n]
        healthy_chunks.append(window if window.size else values[:reference_n])
        n_eol = max(1, int(len(values) * eol_fraction))
        failure_points.append(float(np.nanmedian(values[-n_eol:])))

    hi_warn = float(np.nanquantile(np.concatenate(healthy_chunks), healthy_quantile))
    hi_critical = float(np.nanmedian(failure_points))

    if not hi_critical < hi_warn:
        raise ValueError(
            f"Refusing to fit stages: the training bearings' end-of-life HI ({hi_critical:.4f}) "
            f"is not below their healthy-band edge ({hi_warn:.4f}). The health indicator does "
            "not separate healthy from failed on this training set, so a severity band on it "
            "would be meaningless."
        )

    return StageThresholds(
        hi_warn=hi_warn, hi_critical=hi_critical, persistence=persistence,
        n_train_bearings=int(tmp["bearing_run_id"].nunique()),
    )


def _raw_stage(hi: np.ndarray, thresholds: StageThresholds) -> np.ndarray:
    """Instantaneous band, before the persistence rule. NaN HI -> HEALTHY is
    deliberately NOT assumed; NaN propagates as an empty label so a missing
    reading is never silently reported as healthy."""
    out = np.full(hi.shape, "", dtype=object)
    known = ~np.isnan(hi)
    out[known & (hi >= thresholds.hi_warn)] = HEALTHY
    out[known & (hi < thresholds.hi_warn) & (hi >= thresholds.hi_critical)] = DEGRADING
    out[known & (hi < thresholds.hi_critical)] = CRITICAL
    return out


def _apply_persistence(raw: np.ndarray, k: int) -> np.ndarray:
    """Commit a stage change only after `k` consecutive acquisitions agree.

    Causal: the label at index i depends only on indices <= i. The stream
    starts UNKNOWN - never HEALTHY - until the first known (non-empty) raw
    reading is observed, and that first reading is trusted immediately (no
    persistence delay is needed to establish a baseline where none existed).
    A bearing that is already degraded when monitoring begins is therefore
    still not mislabelled as healthy for the first k acquisitions; a bearing
    with no valid reading yet (leading gap, or an entirely missing HI) is
    UNKNOWN rather than silently HEALTHY. Reading ahead into the array for the
    initial state - the previous behaviour - would have let a later index's
    value determine an earlier index's label, which is not causal.
    """
    committed = np.empty(raw.shape, dtype=object)
    current = UNKNOWN
    candidate, run = None, 0
    for i, stage in enumerate(raw):
        if not stage:
            pass  # missing reading: carry the last known state forward
        elif current == UNKNOWN:
            current = stage
        elif stage != current:
            run = run + 1 if stage == candidate else 1
            candidate = stage
            if run >= k:
                current, candidate, run = stage, None, 0
        else:
            candidate, run = None, 0
        committed[i] = current
    return committed


def assign_stages(
    df: pd.DataFrame, hi: pd.Series, thresholds: StageThresholds
) -> pd.Series:
    """Per-acquisition stage label, ordered by sequence_index within each
    bearing and returned aligned to `df.index`."""
    labels = pd.Series(index=df.index, dtype=object)
    tmp = df.assign(_hi=hi.to_numpy())
    for _bearing, group in tmp.groupby("bearing_run_id", sort=False):
        ordered = group.sort_values("sequence_index")
        raw = _raw_stage(ordered["_hi"].to_numpy(dtype=float), thresholds)
        labels.loc[ordered.index] = _apply_persistence(raw, thresholds.persistence)
    return labels


def summarize_stages(df: pd.DataFrame, stages: pd.Series) -> pd.DataFrame:
    """Per-bearing stage validation. Uses `rul_seconds` - that is SCORING, not
    fitting: no threshold above was derived from it.

    `rul_at_first_critical_seconds` is the practical question ("how much warning
    did this give?"). `n_severity_reversions` counts stages moving back toward
    healthy, which a severity band on a noisy HI can legitimately do and which
    should be reported rather than suppressed.
    """
    rank = {stage: i for i, stage in enumerate(STAGE_ORDER)}
    rows = []
    tmp = df.assign(_stage=stages.to_numpy())
    for bearing, group in tmp.groupby("bearing_run_id"):
        ordered = group.sort_values("sequence_index")
        labels = ordered["_stage"].to_numpy()
        n = len(labels)
        severity = np.array([rank.get(s, -1) for s in labels])
        first_critical = np.flatnonzero(severity == rank[CRITICAL])
        rul = ordered["rul_seconds"].to_numpy(dtype=float)
        rows.append({
            "bearing_run_id": bearing,
            "n": n,
            "frac_healthy": float(np.mean(labels == HEALTHY)),
            "frac_degrading": float(np.mean(labels == DEGRADING)),
            "frac_critical": float(np.mean(labels == CRITICAL)),
            "life_frac_at_first_critical": (
                float(first_critical[0] / n) if first_critical.size else float("nan")
            ),
            "rul_at_first_critical_seconds": (
                float(rul[first_critical[0]])
                if first_critical.size and np.isfinite(rul[first_critical[0]])
                else float("nan")
            ),
            "n_severity_reversions": int(np.sum(np.diff(severity) < 0)),
        })
    return pd.DataFrame(rows)
