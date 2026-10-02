"""Applicability/OOD, uncertainty, cross-domain features, leakage guards and
routing. Synthetic data with known structure, so every expectation is exact
or statistically guaranteed - no dataset files needed."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import ExtraTreesRegressor

from bearing_pdm import experiments as E
from bearing_pdm.applicability import HIGH, LOW, MEDIUM, assess, fit_applicability
from bearing_pdm.domain import SN_FEATURES, add_self_normalized_features, after_reference_window
from bearing_pdm.health import prognostic_metrics
from bearing_pdm.modeling import fraction_to_rul
from bearing_pdm.routing import (
    RUL_AVAILABLE,
    RUL_EXPERIMENTAL,
    RUL_SUPPRESSED,
    Candidate,
    decide,
    quality_gate,
)
from bearing_pdm.uncertainty import (
    conformal_interval,
    fit_conformal,
    tree_predictions,
)

FEATS = ["f1", "f2", "f3"]


def _bearings(n_bearings=4, n=200, shift=0.0, role="learning", seed=0, life_s=1000.0):
    rng = np.random.default_rng(seed)
    rows = []
    for b in range(n_bearings):
        x = rng.normal(shift, 1.0, size=(n, 3))
        elapsed = np.linspace(0, life_s, n)
        rows.append(pd.DataFrame(x, columns=FEATS).assign(
            dataset_id="xjtu", bearing_run_id=f"xjtu:B{seed}_{b}", role=role,
            sequence_index=np.arange(n), elapsed_s=elapsed, rul_seconds=life_s - elapsed,
            sample_rate_hz=25600.0, rpm=2000.0, radial_load_n=10000.0))
    return pd.concat(rows, ignore_index=True)


# ---------------------------------------------------------------------------
# Applicability
# ---------------------------------------------------------------------------

def test_in_domain_bearing_is_high_and_shifted_bearing_is_low():
    model = fit_applicability(_bearings(), FEATS)
    assert assess(_bearings(1, seed=5), model)["level"] == HIGH
    far = assess(_bearings(1, shift=10.0, seed=6), model)
    assert far["level"] == LOW and far["shift_ratio"] > 2
    assert any("robust z" in r for r in far["reasons"])


def test_missing_feature_and_metadata_are_reported():
    model = fit_applicability(_bearings(), FEATS)
    missing = _bearings(1, seed=7).assign(f3=np.nan)
    a = assess(missing, model)
    assert a["level"] == LOW and a["missing_features"] == ["f3"]
    fast = _bearings(1, seed=8).assign(rpm=3000.0, sample_rate_hz=20000.0)
    a = assess(fast, model)
    assert a["level"] == MEDIUM
    assert any("speed" in r for r in a["reasons"]) and any("sampling rate" in r for r in a["reasons"])


def test_single_recording_missing_cap_uses_fraction_not_worst_column():
    """Regression for a defect found integrating applicability.py into the
    online prediction API (api.py's _assess_applicability): assess() was
    designed to summarise a whole bearing RUN (many rows), where
    `isna().mean()` per column answers "what fraction of recordings lack
    this feature" and the worst (max) column is the right run-level signal.
    Applied to exactly ONE recording's feature row, that same per-column
    mean is just a 0/1 indicator, so max() trips LOW the instant even one of
    many features is absent - however small a fraction of the whole feature
    set that is. single_recording=True must use the mean of that indicator
    (the fraction of the feature set actually present) instead."""
    model = fit_applicability(_bearings(), FEATS)
    one = _bearings(1, seed=9).iloc[[0]].assign(f3=np.nan)  # 1 of 3 features missing (33%)

    default = assess(one, model)
    assert default["level"] == LOW  # old (run-level) semantics: max() -> 100% "missing"

    single = assess(one, model, single_recording=True)
    assert single["level"] == MEDIUM  # correct: 1/3 features actually absent -> partial, not absent
    assert single["missing_features"] == ["f3"]


def test_life_time_scale_caps_level_by_target_type():
    train = _bearings()
    long_lived = _bearings(1, seed=9, life_s=10_000.0)      # outlives every training bearing
    assert assess(long_lived, fit_applicability(train, FEATS, life_scale_cap=LOW))["level"] == LOW
    a = assess(long_lived, fit_applicability(train, FEATS, life_scale_cap=MEDIUM))
    assert a["level"] == MEDIUM and a["outlived_fraction"] > 0.8


@pytest.mark.parametrize("role", ["test_censored", "full_test", "survivor"])
def test_applicability_refuses_to_fit_on_held_out_roles(role):
    with pytest.raises(ValueError, match="Refusing to fit"):
        fit_applicability(_bearings(role=role), FEATS)


# ---------------------------------------------------------------------------
# Uncertainty
# ---------------------------------------------------------------------------

def test_tree_predictions_average_to_the_forest_prediction():
    rng = np.random.default_rng(0)
    x, y = rng.normal(size=(200, 3)), rng.normal(size=200)
    forest = ExtraTreesRegressor(n_estimators=20, random_state=42).fit(x, y)
    per_tree = tree_predictions(forest, x)
    assert per_tree.shape == (20, 200)
    np.testing.assert_allclose(per_tree.mean(axis=0), forest.predict(x))


@pytest.mark.parametrize("normalized", [True, False])
def test_conformal_reaches_nominal_coverage_on_exchangeable_groups(normalized):
    """30 calibration and 30 test bearings from the same law: coverage ~ 90%."""
    rng = np.random.default_rng(1)

    def draw(n_groups):
        sigma = rng.uniform(0.5, 2.0, size=n_groups * 50)
        y_pred = rng.normal(size=sigma.size)
        return (y_pred + rng.normal(0, sigma), y_pred, sigma,
                np.repeat(np.arange(n_groups), 50))

    cal = fit_conformal(*draw(30), alpha=0.1, normalized=normalized)
    y, y_pred, sigma, _ = draw(30)
    lo, hi = conformal_interval(y_pred, sigma, cal, lower_bound=-np.inf)
    assert 0.86 <= np.mean((y >= lo) & (y <= hi)) <= 0.96


def test_conformal_weights_each_bearing_equally():
    """One long bearing with tiny errors must not shrink the quantile for all."""
    y_pred = np.zeros(1100)
    y = np.concatenate([np.full(1000, 0.01), np.linspace(1, 2, 100)])
    groups = np.array([0] * 1000 + [1] * 50 + [2] * 50)
    cal = fit_conformal(y, y_pred, np.zeros(1100), groups, normalized=False)
    assert cal.quantile > 1.0
    with pytest.raises(ValueError, match=">= 2 bearings"):
        fit_conformal(y[:10], y_pred[:10], np.zeros(10), np.zeros(10))


# ---------------------------------------------------------------------------
# Self-normalised features
# ---------------------------------------------------------------------------

def _canonical_like(scale=1.0, n=40, late_spike=False):
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"dataset_id": "xjtu", "bearing_run_id": "xjtu:B", "sequence_index":
                       np.arange(n)})
    for ch in ("vibration_x", "vibration_y"):
        for feat in ("rms", "peak_to_peak", "crest_factor", "impulse_factor", "shape_factor",
                     "clearance_factor", "spectral_centroid_hz", "frequency_rms_hz"):
            df[f"{ch}_{feat}"] = rng.uniform(1, 2, n) * (scale if feat in ("rms", "peak_to_peak")
                                                          else 1.0)
        for feat in ("kurtosis", "skewness", "spectral_entropy", "band_energy_frac_low",
                     "band_energy_frac_mid", "band_energy_frac_high"):
            df[f"{ch}_{feat}"] = rng.uniform(0, 1, n)
    if late_spike:
        df.loc[35:, "vibration_x_rms"] *= 100
    return df


def test_sn_features_are_unit_invariant():
    """g vs m/s^2 (x 9.80665) must not change any self-normalised feature."""
    a = add_self_normalized_features(_canonical_like(1.0))
    b = add_self_normalized_features(_canonical_like(9.80665))
    np.testing.assert_allclose(a[SN_FEATURES].to_numpy(), b[SN_FEATURES].to_numpy(), atol=1e-12)


def test_sn_features_are_causal():
    """Changing late recordings must not change any earlier recording's value."""
    a = add_self_normalized_features(_canonical_like())
    b = add_self_normalized_features(_canonical_like(late_spike=True))
    np.testing.assert_allclose(a.loc[:34, SN_FEATURES].to_numpy(), b.loc[:34, SN_FEATURES].to_numpy())
    assert (b.loc[35:, "sn_rms"] > a.loc[35:, "sn_rms"]).all()
    # xjtu reference window = (2, 10): rows 0-11 are not evaluated
    assert after_reference_window(a).tolist() == [False] * 12 + [True] * 28


# ---------------------------------------------------------------------------
# Leakage guards in the experiment harness
# ---------------------------------------------------------------------------

def _prepared():
    frames = []
    for i in range(5):
        df = _canonical_like()
        df["bearing_run_id"] = f"xjtu:B{i}"
        df["role"] = "run_to_failure"
        df["elapsed_s"] = np.arange(len(df)) * 60.0
        df["rul_seconds"] = df["elapsed_s"].max() - df["elapsed_s"]
        df["life_fraction"] = df["elapsed_s"] / df["elapsed_s"].max()
        df["sample_rate_hz"] = 25600.0
        # a degradation signal the model can learn
        df["vibration_x_rms"] *= 1 + 3 * df["life_fraction"] ** 4
        frames.append(df)
    return E.prepare(frames)


def test_split_refuses_bearing_overlap():
    df = _prepared()
    with pytest.raises(AssertionError, match="Bearing-level leakage"):
        E.run_split(df, df[df["bearing_run_id"] == "xjtu:B0"], "sn_fraction", [], "x", "y")


def test_test_bearing_labels_cannot_influence_model_or_calibration():
    """Corrupting the held-out bearing's labels must leave every prediction and
    interval unchanged - they are only used for scoring."""
    df = _prepared()
    train, test = df[df["bearing_run_id"] != "xjtu:B4"], df[df["bearing_run_id"] == "xjtu:B4"]
    p1, _ = E.run_split(train, test, "sn_fraction", [], "x", "y")
    corrupted = test.assign(rul_seconds=test["rul_seconds"] * 1e6, life_fraction=0.123)
    p2, _ = E.run_split(train, corrupted, "sn_fraction", [], "x", "y")
    for col in ("predicted_rul_seconds", "rul_lo", "rul_hi", "rul_lo_abs", "rul_hi_abs"):
        np.testing.assert_array_equal(p1[col].to_numpy(), p2[col].to_numpy())


def test_fit_refuses_censored_rows():
    df = _prepared().assign(role="test_censored")
    with pytest.raises(ValueError, match="Refusing to fit"):
        E.fit_kind(df, "sn_fraction", [])


def test_fraction_to_rul_is_exact_and_monotone():
    elapsed = np.array([100.0, 100.0, 100.0])
    np.testing.assert_allclose(fraction_to_rul(np.array([0.5, 0.25, 1.0]), elapsed),
                               [100.0, 300.0, 0.0])
    f = np.linspace(0.05, 1, 50)
    assert np.all(np.diff(fraction_to_rul(f, np.full(50, 10.0))) < 0)


def test_prognostic_metrics_on_ideal_hi():
    frames = []
    for b, life in (("a", 100), ("b", 200)):
        seq = np.arange(life)
        frames.append(pd.DataFrame({"bearing_run_id": b, "sequence_index": seq,
                                    "elapsed_s": seq * 10.0, "rul_seconds": (life - 1 - seq) * 10.0,
                                    "hi": 1 - seq / (life - 1)}))
    df = pd.concat(frames, ignore_index=True)
    m = prognostic_metrics(df, df["hi"])
    assert m["monotonicity_mean"] == pytest.approx(1.0)
    # end values are medians over the last 5% of each run, so ~1, not exactly 1
    assert m["prognosability"] == pytest.approx(1.0, abs=0.01)
    assert m["trendability_min_abs_spearman"] == pytest.approx(1.0)
    assert m["spearman_rul_mean"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Routing / suppression
# ---------------------------------------------------------------------------

def _cand(name, skill=0.3):
    return Candidate(name=name, kind="raw_seconds", model=None, calibrators={},
                     applicability=None, validated_skill=skill, validation_note="test")


def _a(level):
    return {"level": level, "shift_ratio": {HIGH: 0.5, MEDIUM: 1.5, LOW: 5.0}[level],
            "reasons": [f"{level} reason"]}


def test_routing_available_experimental_suppressed():
    assert decide(True, [], [(_cand("m"), _a(HIGH), True)])["status"] == RUL_AVAILABLE
    assert decide(True, [], [(_cand("m"), _a(MEDIUM), True)])["status"] == RUL_EXPERIMENTAL
    low = decide(True, [], [(_cand("m"), _a(LOW), True)])
    assert low["status"] == RUL_SUPPRESSED and low["model"] is None
    assert any("LOW reason" in r for r in low["reasons"])


def test_routing_prefers_first_high_candidate_over_medium():
    d = decide(True, [], [(_cand("a"), _a(MEDIUM), True), (_cand("b"), _a(HIGH), True)])
    assert (d["status"], d["model"]) == (RUL_AVAILABLE, "b")


def test_model_without_validated_skill_never_outputs_rul():
    d = decide(True, [], [(_cand("m", skill=-0.1), _a(HIGH), True)])
    assert d["status"] == RUL_SUPPRESSED
    assert any("no validated skill" in r for r in d["reasons"])
    assert decide(True, [], [(_cand("m", skill=None), _a(HIGH), True)])["status"] == RUL_SUPPRESSED


def test_in_sample_bearing_without_out_of_fold_prediction_is_withheld():
    d = decide(True, [], [(_cand("m"), _a(HIGH), False)])
    assert d["status"] == RUL_SUPPRESSED and any("training set" in r for r in d["reasons"])


def test_quality_gate_blocks_dead_channels_and_suppresses_rul():
    dead = pd.DataFrame({f"qc_vibration_{c}_{k}": v for c in "xy"
                         for k, v in (("constant", [1.0] * 3), ("nan_fraction", [1.0] * 3),
                                      ("nonfinite", [0.0] * 3), ("clip_fraction", [0.0] * 3))})
    ok, reasons = quality_gate(dead)
    assert not ok and "no usable vibration channel" in reasons[0]
    d = decide(ok, reasons, [(_cand("m"), _a(HIGH), True)])
    assert d["status"] == RUL_SUPPRESSED and d["reasons"][0].startswith("data quality")
    assert quality_gate(pd.DataFrame())[0] is False


# ---------------------------------------------------------------------------
# Causal (per-recording) applicability and routing - independent review finding
# ---------------------------------------------------------------------------

def test_causal_levels_use_only_the_past():
    from bearing_pdm.applicability import causal_levels
    model = fit_applicability(_bearings(), FEATS)
    b = _bearings(1, seed=11)
    b.loc[b.index[60:], FEATS] += 25.0             # drift dominates 70% of the record
    full = causal_levels(b, model)
    early = causal_levels(b.iloc[:55], model)
    pd.testing.assert_frame_equal(full.iloc[:55], early)    # future rows change nothing
    assert full["level"].iloc[50] == HIGH and full["level"].iloc[-1] == LOW
    # at the last recording the causal level equals the whole-run summary
    assert full["level"].iloc[-1] == assess(b, model)["level"]


def test_partly_missing_feature_caps_at_medium():
    model = fit_applicability(_bearings(), FEATS)
    b = _bearings(1, seed=12)
    b.loc[b.index[:60], "f2"] = np.nan              # 30% missing
    a = assess(b, model)
    assert a["level"] == MEDIUM and any("partly missing" in r for r in a["reasons"])
    # Regression: api.py's _classify attributes a RETRAIN_REQUIRED downgrade
    # to its cause using missing_features/partial_features - a feature only
    # partly missing (not >50%, so absent from missing_features) must still
    # be visible via partial_features, or a multi-window upload whose only
    # problem is a partly-dropped channel gets a vacuous "due to the
    # applicability check" message with no real cause named.
    assert a["missing_features"] == []
    assert a["partial_features"] == ["f2"]


def test_analyze_bearing_decisions_are_causal():
    """Routing recording k must not depend on recordings after k."""
    from bearing_pdm.health import fit_reference_hi
    from bearing_pdm.routing import analyze_bearing
    from bearing_pdm.stages import fit_stage_thresholds

    df = _prepared()
    train = df[df["bearing_run_id"] != "xjtu:B4"].assign(role="learning")
    test = df[df["bearing_run_id"] == "xjtu:B4"]
    model = E.fit_kind(train, "sn_fraction", [])
    cand = Candidate(name="sn", kind="sn_fraction", model=model,
                     calibrators=E.calibrate(train, "sn_fraction", []),
                     applicability=fit_applicability(train, SN_FEATURES), validated_skill=0.2)
    hi = fit_reference_hi(train, features=["sn_rms"], skip=2, n_ref=10, smooth_window=3)
    from bearing_pdm.health import apply_reference_hi
    thresholds = fit_stage_thresholds(train, apply_reference_hi(train, hi), 2, 10)
    qc = {f"qc_vibration_{c}_{k}": v for c in "xy"
          for k, v in (("constant", 0.0), ("nan_fraction", 0.0), ("nonfinite", 0.0),
                       ("clip_fraction", 0.0))}
    test = test.assign(**qc)
    full, decision = analyze_bearing(test, [cand], hi, thresholds, (2, 10))
    part, _ = analyze_bearing(test.iloc[:25], [cand], hi, thresholds, (2, 10))
    cols = ["rul_status", "rul_model", "level_sn", "predicted_rul_seconds"]
    pd.testing.assert_frame_equal(full[cols].iloc[:25], part[cols])
    assert decision["current"]["status"] == full["rul_status"].iloc[-1]
    assert decision["scope"].startswith("whole-run")


def test_training_bearing_is_not_judged_against_itself():
    """In-sample distance is ~0 (always HIGH); excluding the bearing must restore
    an honest out-of-sample distance and drop its own in-domain threshold."""
    from bearing_pdm.applicability import exclude_bearing, recording_distances
    train = _bearings(4)
    train.loc[train["bearing_run_id"] == "xjtu:B0_3", FEATS] += 6.0   # one unusual bearing
    model = fit_applicability(train, FEATS)
    own = train[train["bearing_run_id"] == "xjtu:B0_3"]
    inside = np.median(recording_distances(own, model))
    held_out = exclude_bearing(model, "xjtu:B0_3")
    assert "xjtu:B0_3" not in held_out.in_domain_distances
    assert np.median(recording_distances(own, held_out)) > 5 * inside


def test_skill_is_resolved_per_dataset_with_unseen_fallback():
    c = Candidate(name="m", kind="raw_seconds", model=None, calibrators={}, applicability=None,
                  skill_by_dataset={"femto": 0.3, "college": -0.7, "unseen": -0.4})
    assert c.skill_for("femto") == 0.3 and c.skill_for("college") == -0.7
    assert c.skill_for("new_rig") == -0.4          # never-seen machine type -> no skill
    assert decide(True, [], [(_cand("m", skill=c.skill_for("new_rig")), _a(HIGH), True)])[
        "status"] == RUL_SUPPRESSED


def test_no_status_without_a_prediction():
    """Out-of-fold predictions skip a training bearing's reference window; those
    recordings must be SUPPRESSED, never 'available' with an empty number."""
    from bearing_pdm.health import apply_reference_hi, fit_reference_hi
    from bearing_pdm.routing import analyze_bearing
    from bearing_pdm.stages import fit_stage_thresholds

    df = _prepared()
    train = df.assign(role="learning")
    bearing = "xjtu:B4"
    test = df[df["bearing_run_id"] == bearing].assign(
        **{f"qc_vibration_{c}_{k}": 0.0 for c in "xy"
           for k in ("constant", "nan_fraction", "nonfinite", "clip_fraction")})
    cand = Candidate(name="sn", kind="sn_fraction", model=E.fit_kind(train, "sn_fraction", []),
                     calibrators=E.calibrate(train, "sn_fraction", []),
                     applicability=fit_applicability(train, SN_FEATURES), validated_skill=0.2,
                     train_bearings=frozenset({bearing}))
    oof = test[test["evaluable"]][["bearing_run_id", "sequence_index"]].assign(
        predicted_rul_seconds=100.0, rul_lo=50.0, rul_hi=150.0)
    hi = fit_reference_hi(train, features=["sn_rms"], skip=2, n_ref=10, smooth_window=3)
    thresholds = fit_stage_thresholds(train, apply_reference_hi(train, hi), 2, 10)
    out, _ = analyze_bearing(test, [cand], hi, thresholds, (2, 10), oof={"sn": oof})
    early = out["sequence_index"] < 12
    assert (out.loc[early, "rul_status"] == RUL_SUPPRESSED).all()
    shown = out["rul_status"] != RUL_SUPPRESSED
    assert out.loc[shown, "predicted_rul_seconds"].notna().all()
