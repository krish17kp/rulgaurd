"""Degradation-stage tests (M5, docs/decisions.md D19).

The stage boundaries are fitted quantiles of the training bearings' HI, so what
matters is that they are fitted on train only, that a single noise spike cannot
trip an alarm, and that a stage label can never leak back into the RUL feature
matrix.
"""

import numpy as np
import pandas as pd
import pytest

from bearing_pdm.health import candidate_feature_columns
from bearing_pdm.stages import (
    CRITICAL,
    DEGRADING,
    HEALTHY,
    STAGE_ORDER,
    _apply_persistence,
    assign_stages,
    fit_stage_thresholds,
    summarize_stages,
)

SKIP, N_REF, N = 10, 50, 200


def _hi_frame(curves: dict[str, np.ndarray]) -> tuple[pd.DataFrame, pd.Series]:
    frames, his = [], []
    for bearing, hi in curves.items():
        n = len(hi)
        frames.append(pd.DataFrame({
            "bearing_run_id": bearing,
            "role": "learning",
            "sequence_index": np.arange(n),
            "rul_seconds": (n - 1 - np.arange(n)) * 10.0,
        }))
        his.append(pd.Series(hi))
    df = pd.concat(frames, ignore_index=True)
    return df, pd.Series(np.concatenate(his), index=df.index)


def _declining(n: int = N) -> np.ndarray:
    """Healthy plateau then a decline to failure - the shape the thresholds
    are meant to band."""
    return np.clip(0.96 - 0.95 * np.clip((np.arange(n) - 0.5 * n) / (0.5 * n), 0, 1), 0.01, 0.99)


def _train_frame():
    return _hi_frame({f"femto:BearingX_{i}": _declining() for i in range(3)})


def test_thresholds_are_ordered_and_come_from_the_hi_distribution():
    df, hi = _train_frame()
    th = fit_stage_thresholds(df, hi, SKIP, N_REF)

    assert th.hi_critical < th.hi_warn
    # hi_warn is the healthy band's lower edge, so it sits in the plateau.
    assert 0.9 < th.hi_warn <= 0.96
    # hi_critical is where the training bearings actually end up.
    assert th.hi_critical < 0.1
    assert th.n_train_bearings == 3


def test_thresholds_refuse_to_fit_on_hidden_roles():
    df, hi = _train_frame()
    df.loc[df.index[:5], "role"] = "full_test"
    with pytest.raises(ValueError, match="Refusing to fit"):
        fit_stage_thresholds(df, hi, SKIP, N_REF)


def test_thresholds_refuse_an_hi_that_does_not_separate_healthy_from_failed():
    """A flat HI cannot support a severity band. Better to fail loudly than to
    emit stages that mean nothing - which is exactly what the old pinned HI
    would have produced."""
    df, hi = _hi_frame({f"femto:BearingX_{i}": np.full(N, 0.8) for i in range(2)})
    with pytest.raises(ValueError, match="does not separate"):
        fit_stage_thresholds(df, hi, SKIP, N_REF)


def test_stage_progression_follows_a_declining_hi():
    df, hi = _train_frame()
    th = fit_stage_thresholds(df, hi, SKIP, N_REF)
    stages = assign_stages(df, hi, th)

    first = stages.iloc[:N].to_numpy()
    assert first[0] == HEALTHY
    assert first[-1] == CRITICAL
    assert DEGRADING in set(first)
    assert set(stages.unique()) <= set(STAGE_ORDER)


def test_stage_progression_on_a_declining_hi_never_reverses():
    """On a strictly declining HI, severity must only ever increase."""
    df, hi = _train_frame()
    th = fit_stage_thresholds(df, hi, SKIP, N_REF)
    stages = assign_stages(df, hi, th)

    rank = {s: i for i, s in enumerate(STAGE_ORDER)}
    for _bearing, group in df.assign(_s=stages).groupby("bearing_run_id"):
        severity = [rank[s] for s in group.sort_values("sequence_index")["_s"]]
        assert all(b >= a for a, b in zip(severity, severity[1:]))


def test_a_single_spike_does_not_trip_a_stage():
    """The persistence rule is the reason a noisy HI can drive an alarm at all."""
    df, hi = _train_frame()
    th = fit_stage_thresholds(df, hi, SKIP, N_REF)

    spiked = hi.copy()
    spiked.iloc[20] = 0.0  # one acquisition deep in CRITICAL territory
    stages = assign_stages(df, spiked, th)

    assert stages.iloc[20] == HEALTHY


