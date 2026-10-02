"""Model applicability / out-of-distribution assessment.

Question answered: is this bearing's data similar enough to what the RUL model
was trained on for its prediction to mean anything? Deliberately simple and
interpretable - no learned OOD detector:

1. Robust standardisation with the TRAINING rows' median and MAD (fit on the
   training fold only), so every feature is in "training spreads" units.
2. Per recording: mean distance to its k nearest training recordings, as an RMS
   robust-z per feature (divided by sqrt(n_features) so the number of features
   does not change the scale).
3. Threshold calibrated in-domain, leave-one-bearing-out: each training bearing
   is scored against the OTHER training bearings, and the largest of those
   median distances is `in_domain_distance` - "as unfamiliar as the most
   unfamiliar bearing the training domain itself contains". A new bearing's
   `shift_ratio` = its median distance / that value.
4. Operating metadata checked against the training range: sampling rate, rpm,
   radial load; and model features that are mostly missing.
5. Life time-scale: a recording whose elapsed time already exceeds the
   longest complete life in the training set means the model is asked about
   a time scale it has no example of. This is label-range shift, which a
   feature-space distance cannot see: a bearing that runs healthy for 100
   hours has perfectly in-distribution (healthy-looking) features. Checked per
   recording, so it is causal (known at that moment). A seconds-target tree
   model cannot predict beyond its training labels at all -> LOW; a
   scale-free target -> MEDIUM.

Levels:
    HIGH    shift_ratio <= 1.0 and no metadata/availability problem
    MEDIUM  shift_ratio <= 2.0, or operating condition outside the training range
    LOW     shift_ratio  > 2.0, or a model feature is unavailable, or (seconds
            model) the bearing has outlived every training bearing

`shift_ratio` is the continuous quantity; the levels are a reporting convention.
Whether it tracks prediction error is tested, not assumed
(experiments.applicability_vs_error).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors

HIGH, MEDIUM, LOW = "HIGH", "MEDIUM", "LOW"
_LEVELS = (HIGH, MEDIUM, LOW)

MEDIUM_SHIFT_RATIO = 1.0
LOW_SHIFT_RATIO = 2.0
METADATA_TOLERANCE = 0.10      # +/-10% outside the training range still counts as inside
MISSING_FEATURE_FRACTION = 0.5
PARTIAL_MISSING_FRACTION = 0.1
Z_CLIP = 50.0                  # one absurd value must not decide the whole distance


@dataclass(frozen=True)
class ApplicabilityModel:
    feature_columns: tuple[str, ...]
    center: np.ndarray
    scale: np.ndarray
    reference: np.ndarray            # standardised training rows (subsampled)
    k: int
    in_domain_distance: float
    in_domain_distances: dict[str, float]
    sampling_rates_hz: tuple[float, ...]
    rpm_range: tuple[float, float] | None
    load_range: tuple[float, float] | None
    max_train_life_s: float | None = None
    life_scale_cap: str = LOW
    reference_bearings: np.ndarray | None = None   # bearing id of each `reference` row


def _standardize(df: pd.DataFrame, cols, center, scale) -> np.ndarray:
    x = df[list(cols)].to_numpy(dtype=float)
    z = (x - center) / scale
    z = np.clip(z, -Z_CLIP, Z_CLIP)
    return np.where(np.isfinite(z), z, 0.0)  # missing -> training median; flagged separately


def _knn_distance(z: np.ndarray, reference: np.ndarray, k: int) -> np.ndarray:
    nn = NearestNeighbors(n_neighbors=min(k, len(reference))).fit(reference)
    dist, _ = nn.kneighbors(z)
    return dist.mean(axis=1) / np.sqrt(z.shape[1])


def _range(values: pd.Series) -> tuple[float, float] | None:
    v = values.dropna()
    return (float(v.min()), float(v.max())) if len(v) else None


def _subsample_index(n: int, max_rows: int, seed: int) -> np.ndarray:
    if n <= max_rows:
        return np.arange(n)
    return np.sort(np.random.default_rng(seed).choice(n, max_rows, replace=False))


def fit_applicability(
    df_train: pd.DataFrame, feature_columns: list[str], k: int = 5,
    max_reference_rows: int = 5000, seed: int = 42, life_scale_cap: str = LOW,
) -> ApplicabilityModel:
    """Fit on the model's training rows only (the caller passes the same fold
    the RUL model was fit on)."""
    from bearing_pdm.evaluation import assert_no_leakage

    assert_no_leakage(df_train)
    cols = list(feature_columns)
    x = df_train[cols].to_numpy(dtype=float)
    center = np.nanmedian(x, axis=0)
    scale = 1.4826 * np.nanmedian(np.abs(x - center), axis=0)
    fallback = np.nanstd(x, axis=0)
    scale = np.where(scale > 1e-12, scale, np.where(fallback > 1e-12, fallback, 1.0))

    z = _standardize(df_train, cols, center, scale)
    bearings = df_train["bearing_run_id"].to_numpy()
    in_domain = {}
    for b in np.unique(bearings):
        others = z[bearings != b]
        others = others[_subsample_index(len(others), max_reference_rows, seed)]
        in_domain[str(b)] = float(np.median(_knn_distance(z[bearings == b], others, k)))

    def meta(col):
        return _range(df_train[col]) if col in df_train else None

    keep = _subsample_index(len(z), max_reference_rows, seed)
    return ApplicabilityModel(
        feature_columns=tuple(cols), center=center, scale=scale,
        reference=z[keep], reference_bearings=bearings[keep], k=k,
        in_domain_distance=max(in_domain.values()), in_domain_distances=in_domain,
        sampling_rates_hz=tuple(sorted(df_train["sample_rate_hz"].dropna().unique().tolist()))
        if "sample_rate_hz" in df_train else (),
        rpm_range=meta("rpm"), load_range=meta("radial_load_n"),
        max_train_life_s=_max_life(df_train), life_scale_cap=life_scale_cap,
    )


def _max_life(df: pd.DataFrame) -> float | None:
    """Longest complete life among labelled training bearings."""
    if "elapsed_s" not in df or "rul_seconds" not in df:
        return None
    labelled = df[df["rul_seconds"].notna()]
    return float(labelled.groupby("bearing_run_id")["elapsed_s"].max().max()) if len(labelled) else None


def outlived_training(df: pd.DataFrame, model: ApplicabilityModel) -> np.ndarray:
    """Per recording (causal): has this bearing already run longer than any
    training bearing's whole life?"""
    if model.max_train_life_s is None or "elapsed_s" not in df:
        return np.zeros(len(df), dtype=bool)
    limit = model.max_train_life_s * (1 + METADATA_TOLERANCE)
    return df["elapsed_s"].to_numpy(dtype=float) > limit


