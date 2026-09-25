"""Deterministic model routing - no learned or agentic decision logic.

    INPUT -> PROFILE -> QUALITY -> ADAPTER -> FEATURES -> APPLICABILITY
          -> RUL + interval            (a validated model is applicable)
          -> health/degradation only   (otherwise: RUL is suppressed)

Decision rule, applied to the candidate models in priority order:
1. Data-quality gate fails                          -> RUL_SUPPRESSED
2. A candidate is only ELIGIBLE if its own validation showed skill over the
   label-free baseline (`validated_skill` > 0: life-fraction MAE better than a
   constant 0.5 guess, experiments.bearing_metrics). A model with no measured
   skill never produces a number, however in-distribution the input looks.
3. First eligible candidate with HIGH applicability  -> RUL_AVAILABLE
4. else first eligible candidate with MEDIUM          -> RUL_EXPERIMENTAL
5. else                                               -> RUL_SUPPRESSED

Health indicator, stage, signal analysis and the applicability reasons are
returned in every case - suppression removes the RUL number, nothing else.

A bearing that was part of a candidate's training set must not be shown an
in-sample prediction as if it were validated: pass its out-of-fold predictions
(`oof`) and they are used instead; without them that candidate's RUL is
withheld for that bearing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from bearing_pdm.applicability import HIGH, LOW, MEDIUM, assess, outlived_training
from bearing_pdm.features import CLIP_FRACTION_LIMIT

RUL_AVAILABLE = "RUL_AVAILABLE"
RUL_EXPERIMENTAL = "RUL_EXPERIMENTAL"
RUL_SUPPRESSED = "RUL_SUPPRESSED"

MAX_NAN_FRACTION = 0.5
MAX_CLIPPED_RECORDINGS = 0.05


@dataclass(frozen=True)
class Candidate:
    name: str
    kind: str                       # experiments.KINDS
    model: object                   # modeling.TreeBaseline
    calibrators: dict
    applicability: object           # applicability.ApplicabilityModel
    train_bearings: frozenset[str] = field(default_factory=frozenset)
    validated_skill: float | None = None
    validation_note: str = ""
    # Held-out life-fraction skill per dataset, plus "unseen" for a machine type
    # absent from validation (raw model: mean zero-shot skill; multi-dataset
    # model: mean leave-one-domain-out skill). Resolved per bearing by skill_for.
    skill_by_dataset: dict[str, float] = field(default_factory=dict)

    def skill_for(self, dataset_id: str) -> float | None:
        if not self.skill_by_dataset:
            return self.validated_skill
        return self.skill_by_dataset.get(dataset_id, self.skill_by_dataset.get("unseen"))


def quality_gate(df: pd.DataFrame) -> tuple[bool, list[str]]:
    """(usable, reasons). Blocking: no recordings, no usable vibration channel,
    most samples missing. Non-blocking warnings: non-finite values, clipping."""
    if df.empty:
        return False, ["no recordings"]
    reasons, ok = [], True
    channels = [c for c in ("vibration_x", "vibration_y") if f"qc_{c}_constant" in df]
    usable = [c for c in channels if (df[f"qc_{c}_constant"] < 1).mean() > 0.5]
    if not usable:
        ok = False
        reasons.append("no usable vibration channel (missing or constant in most recordings)")
    for c in usable:
        nan = float(df[f"qc_{c}_nan_fraction"].median())
        if nan > MAX_NAN_FRACTION:
            ok = False
            reasons.append(f"{c}: median {nan:.0%} of samples missing")
        if df[f"qc_{c}_nonfinite"].sum() > 0:
            reasons.append(f"{c}: {int(df[f'qc_{c}_nonfinite'].sum())} non-finite samples "
                           "(treated as missing)")
        clipped = float((df[f"qc_{c}_clip_fraction"] > CLIP_FRACTION_LIMIT).mean())
        if clipped > MAX_CLIPPED_RECORDINGS:
            reasons.append(f"{c}: possible sensor saturation in {clipped:.0%} of recordings")
    return ok, reasons


def decide(quality_ok: bool, quality_reasons: list[str],
           assessed: list[tuple[Candidate, dict, bool]]) -> dict:
    """assessed: (candidate, applicability.assess result, prediction_available)."""
    reasons = list(quality_reasons)
    if not quality_ok:
        return {"status": RUL_SUPPRESSED, "model": None, "level": None,
                "reasons": ["data quality: " + r for r in quality_reasons]}
    eligible = []
    for cand, a, available in assessed:
        if cand.validated_skill is None or not cand.validated_skill > 0:
            reasons.append(f"{cand.name}: not eligible - no validated skill over the baseline "
                           f"({cand.validation_note or 'no validation result'})")
        elif not available:
            reasons.append(f"{cand.name}: bearing was in its training set and no out-of-fold "
                           "prediction exists - withheld")
        else:
            eligible.append((cand, a))
    for wanted, status in ((HIGH, RUL_AVAILABLE), (MEDIUM, RUL_EXPERIMENTAL)):
        for cand, a in eligible:
            if a["level"] == wanted:
                return {"status": status, "model": cand.name, "level": a["level"],
                        "shift_ratio": a["shift_ratio"], "validated_skill": cand.validated_skill,
                        "reasons": reasons + a["reasons"]}
    for cand, a in eligible:
        reasons += [f"{cand.name}: {LOW} applicability"] + a["reasons"]
    return {"status": RUL_SUPPRESSED, "model": None, "level": LOW, "reasons": reasons}


def recording_quality_ok(df: pd.DataFrame) -> np.ndarray:
    """Per recording (causal): at least one vibration channel present, not
    constant, and at most MAX_NAN_FRACTION of its samples missing."""
    ok = np.zeros(len(df), dtype=bool)
    for c in ("vibration_x", "vibration_y"):
        if f"qc_{c}_constant" in df:
            ok |= ((df[f"qc_{c}_constant"] < 1)
                   & (df[f"qc_{c}_nan_fraction"] <= MAX_NAN_FRACTION)).to_numpy()
    return ok


def analyze_bearing(df: pd.DataFrame, candidates: list[Candidate], hi_model, stage_thresholds,
                    reference_window: tuple[int, int],
                    oof: dict[str, pd.DataFrame] | None = None,
                    smooth_window: int | None = None) -> tuple[pd.DataFrame, dict]:
    """Route one bearing. `df`: its canonical rows WITH self-normalised features
    (domain.add_self_normalized_features).

    Per recording (`rul_status`, `rul_model`, `level_<candidate>`): the decision
    the system would have made AT that recording, from that recording and earlier
    ones only (applicability.causal_levels, per-recording quality). The returned
    dict is the retrospective whole-run summary (all recordings; used for the
    offline analysis), plus `current` = the causal decision at the last recording."""
    from dataclasses import replace

    from bearing_pdm.applicability import causal_levels, exclude_bearing
    from bearing_pdm.experiments import predict_rows
    from bearing_pdm.health import apply_reference_hi
    from bearing_pdm.stages import assign_stages

    df = df.sort_values("sequence_index")
    bearing = df["bearing_run_id"].iloc[0]
    out = df[["dataset_id", "bearing_run_id", "sequence_index", "elapsed_s"]].copy()
    if "rul_seconds" in df:
        out["actual_rul_seconds"] = df["rul_seconds"]
    out["health_indicator"] = apply_reference_hi(df, hi_model, reference_window,
                                                 smooth_window).to_numpy()
    out["stage"] = assign_stages(out, out["health_indicator"], stage_thresholds).to_numpy()

    ok, q_reasons = quality_gate(df)
    dataset = df["dataset_id"].iloc[0]
    assessed, predictions = [], {}
    for cand in candidates:
        in_training = bearing in cand.train_bearings
        skill = cand.skill_for(dataset)
        cand = replace(cand, validated_skill=skill,
                       validation_note=f"{cand.validation_note} (skill for {dataset}: "
                                       f"{'n/a' if skill is None else f'{skill:+.3f}'})",
                       # never judge a training bearing against a reference containing itself
                       applicability=exclude_bearing(cand.applicability, bearing)
                       if in_training else cand.applicability)
        a = assess(df, cand.applicability)
        if in_training and oof and cand.name in oof:
            p = oof[cand.name]
            p = p[p["bearing_run_id"] == bearing].set_index("sequence_index")
            predictions[cand.name] = p.reindex(out["sequence_index"]).set_axis(out.index)
        elif not in_training:
            predictions[cand.name] = predict_rows(cand.model, cand.calibrators, df, cand.kind)
        assessed.append((cand, a, cand.name in predictions))
        out[f"level_{cand.name}"] = causal_levels(df, cand.applicability)["level"].to_numpy()
        out[f"outlived_training_{cand.name}"] = outlived_training(df, cand.applicability)

    decision = decide(ok, q_reasons, assessed)
    decision["scope"] = "whole-run retrospective summary (all recordings)"
    decision["applicability"] = {c.name: {"level": a["level"], "shift_ratio": a["shift_ratio"],
                                          "reasons": a["reasons"]} for c, a, _ in assessed}
    decision["quality_ok"], decision["quality_reasons"] = ok, q_reasons

    # Causal, per-recording routing with the same priority rule as `decide`.
    eligible = [c for c, _, available in assessed
                if available and c.validated_skill is not None and c.validated_skill > 0]
    row_ok = recording_quality_ok(df)
    status = np.full(len(out), RUL_SUPPRESSED, dtype=object)
    model = np.full(len(out), None, dtype=object)
    for wanted, label in ((MEDIUM, RUL_EXPERIMENTAL), (HIGH, RUL_AVAILABLE)):
        # MEDIUM first, then HIGH overwrites: HIGH anywhere in the list wins.
        for cand in reversed(eligible):
            # A status needs an actual number: out-of-fold predictions do not exist
            # for a training bearing's own reference-window recordings.
            has_pred = predictions[cand.name]["predicted_rul_seconds"].notna().to_numpy()
            hit = row_ok & has_pred & (out[f"level_{cand.name}"].to_numpy() == wanted)
            status[hit], model[hit] = label, cand.name
    out["rul_status"], out["rul_model"] = status, model
    for col in ("predicted_rul_seconds", "rul_lo", "rul_hi"):
        values = np.full(len(out), np.nan)
        for name in {m for m in model if m is not None}:
            rows = model == name
            values[rows] = predictions[name][col].to_numpy()[rows]
        out[col] = values
    skills = {c.name: c.validated_skill for c in eligible}
    decision["current"] = {"status": status[-1], "model": model[-1],
                           "validated_skill": skills.get(model[-1]),
                           "scope": "causal decision at the last recording"}
    return out, decision


# Priority order: the validated in-domain model first, the experimental
# multi-dataset model second.
CANDIDATE_ORDER = (("raw_seconds", "raw_seconds"), ("sn_fraction_multi", "sn_fraction"))
# Out-of-fold experiment whose held-out predictions stand in for a bearing that
# was inside a candidate's training set.
OOF_EXPERIMENT = {"raw_seconds": ("A: FEMTO -> FEMTO (LOBO)", "raw_seconds"),
                  "sn_fraction_multi": ("MD: all datasets (LOBO)", "sn_fraction")}


def candidates_from_bundle(bundle: dict) -> list[Candidate]:
    """Routing candidates from artifacts/models/cross_domain_bundle.joblib."""
    return [Candidate(name=name, kind=kind, model=bundle[name]["model"],
                      calibrators=bundle[name]["calibrators"],
                      applicability=bundle[name]["applicability"],
                      train_bearings=frozenset(bundle[name].get("train_bearings", ())),
                      validated_skill=bundle[name].get("validated_skill"),
                      validation_note=bundle[name].get("validation_note", ""),
                      skill_by_dataset=bundle[name].get("skill_by_dataset", {}))
            for name, kind in CANDIDATE_ORDER if name in bundle]


def oof_from_predictions(pred: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {name: pred[(pred["experiment"] == exp) & (pred["model"] == kind)]
            for name, (exp, kind) in OOF_EXPERIMENT.items()}
