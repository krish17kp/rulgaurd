"""Health indicator (HI) construction: transparent baseline + paper-inspired
PCA variant (command.md section 11). Both HIs are calibrated ("fit") only
on FEMTO `role='learning'` rows - never on `test_censored`/`full_test`
(docs/data-contract.md leakage guard).

v1 simplification (docs/decisions.md): calibration pools all 6 learning
bearings rather than leave-one-bearing-out. Documented as a hypothesis to
revisit, not a silent shortcut - see monotonicity/trendability evidence
in artifacts/evidence/REVIEW-M3/ for whether it holds up.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

# Contract/identifier columns that are never candidate HI features.
NON_FEATURE_COLUMNS = {
    "acquisition_id", "dataset_id", "bearing_run_id", "role", "source_file_path",
    "sequence_index", "event_timestamp", "sample_rate_hz", "n_samples", "row_start",
    "row_end", "schema_version", "source_sha256", "code_version", "temp_available",
    "rul_seconds", "stage_label",
    # Derived health outputs. Not present in any feature Parquet today, but
    # listed so that persisting them later can never turn a model output into a
    # RUL input (.claude/rules/ml-data.md: no target-derived features).
    "health_indicator", "hi_degradation_score",
}

TRANSPARENT_HI_FEATURES = [
    "vibration_x_rms", "vibration_y_rms", "vibration_x_kurtosis", "vibration_y_kurtosis",
]


def candidate_feature_columns(df: pd.DataFrame, max_nan_fraction: float = 1.0) -> list[str]:
    """All non-contract numeric columns, optionally excluding ones with a
    high NaN rate. A column that's entirely NaN for some bearings (e.g.
    bearing_temp_* for Bearing2_2/Bearing3_2, which have zero temperature
    files - docs/dataset-audit.md) must NOT reach PCA fitting: imputing it
    would fabricate a signal for a sensor that was never present, not fill
    a rare small gap. `max_nan_fraction` (used by fit_pca_hi) filters those
    out structurally instead of silently median-filling them."""
    cols = [c for c in df.columns if c not in NON_FEATURE_COLUMNS]
    if max_nan_fraction >= 1.0:
        return cols
    return [c for c in cols if df[c].isna().mean() <= max_nan_fraction]


def _healthy_baseline_mask(df: pd.DataFrame, healthy_fraction: float) -> pd.Series:
    """True for each bearing's earliest `healthy_fraction` of rows (by
    sequence_index) - assumed healthy, used only to calibrate, never as a
    model target."""
    cutoff = df.groupby("bearing_run_id")["sequence_index"].transform(
        lambda s: s.quantile(healthy_fraction)
    )
    return df["sequence_index"] <= cutoff


# ---------------------------------------------------------------------------
# Transparent baseline HI
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransparentHIBaseline:
    feature_means: dict[str, float]
    feature_stds: dict[str, float]
    features: tuple[str, ...] = tuple(TRANSPARENT_HI_FEATURES)


def fit_transparent_hi_baseline(
    df_train: pd.DataFrame, healthy_fraction: float = 0.1
) -> TransparentHIBaseline:
    """Fit healthy-reference mean/std for each feature from the pooled
    early-life rows of the training bearings only."""
    healthy = df_train[_healthy_baseline_mask(df_train, healthy_fraction)]
    means, stds = {}, {}
    for feat in TRANSPARENT_HI_FEATURES:
        values = healthy[feat].dropna()
        means[feat] = float(values.mean())
        stds[feat] = float(values.std(ddof=0)) or 1.0  # guard: never divide by 0
    return TransparentHIBaseline(feature_means=means, feature_stds=stds)


def apply_transparent_hi(df: pd.DataFrame, baseline: TransparentHIBaseline) -> pd.Series:
    """HI in (0, 1]: 1.0 = matches the healthy baseline exactly, ->0 as the
    mean z-score across features grows (RMS/kurtosis rising = degrading,
    confirmed in artifacts/evidence/REVIEW-M2/summary.md real-data check)."""
    z_scores = []
    for feat in baseline.features:
        z = (df[feat] - baseline.feature_means[feat]) / baseline.feature_stds[feat]
        z_scores.append(z)
    anomaly = pd.concat(z_scores, axis=1).mean(axis=1).clip(lower=0)
    return 1.0 / (1.0 + anomaly)


# ---------------------------------------------------------------------------
# Paper-inspired PCA HI
# ---------------------------------------------------------------------------


def monotonicity_trendability_scores(
    df_train: pd.DataFrame, feature_cols: list[str]
) -> pd.Series:
    """Cori-inspired composite ranking (command.md section 11.2), simplified
    to monotonicity + trendability (docs/decisions.md) - NOT a verified
    reproduction of the source paper's exact Cori formula.

    monotonicity: |mean(sign(diff))| per bearing, averaged across bearings.
    trendability: min pairwise correlation of the feature vs normalized
    life-fraction across bearings (low if bearings disagree on the trend).
    Both in [0, 1]; composite = monotonicity * trendability.
    """
    scores = {}
    for feat in feature_cols:
        mono_per_bearing = []
        trend_series = []
        for _bearing, g in df_train.sort_values("sequence_index").groupby("bearing_run_id"):
            values = g[feat].to_numpy()
            if len(values) < 3 or np.all(np.isnan(values)):
                continue
            diffs = np.diff(values[~np.isnan(values)])
            if diffs.size == 0:
                continue
            mono_per_bearing.append(abs(np.mean(np.sign(diffs))))
            life_fraction = np.linspace(0, 1, len(values))
            valid = ~np.isnan(values)
            if valid.sum() >= 2 and np.std(values[valid]) > 0:
                trend_series.append(np.corrcoef(life_fraction[valid], values[valid])[0, 1])

        monotonicity = float(np.mean(mono_per_bearing)) if mono_per_bearing else 0.0
        trendability = float(np.min(np.abs(trend_series))) if trend_series else 0.0
        scores[feat] = monotonicity * trendability

    return pd.Series(scores).sort_values(ascending=False)


@dataclass(frozen=True)
class PcaHIModel:
    selected_features: tuple[str, ...]
    scaler: StandardScaler
    pca: PCA
    orientation_sign: float  # +1 or -1, applied so PC1 decreases with degradation
    pc1_min: float
    pc1_max: float


def fit_pca_hi(
    df_train: pd.DataFrame, top_k: int = 8, healthy_fraction: float = 0.1, max_nan_fraction: float = 0.2
) -> PcaHIModel:
    """Feature-select (train-only monotonicity/trendability ranking, columns
    with >max_nan_fraction missing excluded entirely - see
    candidate_feature_columns) -> StandardScaler -> PCA(1) -> orient ->
    min-max, all fit on train rows only (docs/data-contract.md leakage
    guard). Remaining (rare, small) gaps in the selected columns are
    median-filled, which is standard practice for sparse missingness, not
    the same as fabricating a wholly-absent sensor."""
    all_features = candidate_feature_columns(df_train, max_nan_fraction=max_nan_fraction)
    ranked = monotonicity_trendability_scores(df_train, all_features)
    selected = tuple(ranked.head(top_k).index)

    train_matrix = df_train[list(selected)].fillna(df_train[list(selected)].median())
    scaler = StandardScaler().fit(train_matrix)
    scaled = scaler.transform(train_matrix)

    pca = PCA(n_components=1, random_state=42).fit(scaled)
    pc1 = pca.transform(scaled)[:, 0]

    # Orient so PC1 decreases with life-fraction (degradation direction).
    # Must normalize per-bearing (sequence_index / that bearing's max) before
    # pooling - bearings range from 515 to 2803 acquisitions, so correlating
    # against raw pooled sequence_index lets the longest bearings dominate
    # the sign and can invert the orientation for every other bearing.
    life_fraction = df_train.groupby("bearing_run_id")["sequence_index"].transform(
        lambda s: s / s.max()
    )
    corr = np.corrcoef(pc1, life_fraction.to_numpy())[0, 1]
    orientation_sign = -1.0 if corr > 0 else 1.0
    pc1_oriented = orientation_sign * pc1

    return PcaHIModel(
        selected_features=selected, scaler=scaler, pca=pca, orientation_sign=orientation_sign,
        pc1_min=float(pc1_oriented.min()), pc1_max=float(pc1_oriented.max()),
    )


def apply_pca_hi(df: pd.DataFrame, model: PcaHIModel) -> pd.Series:
    """HI in [0, 1] via min-max scaling of the (train-frozen) oriented PC1
    range. Values outside the train range are NOT clipped - a HI < 0 or > 1
    on new data is itself diagnostic (worse/better than any train bearing
    ever saw), not an error to hide."""
    matrix = df[list(model.selected_features)].fillna(df[list(model.selected_features)].median())
    scaled = model.scaler.transform(matrix)
    pc1 = model.orientation_sign * model.pca.transform(scaled)[:, 0]
    span = model.pc1_max - model.pc1_min
    if span == 0:
        return pd.Series(np.full(len(df), np.nan), index=df.index)
    return pd.Series((pc1 - model.pc1_min) / span, index=df.index)


# ---------------------------------------------------------------------------
# Shared evaluation metrics
# ---------------------------------------------------------------------------


def evaluate_hi(df: pd.DataFrame, hi: pd.Series) -> pd.DataFrame:
    """Per-bearing monotonicity (|mean(sign(diff))|, 1=perfectly monotone)
    and trend correlation (HI vs sequence_index; expect strongly negative)."""
    rows = []
    tmp = df.assign(hi=hi.to_numpy())
    for bearing, g in tmp.sort_values("sequence_index").groupby("bearing_run_id"):
        values = g["hi"].to_numpy()
        diffs = np.diff(values)
        monotonicity = float(np.abs(np.mean(np.sign(diffs)))) if diffs.size else float("nan")
        if np.std(values) > 0:
            trend_corr = float(np.corrcoef(values, g["sequence_index"].to_numpy())[0, 1])
        else:
            trend_corr = float("nan")
        rows.append({"bearing_run_id": bearing, "monotonicity": monotonicity, "trend_corr": trend_corr, "n": len(g)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Reference HI - per-unit healthy reference, train-calibrated scale/anchors
# ---------------------------------------------------------------------------
#
# Added (docs/decisions.md D18) after measuring that both HIs above fail on the
# real FEMTO learning set:
#
#   transparent_hi: 47.5% of all learning acquisitions pin at exactly 1.0
#     (87.4% of Bearing3_1, 88.9% of Bearing3_2, both with IQR 0.00). Two
#     causes compound. (a) apply_transparent_hi clips the anomaly at 0, so
#     every row at or below the reference collapses to HI=1.0 - a hard floor
#     that destroys all resolution on the healthy side. (b) the healthy
#     reference is POOLED across bearings running at three different FEMTO
#     operating conditions (1800rpm/4000N, 1650rpm/4200N, 1500rpm/5000N), so
#     absolute vibration level differs per condition: pooled healthy
#     vibration_x_rms is 0.401 while Bearing3_1/3_2 sit at ~0.31 for most of
#     their lives - permanently "below reference", hence pinned. Bearing2_1 has
#     the mirror problem (median z = +1.58 from its first acquisition).
#
#   pca_hi: not pinned but collapsed - min-max over pooled PC1 is set by rare
#     end-of-life spikes, leaving Bearing3_1 a p10->p90 span of 0.968->0.987.
#
# The degradation signal is real; the pooled reference is what hid it. Measured
# ratio of each bearing's own end-of-life median to its own early-life median:
# vibration_x_rms 1.57-4.28x, crest factor 1.44-1.86x, kurtosis 25-331x - every
# bearing rises against ITS OWN baseline, while no feature is consistently
# signed against a pooled one (vibration_x_rms scores Spearman +0.86 on
# Bearing1_1 and -0.42 on Bearing3_1).

# Fixed, physically-motivated set: amplitude + impulsiveness on both channels.
# Chosen from the measured per-bearing rise ratios above rather than from
# monotonicity_trendability_scores, whose full-life correlation is inverted by
# FEMTO's early-life run-in transient (see REFERENCE_HI_SKIP below).
REFERENCE_HI_FEATURES = [
    "vibration_x_rms", "vibration_y_rms",
    "vibration_x_peak_to_peak", "vibration_y_peak_to_peak",
    "vibration_x_kurtosis", "vibration_y_kurtosis",
    "vibration_x_crest_factor", "vibration_y_crest_factor",
]

# Heavy-tailed channels get log1p before fusion: raw kurtosis spans 0.02..412
# across the learning set, so an unlogged mean is dominated by whichever
# feature happens to spike.
REFERENCE_HI_LOG_FEATURES = frozenset({"vibration_x_kurtosis", "vibration_y_kurtosis"})

# Healthy reference window: acquisitions [SKIP, SKIP+N) of each bearing's own
# record. A fixed COUNT with a fixed OFFSET, deliberately not a fraction of
# total life (which _healthy_baseline_mask uses): total life is only known
# after failure, so a fraction cannot be computed online or on a censored
# bearing. The offset skips FEMTO's measured run-in transient - median
# vibration_x_rms by life decile for Bearing3_1 runs 0.458 -> 0.324 -> 0.310
# -> ... -> 0.305, high then settling.
REFERENCE_HI_SKIP = 10
REFERENCE_HI_N = 50

# Trailing rolling-median width. Swept on real data (artifacts/evidence): 31
# over-smooths - it cannot resolve Bearing3_1's ~17-acquisition terminal cliff,
# leaving its last-10% HI at 0.956 - while 1 is needlessly noisy. 11 is the
# responsiveness/noise trade-off point.
REFERENCE_HI_SMOOTH_WINDOW = 11

# End-of-life window used to set the failure anchor, as a fraction of each
# TRAINING bearing's run.
REFERENCE_HI_EOL_FRACTION = 0.05


@dataclass(frozen=True)
class ReferenceHIModel:
    """Fitted state that must travel with the model (.claude/rules/ml-data.md:
    "fit on train fold only"). Everything here is derived from training
    bearings; the per-bearing healthy reference is NOT stored, because it is
    recomputed at apply time from the target bearing's own leading window."""

    features: tuple[str, ...]
    log_features: tuple[str, ...]
    scales: dict[str, float]          # robust per-feature spread, frozen from train
    healthy_score: float              # median degradation score in train healthy windows
    failure_score: float              # median of per-train-bearing end-of-life scores
    reference_skip: int
    reference_n: int
    smooth_window: int