def exclude_bearing(model: ApplicabilityModel, bearing: str) -> ApplicabilityModel:
    """The same model as if `bearing` had not been in its training set: its
    reference rows and its own in-domain distance are dropped. Used to assess a
    bearing that WAS in a model's training data without the trivially-zero
    distance to itself (routing.py). Centre/scale keep that bearing's minor
    influence - stated, not hidden."""
    if model.reference_bearings is None or bearing not in model.in_domain_distances:
        return model
    keep = model.reference_bearings != bearing
    others = {b: d for b, d in model.in_domain_distances.items() if b != bearing}
    return replace(model, reference=model.reference[keep],
                   reference_bearings=model.reference_bearings[keep],
                   in_domain_distances=others, in_domain_distance=max(others.values()))


def recording_distances(df: pd.DataFrame, model: ApplicabilityModel) -> np.ndarray:
    """Per-recording kNN distance to the training domain (same units as
    `in_domain_distance`). Causal per row: uses only that recording."""
    z = _standardize(df, model.feature_columns, model.center, model.scale)
    return _knn_distance(z, model.reference, model.k)


def _outside(value: float | None, rng: tuple[float, float] | None) -> bool:
    if value is None or rng is None or not np.isfinite(value):
        return False
    lo, hi = rng
    return value < lo * (1 - METADATA_TOLERANCE) or value > hi * (1 + METADATA_TOLERANCE)


def _worse(a: str, b: str) -> str:
    return _LEVELS[max(_LEVELS.index(a), _LEVELS.index(b))]


def _level(shift_ratio):
    return np.where(shift_ratio <= MEDIUM_SHIFT_RATIO, HIGH,
                    np.where(shift_ratio <= LOW_SHIFT_RATIO, MEDIUM, LOW))


def _metadata_cap(first: pd.Series, model: ApplicabilityModel) -> tuple[str, list[str]]:
    """Worst level implied by operating metadata (constant per bearing)."""
    level, reasons = HIGH, []
    rate = float(first.get("sample_rate_hz", np.nan))
    if model.sampling_rates_hz and np.isfinite(rate) and rate not in model.sampling_rates_hz:
        level = MEDIUM
        reasons.append(f"sampling rate {rate:.0f} Hz not in training set "
                       f"{[int(r) for r in model.sampling_rates_hz]} Hz")
    for col, label, rng, unit in (("rpm", "speed", model.rpm_range, "rpm"),
                                  ("radial_load_n", "radial load", model.load_range, "N")):
        value = first.get(col)
        value = float(value) if value is not None and pd.notna(value) else None
        if _outside(value, rng):
            level = MEDIUM
            reasons.append(f"{label} {value:.0f} {unit} outside training range "
                           f"{rng[0]:.0f}-{rng[1]:.0f} {unit}")
    return level, reasons


def _missing_cap(missing_fraction: float) -> str:
    """Absent (> 50%) -> LOW. Partly missing (> 10%) -> MEDIUM: missing values sit
    at the training median in the distance, which would understate the shift."""
    if missing_fraction > MISSING_FEATURE_FRACTION:
        return LOW
    return MEDIUM if missing_fraction > PARTIAL_MISSING_FRACTION else HIGH


