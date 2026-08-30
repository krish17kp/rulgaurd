"""Streamlit startup smoke test (command.md section 19: "Streamlit
import/startup where feasible"). Uses Streamlit's built-in AppTest
framework - runs the real script headlessly, no browser needed. Streamlit
renders every st.tabs() body in a single script run (tabs are a CSS-level
show/hide, not lazy-loaded), so one .run() call exercises all five tabs.

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


def test_dashboard_shows_all_five_tabs():
    at = AppTest.from_file(str(DASHBOARD_PATH), default_timeout=120)
    at.run()
    assert len(at.tabs) == 5


def _run_on_femto() -> AppTest:
    """The dataset selectbox defaults to the alphabetically first dataset
    (college), whose HI and RUL tabs are deliberately gated (docs/decisions.md
    D11). Switch to FEMTO, which is what those tabs are about."""
    at = AppTest.from_file(str(DASHBOARD_PATH), default_timeout=120)
    at.run()
    assert not at.exception, f"Dashboard raised: {at.exception}"
    at.sidebar.selectbox[0].select("femto").run()
    assert not at.exception, f"Dashboard raised after selecting femto: {at.exception}"
    return at


def test_dashboard_shows_health_indicator_and_stage_badge():
    """The HI tab must render a health indicator and a degradation stage for
    FEMTO, and must label the stage as a severity band rather than a fault
    type (.claude/rules/ml-data.md)."""
    from bearing_pdm.stages import STAGE_ORDER

    at = _run_on_femto()

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
    at = AppTest.from_file(str(DASHBOARD_PATH), default_timeout=120)
    at.run()
    assert at.sidebar.selectbox[0].value == "college"
    assert "Current health indicator" not in [m.label for m in at.metric]
    assert any("fit only on FEMTO learning" in e.value for e in at.info)


def test_dashboard_shows_rul_in_hours_with_units():
    at = _run_on_femto()

    rul_metrics = [m for m in at.metric if "prediction" in m.label]
    assert rul_metrics, "no RUL prediction metric rendered"
    assert all(m.value.endswith(" h") for m in rul_metrics), (
        f"RUL must state its units in hours, got {[m.value for m in rul_metrics]}"
    )
