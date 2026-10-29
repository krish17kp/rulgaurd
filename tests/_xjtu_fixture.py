"""Tiny synthetic XJTU-SY-shaped tree for dataset-job tests.

NOT real XJTU-SY data: same folder layout and CSV header as the real download
(xjtu.py), random vibration with growing amplitude, 4,096 samples per file
instead of 32,768 to keep tests fast.
"""

from pathlib import Path

import numpy as np


def make_xjtu_tree(root: Path, bearings=("Bearing1_1", "Bearing1_2"), n_files=14,
                   condition="35Hz12kN", wrap="XJTU-SY_Bearing_Datasets") -> Path:
    base = root / wrap if wrap else root
    rng = np.random.default_rng(0)
    for b in bearings:
        bdir = base / condition / b
        bdir.mkdir(parents=True, exist_ok=True)
        for i in range(1, n_files + 1):
            x = rng.normal(0, 0.5 + 0.2 * i, (4096, 2))
            lines = ["Horizontal_vibration_signals,Vertical_vibration_signals"]
            lines += [f"{a:.4f},{c:.4f}" for a, c in x]
            (bdir / f"{i}.csv").write_text("\n".join(lines) + "\n")
    (base / "Introduction.pdf").write_bytes(b"%PDF-1.4 not a real pdf")
    return base