def assess(df_bearing: pd.DataFrame, model: ApplicabilityModel,
           distances: np.ndarray | None = None, single_recording: bool = False) -> dict:
    """Applicability of `model` to one bearing, summarising ALL rows passed.

    With the whole record passed this is a retrospective whole-run summary (used
    for the offline applicability-vs-error analysis). The per-recording, causal
    equivalent - what the system would have said at each moment - is
    `causal_levels`; at the last recording the two agree.

    `single_recording=True` changes only how the missing-feature cap is
    aggregated, for callers scoring exactly one acquisition's feature row
    (e.g. the online prediction API) rather than a whole run of many
    recordings. Per-column `isna().mean()` over a single row is just a 0/1
    indicator ("is this one feature present"), and taking its max (the
    run-level question: "what is this run's worst-covered feature") would
    then trip the LOW cap from a single absent feature, however small a
    fraction of the whole feature set that is. The correct single-row
    question is "what fraction of the required feature set is present in
    this one submission" - the mean of that same indicator, not its max."""
    if distances is None:
        distances = recording_distances(df_bearing, model)
    median_distance = float(np.median(distances))
    shift_ratio = median_distance / model.in_domain_distance
    level = str(_level(shift_ratio))
    reasons = [
        f"feature distribution shift {shift_ratio:.2f}x the in-domain reference "
        f"(median kNN distance {median_distance:.2f} vs {model.in_domain_distance:.2f})"
    ]

    cols = list(model.feature_columns)
    missing_fraction = df_bearing[cols].isna().mean()
    missing = [c for c in cols if missing_fraction[c] > MISSING_FEATURE_FRACTION]
    partial = [c for c in cols if PARTIAL_MISSING_FRACTION < missing_fraction[c]
               <= MISSING_FEATURE_FRACTION]
    missing_cap_input = float(missing_fraction.mean()) if single_recording else float(missing_fraction.max())
    level = _worse(level, _missing_cap(missing_cap_input))
    if missing:
        reasons.append(f"{len(missing)} model feature(s) unavailable, e.g. {missing[0]} "
                       "(sensor channel not present in this dataset)")
    if partial:
        reasons.append(f"{len(partial)} model feature(s) partly missing, e.g. {partial[0]} "
                       f"({missing_fraction[partial[0]]:.0%} of recordings)")

    meta_level, meta_reasons = _metadata_cap(df_bearing.iloc[0], model)
    level = _worse(level, meta_level)
    reasons += meta_reasons

    outlived = outlived_training(df_bearing, model)
    if outlived.any():
        level = _worse(level, model.life_scale_cap)
        reasons.append(
            f"life time-scale: {100 * outlived.mean():.0f}% of recordings are later than the "
            f"longest training life ({model.max_train_life_s / 3600:.1f} h) - RUL at this scale "
            "is extrapolated")

    z = (df_bearing[cols].to_numpy(dtype=float) - model.center) / model.scale
    with warnings.catch_warnings():   # an absent channel is all-NaN: reported above
        warnings.simplefilter("ignore", RuntimeWarning)
        median_z = pd.Series(np.nanmedian(z, axis=0), index=cols)
    top = median_z.abs().sort_values(ascending=False).head(3)
    shifted = {c: float(median_z[c]) for c in top.index if abs(median_z[c]) > 3}
    for c, v in shifted.items():
        reasons.append(f"{c}: median robust z = {v:+.1f} vs training")

    return {
        "level": level, "shift_ratio": float(shift_ratio), "median_distance": median_distance,
        "in_domain_distance": model.in_domain_distance, "reasons": reasons,
        "missing_features": missing, "partial_features": partial, "shifted_features": shifted,
        "outlived_fraction": float(outlived.mean()) if len(outlived) else 0.0,
    }


def causal_levels(df_bearing: pd.DataFrame, model: ApplicabilityModel,
                  distances: np.ndarray | None = None) -> pd.DataFrame:
    """Per recording, using only that recording and earlier ones of the same
    bearing (rows must be in sequence order): expanding-median shift ratio,
    expanding missing-feature fraction, metadata, and whether the bearing has
    outlived every training life by then. Returns columns `shift_ratio`, `level`."""
    if distances is None:
        distances = recording_distances(df_bearing, model)
    shift = pd.Series(distances).expanding().median().to_numpy() / model.in_domain_distance
    levels = _level(shift).astype(object)
    missing = (df_bearing[list(model.feature_columns)].isna().reset_index(drop=True)
               .expanding().mean().max(axis=1).to_numpy())
    meta_level, _ = _metadata_cap(df_bearing.iloc[0], model)
    outlived = np.maximum.accumulate(outlived_training(df_bearing, model))
    for i in range(len(levels)):
        level = _worse(levels[i], _missing_cap(missing[i]))
        level = _worse(level, meta_level)
        if outlived[i]:
            level = _worse(level, model.life_scale_cap)
        levels[i] = level
    return pd.DataFrame({"shift_ratio": shift, "level": levels}, index=df_bearing.index)
