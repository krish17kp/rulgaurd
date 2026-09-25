"""Cross-dataset RUL experiments (docs/cross-dataset.md).

Every experiment is one or more calls to `run_split(train, test, kind)`:

* the model is fit on `train` only (assert_no_leakage), with the SAME seed;
* the conformal calibrator is fit on out-of-fold predictions from an inner
  GroupKFold over the TRAIN bearings only - the test bearing never touches
  calibration;
* the applicability model is fit on `train` only;
* splits are always by whole bearing (never by row) - `_check_disjoint` asserts it.

Model kinds:
    raw_seconds  ExtraTrees on the 44 absolute vibration features -> RUL seconds
                 (exactly the frozen FEMTO pipeline, pinned column order)
    sn_fraction  ExtraTrees on self-normalised features (domain.py) -> life
                 fraction, converted to seconds with elapsed time
                 (modeling.fraction_to_rul); bearing-balanced sample weights.
                 Its skill is judged in life-fraction units against a
                 label-free constant guess (f = 0.5), because the seconds
                 conversion amplifies early-life errors (docs/decisions.md D24).

Categories (never mixed in one table):
    WITHIN-DOMAIN   train and test bearings from the same dataset (LOBO)
    ZERO-SHOT       train FEMTO only, test another dataset, no target labels
    CALIBRATED      FEMTO model + linear map fit on OTHER labelled bearings of
                    the target dataset (LOBO inside the target)
    MULTI-DATASET   train on several datasets: LOBO over all bearings, and
                    leave-one-domain-out (LODO)

Models train on every labelled row of the training bearings. Evaluation (and
conformal calibration) use recordings after each bearing's reference window
(domain.after_reference_window) - the same rows for every model, so every
number in one table is computed on identical data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from bearing_pdm.applicability import (
    LOW,
    MEDIUM,
    assess,
    fit_applicability,
    recording_distances,
)
from bearing_pdm.domain import SN_FEATURES, add_self_normalized_features, after_reference_window
from bearing_pdm.evaluation import assert_no_leakage
from bearing_pdm.modeling import (
    LIFE_FRACTION_COLUMN,
    MIN_LIFE_FRACTION,
    TreeBaseline,
    bearing_balanced_weights,
    fit_tree_baseline,
    fraction_to_rul,
)
from bearing_pdm.uncertainty import conformal_interval, fit_conformal, tree_predictions

ALPHA = 0.1          # 90% prediction intervals
# Bumped whenever the persisted cross_dataset.json layout changes; readers
# (dashboard_cross.py) refuse an artifact with another version instead of
# failing on a missing key.
RESULTS_SCHEMA_VERSION = "cross-dataset-v2"
INNER_FOLDS = 5
KINDS = ("raw_seconds", "sn_fraction")
# A seconds-target tree cannot predict past its training labels; a scale-free
# target can, but has seen no example of that time scale (applicability.py).
LIFE_SCALE_CAP = {"raw_seconds": LOW, "sn_fraction": MEDIUM}
FIT_ROLES = ("learning", "college_run", "run_to_failure")
_KEEP = ["dataset_id", "bearing_run_id", "sequence_index", "elapsed_s", "rul_seconds",
         "life_fraction", "total_life_s"]


def prepare(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate canonical frames, add SN features and the evaluation mask."""
    df = pd.concat(frames, ignore_index=True)
    df = add_self_normalized_features(df)
    df["evaluable"] = after_reference_window(df) & df["rul_seconds"].notna()
    df["total_life_s"] = df.groupby("bearing_run_id")["elapsed_s"].transform("max").where(
        df["rul_seconds"].notna())
    return df


def run_to_failure(df: pd.DataFrame, dataset: str | None = None) -> pd.DataFrame:
    """Complete run-to-failure bearings - the only ones with a RUL label."""
    keep = df["rul_seconds"].notna() & df["role"].isin(FIT_ROLES)
    if dataset is not None:
        keep &= df["dataset_id"] == dataset
    return df[keep]


def _check_disjoint(train: pd.DataFrame, test: pd.DataFrame) -> None:
    overlap = set(train["bearing_run_id"]) & set(test["bearing_run_id"])
    if overlap:
        raise AssertionError(f"Bearing-level leakage: {sorted(overlap)} in both train and test.")


