"""Streamlit startup smoke test (command.md section 19: "Streamlit
import/startup where feasible"). Uses Streamlit's built-in AppTest
framework - runs the real script headlessly, no browser needed. Streamlit
framework - runs the real script headlessly, no browser needed. The five
views are a sidebar radio, so each one is selected explicitly before it is
asserted on (see `_open`).

Requires real cached artifacts (feature batches, fitted models) to exist -
skipped if they don't, since this is an integration check against this
machine's actual config/data_paths.toml, not a unit test with fixtures.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

DASHBOARD_PATH = Path(__file__).parent.parent / "src" / "bearing_pdm" / "dashboard.py"
DUCKDB_PATH = Path(__file__).parent.parent / "artifacts" / "metadata.duckdb"

pytestmark = pytest.mark.skipif(
    not DUCKDB_PATH.exists(), reason="no cached feature batches - run scripts/build_features.py first"
)


def test_dashboard_runs_without_exception():
    at = AppTest.from_file(str(DASHBOARD_PATH), default_timeout=120)
    at.run()
    assert not at.exception, f"Dashboard raised: {at.exception}"


def test_dashboard_offers_all_five_views():
    at = AppTest.from_file(str(DASHBOARD_PATH), default_timeout=120)
    at.run()
    assert at.sidebar.radio[0].options == [
        "Signal & FFT", "Health Indicator", "RUL Prediction",
        "Model Evaluation", "Architecture & Limitations",
        "Universal Machine Analysis", "Cross-Dataset Validation",
        "Raw / ZIP / Bundle Explorer", "Experiment Lab (CWRU / Paderborn / Synthetic)",
    ]


def test_raw_explorer_view_renders_without_exception():
    """Phase K: new local full-research-mode view (raw folder / bearing ZIP /
    analysis bundle). Must render with no input selected yet, with no
    network/credential requirement, and must never run the pipeline until an
    explicit 'Run Analysis' button is pressed."""
    at = _open("Raw / ZIP / Bundle Explorer")
    assert not at.exception
    assert at.selectbox[0].options == [
        "Raw folder (FEMTO role / college)",
        "Raw FEMTO bearing ZIP",
        "RULGuard Analysis Bundle (.rulguard.zip)",
    ]


def test_raw_explorer_browses_femto_learning_set_read_only():
    at = _open("Raw / ZIP / Bundle Explorer")
    fixture_root = Path(__file__).parent.parent / "data" / "fixtures" / "femto"
    at.text_input[0].set_value(str(fixture_root)).run()
    assert not at.exception
    assert "role: **learning**" in " ".join(i.value for i in at.info)


def test_raw_explorer_loads_a_real_analysis_bundle(tmp_path):
    from bearing_pdm.analysis_bundle import build_bundle

    bundle_path = tmp_path / "tiny.rulguard.zip"
    build_bundle("femto:TestBearing", {"actual_rul_seconds": 123.0}, bundle_path)

    at = _open("Raw / ZIP / Bundle Explorer")
    at.selectbox[0].select("RULGuard Analysis Bundle (.rulguard.zip)").run()
    assert not at.exception
    # AppTest's file_uploader has no programmatic upload API, so this only
    # confirms the mode renders; the loader itself is covered directly by
    # tests/test_analysis_bundle.py's round-trip parity tests.
    assert at.file_uploader


def test_experiment_lab_cwru_shows_fault_diagnosis_and_no_rul():
    at = _open("Experiment Lab (CWRU / Paderborn / Synthetic)")
    at.selectbox[0].select("CWRU (real, fault diagnosis)").run()
    assert not at.exception
    at.button(key="lab_cwru_load").click().run()
    assert not at.exception
    text = " ".join(i.value for i in at.error) + " ".join(i.value for i in at.info)
    assert "FAULT DIAGNOSIS" in text
    assert "RUL evaluation unavailable" in text


def test_experiment_lab_paderborn_shows_fault_diagnosis_and_no_rul():
    at = _open("Experiment Lab (CWRU / Paderborn / Synthetic)")
    at.selectbox[0].select("Paderborn (real, fault diagnosis)").run()
    assert not at.exception
    at.button(key="lab_paderborn_load").click().run()
    assert not at.exception
    text = " ".join(i.value for i in at.error) + " ".join(i.value for i in at.info)
    assert "FAULT DIAGNOSIS" in text
    assert "RUL evaluation unavailable" in text


def test_experiment_lab_synthetic_is_clearly_labelled_and_offers_download():
    at = _open("Experiment Lab (CWRU / Paderborn / Synthetic)")
    at.selectbox[0].select("Synthetic Bearing (simulated)").run()
    assert not at.exception
    warning_text = " ".join(i.value for i in at.warning)
    assert "SYNTHETIC" in warning_text
    assert "NOT REAL-WORLD VALIDATION" in warning_text
    at.button(key="lab_synth_generate").click().run()
    assert not at.exception
    assert at.download_button


def _femto_bundle_script():
    import streamlit as st

    from bearing_pdm.dashboard import _render_femto_bundle

    _render_femto_bundle({
        "bearing_run_id": "femto:Bearing2_1",
        "acquisition_count": 3,
        "sample_rate_hz": 25600.0,
        "sequence_index": [0, 1, 2],
        "representative_signals": {"early": {"vibration_x": [0.1, 0.2, 0.1]}},
        "representative_fft": {"early": {"vibration_x": {"frequency_hz": [0, 1, 2], "magnitude": [0.1, 0.2, 0.3]}}},
        "reference_hi": [1.0, 0.8, 0.4],
        "transparent_hi": None,
        "pca_hi": None,
        "stage": ["HEALTHY", "DEGRADING", "CRITICAL"],
        "actual_rul_seconds": [20.0, 10.0, 0.0],
        "held_out_predicted_rul_seconds": [18.0, 9.0, 1.0],
        "held_out_mae_seconds": 120.0,
        "held_out_unavailable_reason": None,
        "warnings": [],
    })
    st.write("DONE_FEMTO_BUNDLE")


def test_render_femto_bundle_charts_not_a_raw_json_dump():
    at = AppTest.from_function(_femto_bundle_script)
    at.run()
    assert not at.exception, f"_render_femto_bundle raised: {at.exception}"
    assert not at.json, "FEMTO bundle must render charts/metrics, not st.json(payload)"
    assert at.metric  # Bearing / Acquisitions / Sample rate
    texts = " ".join(md.value for md in at.markdown)
    assert "Health Indicator" in texts
    assert "CRITICAL" in " ".join(c.value for c in at.caption)


def _college_bundle_script():
    import streamlit as st

    from bearing_pdm.dashboard import _render_college_bundle

    _render_college_bundle({
        "dataset_id": "college",
        "n_acquisitions": 2,
        "temp_available_fraction": 1.0,
        "coverage_note": "Full coverage: all 129 raw LogFile_*.csv files are represented.",
        "sequence_index": [0, 1],
        "feature_trends": {"vibration_x_rms": [0.1, 0.2], "bearing_temp_mean": [30.0, 31.0]},
        "actual_rul_seconds": [10.0, 0.0],
        "held_out_predicted_rul_seconds": {"sequence_index": [0, 1], "predicted_rul_seconds": [9.0, 1.0]},
        "naive_caveat": "College naive MAE is an algebraic oracle identity, not a real baseline.",
        "domain_shift_note": "FEMTO-fit models are not applied to college data here (D11).",
    })
    st.write("DONE_COLLEGE_BUNDLE")


def test_render_college_bundle_shows_caveats_not_a_raw_json_dump():
    at = AppTest.from_function(_college_bundle_script)
    at.run()
    assert not at.exception, f"_render_college_bundle raised: {at.exception}"
    assert not at.json, "college bundle must render charts/metrics, not st.json(payload)"
    assert "algebraic oracle identity" in " ".join(w.value for w in at.warning)
    assert "D11" in " ".join(c.value for c in at.caption)


def _open(view: str) -> AppTest:
    """Select a view from the sidebar. Views are a radio rather than st.tabs so
    that the bearing/window controls can be hidden for the two views they do not
    affect - Streamlit cannot tell which st.tabs tab is in front."""
    at = AppTest.from_file(str(DASHBOARD_PATH), default_timeout=120)
    at.run()
    assert not at.exception, f"Dashboard raised: {at.exception}"
    at.sidebar.radio[0].set_value(view).run()
    assert not at.exception, f"Dashboard raised on view {view!r}: {at.exception}"
    return at


def test_cross_bearing_views_hide_the_bearing_and_window_controls():
    """Model Evaluation is global and Architecture is static. Showing a bearing
    selector that changes nothing on those views would be misleading."""
    for view in ["Model Evaluation", "Architecture & Limitations"]:
        at = _open(view)
        assert not at.sidebar.selectbox, f"{view} should not render data selectors"
        assert not at.sidebar.slider, f"{view} should not render the window slider"

    at = _open("Signal & FFT")
    assert at.sidebar.selectbox, "data views must still render their controls"
    assert at.sidebar.slider


def _run_on_femto(view: str) -> AppTest:
    """The dataset selectbox defaults to the alphabetically first dataset
    (college), whose HI and RUL tabs are deliberately gated (docs/decisions.md
    D11). Switch to FEMTO, which is what those tabs are about."""
    at = _open(view)
    at.sidebar.selectbox[0].select("femto").run()
    assert not at.exception, f"Dashboard raised after selecting femto: {at.exception}"
    return at


def test_dashboard_shows_health_indicator_and_stage_badge():
    """The HI tab must render a health indicator and a degradation stage for
    FEMTO, and must label the stage as a severity band rather than a fault
    type (.claude/rules/ml-data.md)."""
    from bearing_pdm.stages import STAGE_ORDER

    at = _run_on_femto("Health Indicator")

    labels = [m.label for m in at.metric]
    assert "Current health indicator" in labels

    rendered = " ".join(
        [e.value for e in at.success] + [e.value for e in at.warning]
        + [e.value for e in at.error] + [e.value for e in at.caption]
    )
    assert any(f"Degradation stage: **{stage}**" in rendered for stage in STAGE_ORDER)
    assert "not a fault diagnosis" in rendered


def test_dashboard_gates_college_instead_of_showing_a_wrong_number():
    """docs/decisions.md D11: FEMTO-fit models must not be applied to college's
    feature scale. Showing an explanatory message is the correct behaviour."""
    at = _open("Health Indicator")
    assert at.sidebar.selectbox[0].value == "college"
    assert "Current health indicator" not in [m.label for m in at.metric]
    assert any("fit only on FEMTO learning" in e.value for e in at.info)


def test_dashboard_shows_rul_in_hours_with_units():
    at = _run_on_femto("RUL Prediction")

    rul_metrics = [m for m in at.metric if "prediction" in m.label]
    assert rul_metrics, "no RUL prediction metric rendered"
    assert all(m.value.endswith(" h") for m in rul_metrics), (
        f"RUL must state its units in hours, got {[m.value for m in rul_metrics]}"
    )


def test_model_evaluation_tab_renders_real_metrics_not_a_missing_file_notice():
    """The Model Evaluation view used to dead-end on 'rul_evaluation.json not
    found' because that file is a gitignored generated artifact. It must now
    show the real leave-one-bearing-out numbers, including the over-estimate
    rate - MAE alone does not say whether the model is unsafe."""
    at = _open("Model Evaluation")

    labels = [m.label for m in at.metric]
    assert "ExtraTrees MAE (FEMTO)" in labels
    assert "Naive baseline MAE (FEMTO)" in labels, "the baseline comparison must stay on screen"
    # Three different MAEs share this page (FEMTO, hidden set, college). Labels
    # must stay distinct or a reader cannot tell 1.55 h from 34.01 h.
    mae_labels = [lab for lab in labels if "MAE" in lab]
    assert len(mae_labels) == len(set(mae_labels)), f"duplicate MAE labels: {mae_labels}"
    assert any("over-estimate rate" in lab for lab in labels)

    rendered = " ".join(w.value for w in at.warning) + " ".join(i.value for i in at.info)
    assert "unsafe direction" in rendered, "over-prediction must be flagged as the unsafe direction"
    assert "not found - run the corresponding script" not in rendered


def test_model_evaluation_tab_keeps_the_college_naive_oracle_caveat():
    """docs/decisions.md D10: college naive MAE=0.0 is an oracle, not a result.
    The dashboard must never show that number without the reason beside it."""
    at = _open("Model Evaluation")
    rendered = " ".join([i.value for i in at.info] + [e.value for e in at.error])
    assert "oracle" in rendered


def test_cross_dataset_pages_render_without_exception():
    """Both pages degrade to an explanatory message when their artifacts are
    missing and render real tables when present - never a traceback."""
    for view in ["Universal Machine Analysis", "Cross-Dataset Validation"]:
        at = _open(view)
        assert not at.exception


def test_status_banner_names_suppression_explicitly():
    from bearing_pdm.dashboard_cross import status_banner
    level, title, body = status_banner({"status": "RUL_SUPPRESSED", "model": None, "level": "LOW"})
    assert level == "error" and "LOW MODEL APPLICABILITY" in title
    assert "Unavailable: validated RUL prediction" in body
    assert status_banner({"status": "RUL_AVAILABLE", "model": "raw_seconds",
                          "level": "HIGH"})[0] == "success"
    assert status_banner({"status": "RUL_EXPERIMENTAL", "model": "m",
                          "level": "MEDIUM"})[0] == "warning"


def test_profile_box_refuses_paths_outside_known_roots(tmp_path):
    from bearing_pdm.dashboard_cross import is_within
    assert is_within(tmp_path / "a" / "b", [tmp_path])
    assert not is_within(tmp_path.parent / "elsewhere", [tmp_path])
    assert not is_within(tmp_path / ".." / "..", [tmp_path])
