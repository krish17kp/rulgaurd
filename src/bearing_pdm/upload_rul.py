"""RUL for an uploaded dataset whose bearings ran to failure, learned and tested on
that dataset alone.

Fixed before any upload was seen, not chosen per dataset: the `raw_seconds`
ExtraTrees of experiments.py (the project's primary model, the frozen FEMTO
pipeline's feature columns -> RUL seconds), scored leave-one-bearing-out with
`run_split` - the held-out bearing never touches the model, the conformal
calibration or the applicability fit. RUL is shown only when the held-out MAE,
averaged over bearings, beats the naive mean-life baseline fit on the same
training bearings. The FEMTO artifacts are never refit."""

from __future__ import annotations

import pandas as pd

from bearing_pdm.experiments import bearing_metrics, prepare, run_split, run_to_failure

MIN_BEARINGS = 3        # one held out, >= 2 to learn from and calibrate on
MIN_FEATURE_COVERAGE = 0.8
_TRAJ = ["sequence_index", "elapsed_s", "actual_rul_seconds", "predicted_rul_seconds",
         "rul_lo", "rul_hi", "naive_rul_seconds"]


def dataset_rul(frames: list[pd.DataFrame], reference: tuple[int, int],
                raw_columns: list[str], progress=print) -> dict:
    df = prepare(frames, reference)
    rtf = run_to_failure(df)
    bearings = sorted(rtf["bearing_run_id"].unique())
    base = {"n_bearings": len(bearings), "min_bearings": MIN_BEARINGS,
            "model": "ExtraTrees (raw_seconds), leave-one-bearing-out on this dataset"}
    if len(bearings) < MIN_BEARINGS:
        return {**base, "status": "no_failure_data" if not bearings else "too_few_bearings"}
    # A channel this dataset lacks (e.g. no second vibration axis) cannot be a feature.
    cols = [c for c in raw_columns if c in rtf and rtf[c].notna().mean() >= MIN_FEATURE_COVERAGE]
    preds = []
    for i, b in enumerate(bearings, 1):
        progress(f"RUL test {i}/{len(bearings)}: training without {b}, predicting it")
        p, _ = run_split(rtf[rtf["bearing_run_id"] != b], rtf[rtf["bearing_run_id"] == b],
                         "raw_seconds", cols, "UPLOAD: within-dataset LOBO", "WITHIN-DOMAIN")
        preds.append(p)
    pred = pd.concat(preds, ignore_index=True)
    per = bearing_metrics(pred)
    mae, naive = float(per["mae_seconds"].mean()), float(per["naive_mae_seconds"].mean())
    out = {**base, "status": "validated" if mae < naive else "not_better_than_naive",
           "n_features": len(cols), "mae_seconds": mae, "naive_mae_seconds": naive,
           "skill_vs_naive": 1 - mae / naive if naive > 0 else None,
           "nmae_life": float(per["nmae_life"].mean()),
           "interval_coverage": float(per["coverage_conformal"].mean()), "interval_target": 0.9,
           "per_bearing": [{"bearing": r.bearing_run_id, "n": int(r.n), "mae_seconds": r.mae_seconds,
                            "naive_mae_seconds": r.naive_mae_seconds,
                            "coverage": r.coverage_conformal, "total_life_s": r.total_life_s}
                           for r in per.itertuples()]}
    if out["status"] == "validated":   # held-out predictions only: no bearing predicts itself
        out["trajectories"] = {b: g.sort_values("sequence_index")[_TRAJ].to_dict(orient="records")
                               for b, g in pred.groupby("bearing_run_id")}
    return out
