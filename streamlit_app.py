"""Streamlit Community Cloud entrypoint.

Community Cloud runs this file from a fresh clone of the repository root, where
`bearing_pdm` is not installed and PYTHONPATH is not set. Putting `src/` on
sys.path here - and only here - keeps the package layout and the local
`PYTHONPATH=src` workflow exactly as they are.

The dashboard itself is unchanged: with no `config/data_paths.toml` present it
falls back to the tracked `deploy_data/` snapshot (see dashboard._cloud_mode).

Local equivalent: `PYTHONPATH=src python scripts/run_dashboard.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from bearing_pdm.dashboard import main  # noqa: E402  (must follow the sys.path setup)

main()