def _reference_hi_matrix(df: pd.DataFrame, features, log_features) -> pd.DataFrame:
    """Feature matrix with the heavy-tailed channels log1p-compressed. NaN in,
    NaN out - never global-imputed (.claude/rules/python.md)."""
    out = pd.DataFrame(index=df.index)
    log_features = set(log_features)
    for feat in features:
        values = df[feat].astype(float)
        out[feat] = np.log1p(values.clip(lower=0)) if feat in log_features else values
    return out


def _per_bearing_reference(
    df: pd.DataFrame, matrix: pd.DataFrame, skip: int, n_ref: int
) -> pd.DataFrame:
    """Subtract each bearing's OWN healthy-reference median (acquisitions
    [skip, skip+n_ref) of that bearing, ordered by sequence_index).

    This is the fix for the pooled-reference defect, and it is causal: the
    window lies strictly in the past of every later acquisition, is available
    at inference, and exists for all 11 FEMTO test_censored bearings (verified:
    every censored prefix starts at sequence_index == 0).

    Assumption, stated rather than hidden: the bearing is healthy during that
    window. True by construction for PRONOSTIA and the college rig, both of
    which are run-to-failure from new. It would NOT hold for a bearing first
    instrumented mid-life.
    """
    centered = matrix.copy()
    for _bearing, group in df.groupby("bearing_run_id", sort=False):
        ordered = group.sort_values("sequence_index").index
        window = ordered[skip : skip + n_ref]
        if len(window) == 0:  # run shorter than the offset - fall back to what exists
            window = ordered[:n_ref]
        reference = matrix.loc[window].median()
        centered.loc[group.index] = matrix.loc[group.index].to_numpy() - reference.to_numpy()
    return centered


