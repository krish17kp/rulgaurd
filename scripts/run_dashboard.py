#!/usr/bin/env python
"""Launch the Streamlit review dashboard.

Usage:
    python scripts/run_dashboard.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    dashboard_path = Path(__file__).parent.parent / "src" / "bearing_pdm" / "dashboard.py"
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(dashboard_path), *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
