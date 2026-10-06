"""Regression: root .vercelignore must not shadow frontend/reports/.

The deploy prebuild step vendors reports/metrics/rul_evaluation.json into
frontend/reports/ so /models/evaluation works without a Preview-only env var
(see docs/decisions.md). A bare `reports/` line in .vercelignore matches that
path too (gitignore-style), silently stripping the file the deploy build
step needs. Anchoring with a leading slash keeps it scoped to the repo root.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_vercelignore_reports_rule_is_root_anchored() -> None:
    lines = (REPO_ROOT / ".vercelignore").read_text().splitlines()
    bare_reports = [line for line in lines if line.strip() == "reports/"]
    assert not bare_reports, (
        "`.vercelignore` has an unanchored `reports/` rule, which also matches "
        "frontend/reports/ and breaks the deploy prebuild's metrics vendoring. "
        "Use `/reports/` to anchor it to the repo root."
    )