def _robust_scale(values: np.ndarray) -> float:
    """1.4826 * MAD (consistent with std for Gaussian data) with fallbacks, so
    one 100x kurtosis spike cannot set the scale the way a pooled std does."""
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 1.0
    scale = 1.4826 * float(np.median(np.abs(finite - np.median(finite))))
    if scale > 1e-9:
        return scale
    std = float(np.std(finite))
    return std if std > 1e-9 else 1.0


def _degradation_score(
    df: pd.DataFrame, centered: pd.DataFrame, features, scales: dict[str, float], window: int
) -> pd.Series:
    """Fuse the standardised per-feature deviations, then smooth with a
    TRAILING rolling median per bearing. Trailing and uncentred by design - a
    centred window would read future acquisitions into the current value."""
    fused = pd.concat([centered[f] / scales[f] for f in features], axis=1).mean(axis=1)
    return fused.groupby(df["bearing_run_id"]).transform(
        lambda s: s.rolling(window, min_periods=1).median()
    )


def fit_reference_hi(
    df_train: pd.DataFrame,
    features: list[str] | None = None,
    skip: int = REFERENCE_HI_SKIP,
    n_ref: int = REFERENCE_HI_N,
    smooth_window: int = REFERENCE_HI_SMOOTH_WINDOW,
    eol_fraction: float = REFERENCE_HI_EOL_FRACTION,
) -> ReferenceHIModel:
    """Calibrate the robust scale and the healthy/failure anchors on training
    bearings only.

    `failure_score` reads the training bearings' end-of-life, which is
    legitimate: those are complete runs inside the fit fold. No held-out
    bearing contributes to any fitted value, and `rul_seconds` is never read.
    """
    from bearing_pdm.evaluation import assert_no_leakage

    assert_no_leakage(df_train)

    features = list(features or REFERENCE_HI_FEATURES)
    log_features = tuple(f for f in features if f in REFERENCE_HI_LOG_FEATURES)

    matrix = _reference_hi_matrix(df_train, features, log_features)
    centered = _per_bearing_reference(df_train, matrix, skip, n_ref)
    scales = {f: _robust_scale(centered[f].to_numpy()) for f in features}
    score = _degradation_score(df_train, centered, features, scales, smooth_window)

    healthy_chunks, failure_points = [], []
    for _bearing, group in df_train.assign(_score=score.to_numpy()).groupby("bearing_run_id"):
        values = group.sort_values("sequence_index")["_score"].to_numpy()
        healthy_chunks.append(values[skip : skip + n_ref])
        n_eol = max(1, int(len(values) * eol_fraction))
        failure_points.append(float(np.nanmedian(values[-n_eol:])))

    healthy_score = float(np.nanmedian(np.concatenate(healthy_chunks)))
    failure_score = float(np.nanmedian(failure_points))
    if not np.isfinite(failure_score - healthy_score) or failure_score <= healthy_score:
        raise ValueError(
            "Refusing to fit reference HI: the training bearings' end-of-life score "
            f"({failure_score:.4f}) does not exceed their healthy score ({healthy_score:.4f}). "
            "Degradation is not detectable in these features on this training set."
        )

    return ReferenceHIModel(
        features=tuple(features), log_features=log_features, scales=scales,
        healthy_score=healthy_score, failure_score=failure_score,
        reference_skip=skip, reference_n=n_ref, smooth_window=smooth_window,
    )