def fit_kind(train: pd.DataFrame, kind: str, raw_columns: list[str]) -> TreeBaseline:
    assert_no_leakage(train)
    if kind == "raw_seconds":
        return fit_tree_baseline(train, feature_columns=raw_columns)
    return fit_tree_baseline(train, feature_columns=SN_FEATURES, target=LIFE_FRACTION_COLUMN,
                             sample_weight=bearing_balanced_weights(train))


def predict_with_spread(model: TreeBaseline, df: pd.DataFrame,
                        quantiles: bool = False):
    """(mean, std) over trees; with `quantiles`, also the trees' 5th/95th percentiles."""
    x = df[list(model.feature_columns)].fillna(model.median_fill)
    per_tree = tree_predictions(model.model, x)
    out = (per_tree.mean(axis=0), per_tree.std(axis=0))
    if quantiles:
        out += (np.percentile(per_tree, 5, axis=0), np.percentile(per_tree, 95, axis=0))
    return out


def _target(df: pd.DataFrame, kind: str) -> np.ndarray:
    col = "rul_seconds" if kind == "raw_seconds" else LIFE_FRACTION_COLUMN
    return df[col].to_numpy(dtype=float)


def calibrate(train: pd.DataFrame, kind: str, raw_columns: list[str]):
    """Conformal calibrator from inner out-of-fold predictions on TRAIN bearings
    only (GroupKFold by bearing)."""
    bearings = np.array(sorted(train["bearing_run_id"].unique()))
    y, yhat, sig, grp = [], [], [], []
    folds = GroupKFold(n_splits=min(INNER_FOLDS, len(bearings)))
    for tr_b, cal_b in folds.split(bearings, groups=bearings):
        inner = fit_kind(train[train["bearing_run_id"].isin(bearings[tr_b])], kind, raw_columns)
        cal_rows = train[train["bearing_run_id"].isin(bearings[cal_b]) & train["evaluable"]]
        p, s = predict_with_spread(inner, cal_rows)
        y.append(_target(cal_rows, kind))
        yhat.append(p)
        sig.append(s)
        grp.append(cal_rows["bearing_run_id"].to_numpy())
    args = (np.concatenate(y), np.concatenate(yhat), np.concatenate(sig), np.concatenate(grp))
    return {"conformal": fit_conformal(*args, alpha=ALPHA, normalized=True),
            "conformal_abs": fit_conformal(*args, alpha=ALPHA, normalized=False)}


# Interval columns written per row: (lo, hi) name pairs. `rul_lo/rul_hi` is the
# reported interval (normalised conformal); the others exist to be compared.
INTERVALS = {"conformal": ("rul_lo", "rul_hi"), "conformal_abs": ("rul_lo_abs", "rul_hi_abs"),
             "tree_5_95": ("tree_lo", "tree_hi")}


def _to_seconds(lo, hi, kind, elapsed):
    """Interval on the model's target scale -> RUL seconds. RUL decreases in the
    life fraction, so the fraction interval's upper end is the RUL's lower end."""
    if kind == "raw_seconds":
        return np.maximum(lo, 0.0), hi
    return (fraction_to_rul(np.minimum(hi, 1.0), elapsed),
            fraction_to_rul(np.maximum(lo, MIN_LIFE_FRACTION), elapsed))


