"""Vercel Python Function entrypoint. Re-exports the FastAPI app defined in
src/bearing_pdm/api.py so Vercel's Python runtime can serve it directly -
no logic lives here, so there is nothing to duplicate or drift from the
tested app.

bearing_pdm is imported from ./bearing_pdm, not ../../src/bearing_pdm: that
directory is a fresh copy made by frontend/package.json's "prebuild" script
on every build (never hand-edited, never committed - see frontend/
.gitignore). includeFiles with a "../" traversal outside this function's
rootDirectory-scoped bundle, and a local-path pip/uv install of the real
src/ package, both hit unresolved platform errors on this account/CLI
version; vendoring a plain sibling copy at build time sidesteps both.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bearing_pdm.api import vercel_app as app  # noqa: E402,F401

__all__ = ["app"]
