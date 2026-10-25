#!/usr/bin/env python
"""Render the RUL result figures the paper needs, from the metrics JSONs only.

Reads `reports/metrics/{rul_evaluation,hidden_set_evaluation}.json` and writes
PNGs to `reports/figures/`. It never fits a model, never touches a dataset, and
never recomputes a metric - every number drawn here was written by
`evaluate_models.py` or `score_hidden_set.py` (.claude/rules/general.md: never
write a number you did not read out of a generated artifact).

The predicted-vs-actual figure shades the two half-planes deliberately. The
hidden-set finding is directional, not just magnitude: ExtraTrees over-estimates
remaining life on 8 of 11 bearings against the naive baseline's 4, and an
over-estimate is a late warning - the unsafe direction for maintenance planning,
which is also why the official PHM2012 score penalises it with denominator 5
rather than 20 (docs/decisions.md D16/D20, evaluation.phm2012_score).

Usage:
    python scripts/plot_results.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

METRICS_DIR = Path("reports/metrics")
FIGURES_DIR = Path("reports/figures")

# Consistent across every figure so the two models are never confused.
MODEL_STYLE = {
    "extra_trees": {"label": "ExtraTrees", "color": "#1f77b4"},
    "naive": {"label": "naive baseline", "color": "#999999"},
}
# Which hidden-set ground truth to plot. 'official' is the citable, literature
# comparable table; 'archive_derived' differs only on Bearing1_4 (D17).
DEFAULT_GROUND_TRUTH = "official"


def _load(name: str) -> dict:
    path = METRICS_DIR / name
    if not path.is_file():
        raise SystemExit(
            f"{path} not found - run scripts/evaluate_models.py and "
            "scripts/score_hidden_set.py first."
        )
    return json.loads(path.read_text())


def _short(bearing_run_id: str) -> str:
    """'femto:Bearing1_1' -> 'Bearing1_1' (axis labels, not data)."""
    return str(bearing_run_id).split(":", 1)[-1]


def _save(fig, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Wrote {out_path}")


def plot_lobo_mae(metrics: dict, out_path: Path) -> None:
    """Per-bearing leave-one-bearing-out MAE. Per-bearing rather than the mean,
    because the mean hides that ExtraTrees loses to naive on 2 of 6 bearings.

    The naive bars are a lifetime-spread identity, not a sensor-driven
    prediction (docs/decisions.md D22) - read the gap accordingly.
    """
    df = pd.DataFrame(metrics["femto_lobo"])
    bearings = sorted(df["held_out_bearing"].unique())
    x = np.arange(len(bearings))
    width = 0.38

    fig, ax = plt.subplots(figsize=(9, 5))
    for offset, model in ((-width / 2, "extra_trees"), (width / 2, "naive")):
        sub = df[df["model"] == model].set_index("held_out_bearing").loc[bearings]
        ax.bar(
            x + offset, sub["mae_seconds"], width,
            label=MODEL_STYLE[model]["label"], color=MODEL_STYLE[model]["color"],
        )

    means = metrics["femto_lobo_mean_mae_by_model"]
    for model, style in MODEL_STYLE.items():
        ax.axhline(means[model], color=style["color"], linestyle="--", linewidth=1)
        # Inside the axes: at the right edge tight_layout clips the label.
        ax.text(
            -0.42, means[model], f"mean {means[model]:,.0f}",
            va="bottom", ha="left", fontsize=8, color=style["color"],
            bbox={"facecolor": "white", "alpha": 0.75, "edgecolor": "none", "pad": 1},
        )

    ax.set_xticks(x, [_short(b) for b in bearings], rotation=20)
    ax.set_ylabel("MAE (seconds)")
    ax.set_xlabel("held-out bearing")
    ax.set_title("FEMTO leave-one-bearing-out RUL error (lower is better)")
    ax.legend()
    _save(fig, out_path)


def plot_hidden_set_scatter(scored: pd.DataFrame, out_path: Path, ground_truth: str) -> None:
    """Predicted vs actual RUL at the last censored acquisition, n=11 bearings.

    The shaded half-planes carry the finding: anything above y=x is a
    prediction of MORE remaining life than the bearing had - a late warning.
    """
    limit = float(max(scored["actual_rul_seconds"].max(), scored["predicted_rul_seconds"].max()))
    limit *= 1.08

    fig, ax = plt.subplots(figsize=(7.2, 6.6))
    ax.fill_between([0, limit], [0, limit], [limit, limit], color="#d62728", alpha=0.07)
    ax.fill_between([0, limit], [0, 0], [0, limit], color="#2ca02c", alpha=0.07)
    ax.plot([0, limit], [0, limit], color="black", linewidth=1, label="perfect prediction")

    # Boxed, and placed in the sparsest part of each half-plane: these sit on
    # top of the scatter, so an unboxed label becomes unreadable.
    box = {"facecolor": "white", "alpha": 0.8, "edgecolor": "none", "pad": 2.5}
    ax.text(limit * 0.30, limit * 0.96, "over-estimate\n(late warning - unsafe)",
            fontsize=9, color="#d62728", va="top", ha="center", bbox=box, zorder=4)
    ax.text(limit * 0.72, limit * 0.10, "under-estimate\n(early warning)",
            fontsize=9, color="#2ca02c", va="bottom", ha="center", bbox=box, zorder=4)

    for model, style in MODEL_STYLE.items():
        sub = scored[scored["model"] == model]
        if sub.empty:
            continue
        n_over = int((sub["error_seconds"] > 0).sum())
        ax.scatter(
            sub["actual_rul_seconds"], sub["predicted_rul_seconds"],
            s=64, color=style["color"], edgecolor="black", linewidth=0.5, zorder=3,
            label=f"{style['label']} ({n_over}/{len(sub)} over-estimate)",
        )

    for row in scored[scored["model"] == "extra_trees"].itertuples():
        ax.annotate(
            row.bearing, (row.actual_rul_seconds, row.predicted_rul_seconds),
            textcoords="offset points", xytext=(7, 3), fontsize=7, zorder=5,
            bbox={"facecolor": "white", "alpha": 0.7, "edgecolor": "none", "pad": 1},
        )

    ax.set_xlim(0, limit)
    ax.set_ylim(0, limit)
    ax.set_xlabel("actual RUL (seconds)")
    ax.set_ylabel("predicted RUL (seconds)")
    ax.set_title(
        "FEMTO hidden set: predicted vs actual RUL\n"
        f"n=11, one prediction per bearing ({ground_truth} ground truth)",
        fontsize=11,
    )
    ax.legend(loc="upper right", fontsize=8)
    _save(fig, out_path)


def plot_phm2012_scores(scored: pd.DataFrame, out_path: Path, ground_truth: str) -> None:
    """Per-bearing official challenge score A_i, in (0, 1], higher is better.

    Plotted per bearing because the aggregate is an arithmetic mean over a very
    skewed set: one bearing carries most of ExtraTrees' score while several
    score 0.000 outright.
    """
    bearings = sorted(scored["bearing"].unique())
    x = np.arange(len(bearings))
    width = 0.38

    fig, ax = plt.subplots(figsize=(9.5, 5))
    for offset, model in ((-width / 2, "extra_trees"), (width / 2, "naive")):
        sub = scored[scored["model"] == model].set_index("bearing").reindex(bearings)
        ax.bar(
            x + offset, sub["phm2012_score"], width,
            label=MODEL_STYLE[model]["label"], color=MODEL_STYLE[model]["color"],
        )
        ax.axhline(
            float(sub["phm2012_score"].mean()),
            color=MODEL_STYLE[model]["color"], linestyle="--", linewidth=1,
        )

    ax.set_xticks(x, bearings, rotation=25)
    ax.set_ylabel(r"PHM2012 score $A_i$  (higher is better)")
    ax.set_xlabel("hidden-set bearing")
    ax.set_title(
        "Official IEEE PHM 2012 score per bearing "
        f"({ground_truth} ground truth); dashed lines are the challenge aggregate"
    )
    ax.legend()
    _save(fig, out_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ground-truth", choices=["official", "archive_derived"],
        default=DEFAULT_GROUND_TRUTH,
        help="Hidden-set ground-truth variant; they differ only on Bearing1_4 (D17).",
    )
    parser.add_argument("--figures-dir", default=str(FIGURES_DIR))
    args = parser.parse_args()
    out_dir = Path(args.figures_dir)

    plot_lobo_mae(_load("rul_evaluation.json"), out_dir / "rul_lobo_mae_per_bearing.png")

    hidden = _load("hidden_set_evaluation.json")
    scored = pd.DataFrame(hidden["results"][args.ground_truth]["per_bearing"])
    plot_hidden_set_scatter(
        scored, out_dir / "rul_hidden_set_predicted_vs_actual.png", args.ground_truth
    )
    plot_phm2012_scores(
        scored, out_dir / "rul_hidden_set_phm2012_score.png", args.ground_truth
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