def predict_rows(model: TreeBaseline, cals: dict, test: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Point prediction + three intervals, all in seconds, for the test rows."""
    p, s, q05, q95 = predict_with_spread(model, test, quantiles=True)
    elapsed = test["elapsed_s"].to_numpy(dtype=float)
    out = pd.DataFrame(index=test.index)
    out["tree_std"] = s
    if kind == "raw_seconds":
        out["predicted_rul_seconds"] = p
    else:
        out["predicted_life_fraction"] = p
        out["predicted_rul_seconds"] = fraction_to_rul(p, elapsed)
    bounds = {name: conformal_interval(p, s, cal, lower_bound=-np.inf) for name, cal in cals.items()}
    bounds["tree_5_95"] = (q05, q95)
    for name, (lo_col, hi_col) in INTERVALS.items():
        out[lo_col], out[hi_col] = _to_seconds(*bounds[name], kind, elapsed)
    return out


def _app_rows(evaluated: pd.DataFrame, frame: pd.DataFrame, app_model, experiment, category,
              kind) -> list[dict]:
    rows = []
    for bearing, g in evaluated.groupby("bearing_run_id"):
        a = assess(g, app_model, distances=frame.loc[g.index, "distance"].to_numpy())
        rows.append({"experiment": experiment, "category": category, "model": kind,
                     "bearing_run_id": bearing, "level": a["level"],
                     "shift_ratio": a["shift_ratio"], "outlived_fraction": a["outlived_fraction"],
                     "reasons": a["reasons"]})
    return rows


def run_split(train: pd.DataFrame, test: pd.DataFrame, kind: str, raw_columns: list[str],
              experiment: str, category: str, model: TreeBaseline | None = None,
              cal=None) -> tuple[pd.DataFrame, list[dict]]:
    """Fit on train, predict every test bearing, assess applicability per bearing.
    `model`/`cal` may be passed in (the frozen FEMTO artifact for zero-shot) -
    they must then have been fit on exactly `train`."""
    _check_disjoint(train, test)
    model = model or fit_kind(train, kind, raw_columns)
    cals = cal or calibrate(train, kind, raw_columns)
    app_model = fit_applicability(train, list(model.feature_columns),
                                  life_scale_cap=LIFE_SCALE_CAP[kind])

    evaluated = test[test["evaluable"]]
    frame = evaluated[_KEEP].join(predict_rows(model, cals, evaluated, kind))
    frame = frame.rename(columns={"rul_seconds": "actual_rul_seconds"})
    naive_life = float(train.groupby("bearing_run_id")["elapsed_s"].max().mean())
    frame["naive_rul_seconds"] = np.maximum(naive_life - frame["elapsed_s"], 0.0)
    frame["distance"] = recording_distances(evaluated, app_model)
    frame = frame.assign(
        experiment=experiment, category=category, model=kind,
        train_domains="+".join(sorted(train["dataset_id"].unique())),
        test_domain="+".join(sorted(test["dataset_id"].unique())))
    return frame, _app_rows(evaluated, frame, app_model, experiment, category, kind)


# ---------------------------------------------------------------------------
# Experiment families
# ---------------------------------------------------------------------------

def lobo(df: pd.DataFrame, kind: str, raw_columns, experiment, category) -> tuple[list, list]:
    """Leave-one-bearing-out over every bearing in `df`."""
    preds, apps = [], []
    for bearing in sorted(df["bearing_run_id"].unique()):
        p, a = run_split(df[df["bearing_run_id"] != bearing], df[df["bearing_run_id"] == bearing],
                         kind, raw_columns, experiment, category)
        preds.append(p)
        apps += a
    return preds, apps


def leave_one_domain_out(df: pd.DataFrame, raw_columns, log=print) -> tuple[list, list]:
    """Train on every other dataset, test every bearing of the held-out one.
    A fold whose training side has < 2 bearings is skipped: neither the inner
    conformal calibration nor the in-domain applicability threshold exists
    for a single bearing."""
    preds, apps = [], []
    for domain in sorted(df["dataset_id"].unique()):
        train = df[df["dataset_id"] != domain]
        if train["bearing_run_id"].nunique() < 2:
            log(f"  LODO -> {domain} skipped: only {train['bearing_run_id'].nunique()} "
                "training bearing(s)")
            continue
        p, a = run_split(train, df[df["dataset_id"] == domain],
                         "sn_fraction", raw_columns, f"LODO: all others -> {domain}",
                         "MULTI-DATASET")
        preds.append(p)
        apps += a
    return preds, apps


def calibrated(train: pd.DataFrame, target: pd.DataFrame, raw_columns,
               experiment: str) -> tuple[list, list]:
    """FEMTO-trained sn_fraction model, then per test bearing a linear map
    f_true = a + b * f_pred fit on the OTHER target-domain bearings, with a
    conformal interval calibrated on those same bearings' residuals. The test
    bearing is used for nothing but scoring."""
    _check_disjoint(train, target)
    base = fit_kind(train, "sn_fraction", raw_columns)
    app_model = fit_applicability(train, SN_FEATURES, life_scale_cap=MEDIUM)
    t = target[target["evaluable"]].copy()
    t["_p"], t["_s"] = predict_with_spread(base, t)
    preds, apps = [], []
    for bearing in sorted(t["bearing_run_id"].unique()):
        other, test = t[t["bearing_run_id"] != bearing], t[t["bearing_run_id"] == bearing]
        slope, intercept = np.polyfit(other["_p"], other[LIFE_FRACTION_COLUMN], 1)
        y_other = np.clip(intercept + slope * other["_p"], 0, 1)
        args = (other[LIFE_FRACTION_COLUMN], y_other, other["_s"] * abs(slope), other["bearing_run_id"])
        cals = {"conformal": fit_conformal(*args, alpha=ALPHA),
                "conformal_abs": fit_conformal(*args, alpha=ALPHA, normalized=False)}
        y = np.clip(intercept + slope * test["_p"].to_numpy(), 0, 1)
        s = test["_s"].to_numpy() * abs(slope)
        el = test["elapsed_s"].to_numpy(dtype=float)
        bounds = {n: conformal_interval(y, s, c, lower_bound=-np.inf) for n, c in cals.items()}
        # Tree spread is the base model's raw disagreement, not recalibrated;
        # +/-1.645 sd is the 5-95% band under a normal approximation.
        bounds["tree_5_95"] = (y - 1.645 * s, y + 1.645 * s)
        extra = {}
        for name, (lo_col, hi_col) in INTERVALS.items():
            extra[lo_col], extra[hi_col] = _to_seconds(*bounds[name], "sn_fraction", el)
        frame = test[_KEEP].rename(columns={"rul_seconds": "actual_rul_seconds"}).assign(
            tree_std=test["_s"].to_numpy(), predicted_life_fraction=y,
            predicted_rul_seconds=fraction_to_rul(y, el), **extra,
            naive_rul_seconds=np.nan, distance=recording_distances(test, app_model),
            experiment=experiment, category="CALIBRATED", model="sn_fraction",
            train_domains="femto", test_domain=test["dataset_id"].iloc[0])
        preds.append(frame)
        apps += _app_rows(test, frame, app_model, experiment, "CALIBRATED", "sn_fraction")
    return preds, apps


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

_KEYS = ["experiment", "category", "model", "train_domains", "test_domain"]


def bearing_metrics(pred: pd.DataFrame) -> pd.DataFrame:
    """Per (experiment, model, bearing): magnitude, direction, and the
    life-normalised error nMAE = MAE / total life, which makes a bearing that
    lived 1 hour and one that lived 30 days comparable."""
    rows = []
    for key, g in pred.groupby(_KEYS + ["bearing_run_id"]):
        actual = g["actual_rul_seconds"]
        err = g["predicted_rul_seconds"] - actual
        rel = (err.abs() / actual)[actual > 0]
        naive_err = g["naive_rul_seconds"] - actual
        # Life-fraction view, identical for every model: the fraction implied by a
        # RUL prediction at elapsed t is t / (t + RUL). The reference is a
        # label-free constant guess f = 0.5; skill > 0 means better than it.
        t = g["elapsed_s"]
        f_hat = t / (t + g["predicted_rul_seconds"].clip(lower=0))
        f_err = (f_hat - g["life_fraction"]).abs()
        const_err = (0.5 - g["life_fraction"]).abs()
        post = g["stage"].isin(["DEGRADING", "CRITICAL"]) if "stage" in g else pd.Series(False, g.index)
        intervals = {}
        for name, (lo, hi) in INTERVALS.items():
            intervals[f"coverage_{name}"] = float(((actual >= g[lo]) & (actual <= g[hi])).mean())
            intervals[f"width_{name}_seconds"] = float((g[hi] - g[lo]).mean())
        rows.append({
            **dict(zip(_KEYS + ["bearing_run_id"], key)), "n": int(len(g)),
            "mae_seconds": float(err.abs().mean()),
            "rmse_seconds": float(np.sqrt((err ** 2).mean())),
            "median_abs_error_seconds": float(err.abs().median()),
            "median_relative_error": float(rel.median()) if len(rel) else float("nan"),
            "nmae_life": float(err.abs().mean() / g["total_life_s"].iloc[0]),
            "n_overestimates": int((err > 0).sum()), "n_underestimates": int((err < 0).sum()),
            "overestimate_pct": float(100 * (err > 0).mean()),
            "underestimate_pct": float(100 * (err < 0).mean()),
            "naive_mae_seconds": float(naive_err.abs().mean()) if naive_err.notna().any()
            else float("nan"),
            **intervals,
            "fraction_mae": float(f_err.mean()),
            "fraction_mae_const": float(const_err.mean()),
            "fraction_skill": float(1 - f_err.mean() / const_err.mean()) if const_err.mean() > 0
            else float("nan"),
            "n_post_onset": int(post.sum()),
            "mae_post_onset_seconds": float(err[post].abs().mean()) if post.any() else float("nan"),
            "nmae_post_onset": float(err[post].abs().mean() / g["total_life_s"].iloc[0])
            if post.any() else float("nan"),
            "fraction_mae_post_onset": float(f_err[post].mean()) if post.any() else float("nan"),
            "overestimate_pct_post_onset": float(100 * (err[post] > 0).mean()) if post.any()
            else float("nan"),
            "total_life_s": float(g["total_life_s"].iloc[0]),
        })
    return pd.DataFrame(rows)


def summarize(per_bearing: pd.DataFrame) -> pd.DataFrame:
    """Per experiment/model: mean over bearings (each bearing counts once)."""
    mean_cols = [c for c in per_bearing.columns
                 if c not in _KEYS + ["bearing_run_id", "n", "n_post_onset", "total_life_s"]]
    agg = {c: (c, "mean") for c in mean_cols}
    return (per_bearing.groupby(_KEYS)
            .agg(n_bearings=("bearing_run_id", "nunique"), n_rows=("n", "sum"),
                 n_post_onset=("n_post_onset", "sum"), **agg)
            .reset_index())


def applicability_vs_error(per_bearing: pd.DataFrame, app: pd.DataFrame) -> dict:
    """Does applicability track error? Error is measured time-scale-free
    (life-fraction MAE, and skill vs the constant-0.5 guess): nMAE rewards a
    model that predicts ~0 RUL on a long-lived bearing (it caps near 0.5), so it
    cannot rank errors across datasets whose lives differ 1000x.

    `by_life_scale` is a POST-HOC split (the life-scale rule was part of the
    policy, but its separate value was only examined after the results were
    seen) - reported as hypothesis-generating, not as a tuned threshold."""
    m = per_bearing.merge(app[["experiment", "model", "bearing_run_id", "level", "shift_ratio",
                               "outlived_fraction"]],
                          on=["experiment", "model", "bearing_run_id"])
    out: dict = {"n_points": int(len(m))}
    for model, g in m.groupby("model"):
        def table(key):
            return {str(k): {"n": int(len(v)), "median_fraction_mae": float(v["fraction_mae"].median()),
                             "median_skill": float(v["fraction_skill"].median()),
                             "share_with_positive_skill": float((v["fraction_skill"] > 0).mean())}
                    for k, v in g.groupby(key)}
        out[str(model)] = {
            "n": int(len(g)),
            "spearman_shift_vs_fraction_mae": float(
                g["shift_ratio"].corr(g["fraction_mae"], method="spearman")),
            "spearman_shift_vs_nmae": float(g["shift_ratio"].corr(g["nmae_life"], method="spearman")),
            "by_level": table("level"),
            "by_life_scale_post_hoc": table(np.where(g["outlived_fraction"] > 0,
                                                     "outlived training lives",
                                                     "within training lives")),
        }
    return out


# ---------------------------------------------------------------------------
# FEMTO hidden set (11 censored test bearings) and the full experiment matrix
# ---------------------------------------------------------------------------

def hidden_set(censored: pd.DataFrame, hidden_rul: dict[str, float], models: dict,
               cals: dict, app_models: dict) -> tuple[pd.DataFrame, list[dict]]:
    """One prediction per censored bearing at its LAST recording (the IEEE PHM
    2012 convention, evaluation.score_hidden_set), against the hidden RUL
    derived from the archives. Never fit on (role test_censored)."""
    rows, apps = [], []
    for kind, model in models.items():
        for bearing, g in censored.groupby("bearing_run_id"):
            label = bearing.split(":", 1)[1]
            if label not in hidden_rul:
                continue
            last = g.sort_values("sequence_index").tail(1)
            pred = predict_rows(model, cals[kind], last, kind).iloc[0]
            actual = float(hidden_rul[label])
            rows.append({
                "experiment": "A2: FEMTO hidden set (frozen)", "category": "WITHIN-DOMAIN",
                "model": kind, "train_domains": "femto", "test_domain": "femto",
                "dataset_id": "femto", "bearing_run_id": bearing,
                "sequence_index": int(last["sequence_index"].iloc[0]),
                "elapsed_s": float(last["elapsed_s"].iloc[0]),
                "actual_rul_seconds": actual,
                "life_fraction": float(last["elapsed_s"].iloc[0]) / (float(last["elapsed_s"].iloc[0]) + actual),
                "total_life_s": float(last["elapsed_s"].iloc[0]) + actual,
                "naive_rul_seconds": np.nan, **pred.to_dict(),
            })
            a = assess(g, app_models[kind])
            apps.append({"experiment": "A2: FEMTO hidden set (frozen)",
                         "category": "WITHIN-DOMAIN", "model": kind, "bearing_run_id": bearing,
                         "level": a["level"], "shift_ratio": a["shift_ratio"],
                         "outlived_fraction": a["outlived_fraction"], "reasons": a["reasons"]})
    return pd.DataFrame(rows), apps


def run_all(df: pd.DataFrame, frozen_raw: TreeBaseline, hidden_rul: dict[str, float],
            log=print) -> dict:
    """Every experiment in docs/cross-dataset.md, in the order it is reported.
    Returns predictions, applicability rows and the fitted objects the routing
    bundle persists."""
    raw_cols = list(frozen_raw.feature_columns)
    femto = run_to_failure(df, "femto")
    rtf = run_to_failure(df)
    preds, apps = [], []

    def add(result):
        frames, app_rows = result
        preds.extend([frames] if isinstance(frames, pd.DataFrame) else frames)
        apps.extend(app_rows)

    log("A: FEMTO leave-one-bearing-out (raw, sn)")
    for kind in KINDS:
        add(lobo(femto, kind, raw_cols, "A: FEMTO -> FEMTO (LOBO)", "WITHIN-DOMAIN"))

    # Frozen FEMTO models: the raw one IS the committed artifact; the SN one is
    # fit here on the same six bearings.
    models = {"raw_seconds": frozen_raw, "sn_fraction": fit_kind(femto, "sn_fraction", raw_cols)}
    cals = {k: calibrate(femto, k, raw_cols) for k in KINDS}
    app_models = {k: fit_applicability(femto, list(m.feature_columns),
                                       life_scale_cap=LIFE_SCALE_CAP[k])
                  for k, m in models.items()}

    censored = df[df["role"] == "test_censored"]
    if len(censored) and hidden_rul:
        log("A2: FEMTO hidden set")
        h, a = hidden_set(censored, hidden_rul, models, cals, app_models)
        preds.append(h)
        apps.extend(a)

    for domain in sorted(set(rtf["dataset_id"]) - {"femto"}):
        target = run_to_failure(df, domain)
        n_bearings = target["bearing_run_id"].nunique()
        log(f"ZERO-SHOT femto -> {domain} ({n_bearings} bearings)")
        for kind in KINDS:
            add(run_split(femto, target, kind, raw_cols, f"ZS: FEMTO -> {domain}", "ZERO-SHOT",
                          model=models[kind], cal=cals[kind]))
        if n_bearings >= 2:
            log(f"WITHIN-DOMAIN {domain} LOBO; CALIBRATED femto -> {domain}")
            for kind in KINDS:
                add(lobo(target, kind, raw_cols, f"WD: {domain} -> {domain} (LOBO)",
                         "WITHIN-DOMAIN"))
            add(calibrated(femto, target, raw_cols, f"CAL: FEMTO + {domain} calibration"))

    if rtf["dataset_id"].nunique() > 1:
        log("MULTI-DATASET: LOBO over all bearings, and leave-one-domain-out")
        add(lobo(rtf, "sn_fraction", raw_cols, "MD: all datasets (LOBO)", "MULTI-DATASET"))
        add(leave_one_domain_out(rtf, raw_cols, log))

    multi = fit_kind(rtf, "sn_fraction", raw_cols)
    return {
        "predictions": pd.concat(preds, ignore_index=True),
        "applicability": pd.DataFrame(apps),
        "bundle": {
            "raw_seconds": {"model": frozen_raw, "calibrators": cals["raw_seconds"],
                            "applicability": app_models["raw_seconds"], "train": "femto",
                            "train_bearings": sorted(femto["bearing_run_id"].unique())},
            "sn_fraction_multi": {
                "model": multi, "calibrators": calibrate(rtf, "sn_fraction", raw_cols),
                "applicability": fit_applicability(rtf, SN_FEATURES, life_scale_cap=MEDIUM),
                "train": "+".join(sorted(rtf["dataset_id"].unique())),
                "train_bearings": sorted(rtf["bearing_run_id"].unique())},
        },
    }


# Cross-domain health indicators, both fit on FEMTO learning only.
#   sn_hi         all 14 SN features (amplitude + impulsiveness + spectral shape)
#   amplitude_hi  SN log-RMS and log-peak-to-peak only: energy growth, the generic
#                 degradation signature. Added AFTER the fused HI was seen to miss
#                 the college failure, whose kurtosis/crest factor FALL as its RMS
#                 rises (docs/decisions.md D26) - both are always reported.
CROSS_DOMAIN_HIS = {"sn_hi": SN_FEATURES, "amplitude_hi": ["sn_rms", "sn_peak_to_peak"]}
ROUTING_HI = "amplitude_hi"   # drives the degradation stage in cross-domain routing


def hi_evaluation(df: pd.DataFrame, reference_hi) -> dict:
    """Health indicators across datasets, each applied with that dataset's
    reference window and smoothing width, scored with health.prognostic_metrics
    on complete run-to-failure bearings. `reference_hi` is the frozen FEMTO
    reference HI on absolute features (artifacts/models/reference_hi_model.joblib).
    Stage thresholds are fit on FEMTO for each cross-domain HI."""
    from dataclasses import replace

    from bearing_pdm.domain import hi_smooth_window, reference_window, stage_persistence
    from bearing_pdm.health import apply_reference_hi, fit_reference_hi, prognostic_metrics
    from bearing_pdm.stages import assign_stages, fit_stage_thresholds

    femto = run_to_failure(df, "femto")
    models = {name: fit_reference_hi(femto, features=feats)
              for name, feats in CROSS_DOMAIN_HIS.items()}
    thresholds = {name: fit_stage_thresholds(femto, apply_reference_hi(femto, m),
                                             m.reference_skip, m.reference_n)
                  for name, m in models.items()}

    out = df[["dataset_id", "bearing_run_id", "role", "sequence_index", "elapsed_s",
              "rul_seconds", "life_fraction"]].copy()
    for dataset, g in df.groupby("dataset_id"):
        window, smooth = reference_window(dataset), hi_smooth_window(dataset)
        out.loc[g.index, "reference_hi"] = apply_reference_hi(
            g, reference_hi, window, smooth).to_numpy()
        for name, m in models.items():
            out.loc[g.index, name] = apply_reference_hi(g, m, window, smooth).to_numpy()
    for name in models:
        col = name.replace("_hi", "_stage")
        for dataset, g in out.groupby("dataset_id"):
            t = replace(thresholds[name], persistence=stage_persistence(dataset))
            out.loc[g.index, col] = assign_stages(g, g[name], t).to_numpy()

    metrics = {}
    for dataset, g in out[out["rul_seconds"].notna()].groupby("dataset_id"):
        metrics[dataset] = {hi: prognostic_metrics(g, g[hi])
                            for hi in ("reference_hi", *CROSS_DOMAIN_HIS)}
    return {"health": out, "metrics": metrics, "hi_models": models,
            "stage_thresholds": thresholds}