def apply_reference_hi(df: pd.DataFrame, model: ReferenceHIModel) -> pd.Series:
    """HI in the OPEN interval (0, 1): ~0.95 at the bearing's own healthy
    reference, ~0.05 at the failure anchor.

    The logistic map is the point. `1/(1+anomaly)` with a floor at 0 pins every
    at-or-below-reference row at exactly 1.0; a logistic is strictly monotone
    and strictly between 0 and 1 for every finite score, so pinning is
    structurally impossible rather than clipped away. The anchors are frozen
    from train; the per-bearing healthy reference is recomputed here from this
    frame's own leading window, so a bearing the model has never seen is
    normalised against itself, not against the training population's level.
    """
    matrix = _reference_hi_matrix(df, model.features, model.log_features)
    centered = _per_bearing_reference(df, matrix, model.reference_skip, model.reference_n)
    score = _degradation_score(
        df, centered, list(model.features), model.scales, model.smooth_window
    )
    midpoint = 0.5 * (model.healthy_score + model.failure_score)
    # /6 puts the healthy anchor near 0.95 and the failure anchor near 0.05.
    steepness = (model.failure_score - model.healthy_score) / 6.0
    return 1.0 / (1.0 + np.exp((score - midpoint) / steepness))


def reference_hi_diagnostics(df: pd.DataFrame, hi: pd.Series) -> pd.DataFrame:
    """Per-bearing HI health check aimed at the failure modes actually observed.

    `pct_at_one`/`pct_at_zero` are the regression guards for the pinning defect.
    `spearman` replaces `trend_corr` as the headline: FEMTO degradation is
    flat-then-cliff (Bearing3_2's vibration_x_rms is flat at ~0.30 for ~95% of
    life then jumps 6x inside the final ~17 acquisitions), so a Pearson
    correlation against a linear time axis understates a perfectly usable HI.
    `monotonicity` is kept but demoted - |mean(sign(diff))| is near zero for any
    noisy real signal and says more about acquisition noise than about trend.
    """
    rows = []
    tmp = df.assign(_hi=hi.to_numpy())
    for bearing, group in tmp.sort_values("sequence_index").groupby("bearing_run_id"):
        values = group["_hi"].to_numpy()
        sequence = group["sequence_index"].to_numpy()
        n = len(values)
        n_eol = max(1, n // 100)
        diffs = np.diff(values)
        rows.append({
            "bearing_run_id": bearing,
            "n": n,
            "hi_min": float(np.nanmin(values)),
            "hi_max": float(np.nanmax(values)),
            "pct_at_one": float(100.0 * np.mean(values >= 0.999)),
            "pct_at_zero": float(100.0 * np.mean(values <= 0.001)),
            "hi_healthy_window": float(np.nanmedian(values[10:60])),
            "hi_final_1pct": float(np.nanmedian(values[-n_eol:])),
            "usable_range_p05_p95": float(
                np.nanpercentile(values, 95) - np.nanpercentile(values, 5)
            ),
            "spearman": float(
                pd.Series(values).corr(pd.Series(sequence), method="spearman")
            ) if np.std(values) > 0 else float("nan"),
            "monotonicity": float(np.abs(np.mean(np.sign(diffs)))) if diffs.size else float("nan"),
        })
    return pd.DataFrame(rows)
