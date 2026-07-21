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
