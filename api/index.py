"""Vercel Python Function entrypoint. Re-exports the FastAPI app defined in
src/bearing_pdm/api.py so Vercel's Python runtime can serve it directly -
no logic lives here, so there is nothing to duplicate or drift from the
tested app.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bearing_pdm.api import vercel_app as app  # noqa: E402,F401

__all__ = ["app"]