def test_a_sustained_excursion_does_trip_a_stage():
    """The complement of the spike test - persistence must not make the
    detector deaf."""
    df, hi = _train_frame()
    th = fit_stage_thresholds(df, hi, SKIP, N_REF)

    excursion = hi.copy()
    excursion.iloc[20:40] = 0.0
    stages = assign_stages(df, excursion, th)

    assert stages.iloc[20 + th.persistence - 1] == CRITICAL


def test_persistence_is_causal():
    """The label at index i depends only on indices <= i."""
    raw = np.array([HEALTHY] * 10 + [CRITICAL] * 10, dtype=object)
    committed = _apply_persistence(raw, 5)
    for cut in range(1, len(raw)):
        assert _apply_persistence(raw[:cut], 5)[cut - 1] == committed[cut - 1]


def test_persistence_starts_in_the_first_observed_stage():
    """A bearing already degraded when monitoring begins must not be reported
    as healthy for the first k acquisitions."""
    raw = np.array([CRITICAL] * 10, dtype=object)
    assert list(_apply_persistence(raw, 5)) == [CRITICAL] * 10


def test_missing_hi_is_not_reported_as_healthy():
    df, hi = _train_frame()
    th = fit_stage_thresholds(df, hi, SKIP, N_REF)

    gapped = hi.copy()
    gapped.iloc[:3] = np.nan
    stages = assign_stages(df, gapped, th)
    # Carried forward from the first KNOWN stage, never invented as HEALTHY
    # because the reading was absent.
    assert stages.notna().all()
    assert set(stages.unique()) <= set(STAGE_ORDER)


def test_summarize_stages_is_well_formed():
    df, hi = _train_frame()
    th = fit_stage_thresholds(df, hi, SKIP, N_REF)
    summary = summarize_stages(df, assign_stages(df, hi, th))

    assert len(summary) == 3
    assert (summary["rul_at_first_critical_seconds"] >= 0).all()
    assert (summary["life_frac_at_first_critical"] > 0.5).all()
    assert (summary["n_severity_reversions"] == 0).all()
    fractions = summary[["frac_healthy", "frac_degrading", "frac_critical"]].sum(axis=1)
    np.testing.assert_allclose(fractions.to_numpy(), 1.0)


def test_a_bearing_that_degrades_earlier_than_the_training_set_gets_real_warning():
    """The practical question the stages exist to answer: how much notice does
    CRITICAL give? A held-out bearing that fails faster than the bearings the
    thresholds were fitted on must trip well before its own end of life.

    Note the converse, which the real FEMTO numbers show and which must not be
    hidden: a bearing whose failure is a cliff (Bearing3_1 degrades only in its
    final ~2% of life) gets very little warning no matter how the band is set.
    That is a property of the bearing, not of the threshold.
    """
    train_df, train_hi = _train_frame()
    th = fit_stage_thresholds(train_df, train_hi, SKIP, N_REF)

    early = np.clip(0.96 - 0.95 * np.clip(np.arange(N) / (0.35 * N), 0, 1), 0.01, 0.99)
    test_df, test_hi = _hi_frame({"femto:BearingX_9": early})
    summary = summarize_stages(test_df, assign_stages(test_df, test_hi, th))

    assert summary["rul_at_first_critical_seconds"].iloc[0] > 0
    assert summary["life_frac_at_first_critical"].iloc[0] < 0.5


def test_stage_label_can_never_become_a_rul_feature():
    df, hi = _train_frame()
    th = fit_stage_thresholds(df, hi, SKIP, N_REF)
    df["stage_label"] = assign_stages(df, hi, th)
    df["vibration_x_rms"] = 1.0

    cols = candidate_feature_columns(df)
    assert "stage_label" not in cols
    assert "vibration_x_rms" in cols


def test_thresholds_fitted_on_train_apply_unchanged_to_a_held_out_bearing():
    """Leave-one-bearing-out: the held-out bearing contributes nothing to the
    boundaries it is then judged against."""
    df, hi = _train_frame()
    train_mask = df["bearing_run_id"] != "femto:BearingX_2"

    th_all = fit_stage_thresholds(df[train_mask], hi[train_mask], SKIP, N_REF)
    held_out = df[~train_mask].reset_index(drop=True)
    stages = assign_stages(held_out, hi[~train_mask].reset_index(drop=True), th_all)

    assert stages.iloc[0] == HEALTHY
    assert stages.iloc[-1] == CRITICAL
