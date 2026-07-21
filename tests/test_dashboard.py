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
