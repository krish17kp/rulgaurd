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
    ]


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
