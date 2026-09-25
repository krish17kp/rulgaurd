#!/usr/bin/env python
"""Figures for the college audit and the cross-dataset evaluation.

Presentation only: reads the cached outputs of build_canonical_features.py,
audit_dataset.py and run_cross_dataset.py, plus short raw snippets (read, never
reconstructed) for the waveform/FFT panels. Writes PNGs to reports/figures/.

Colours: one fixed categorical slot per dataset (never re-cycled), a single-hue
light->dark ramp for early/mid/late life.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.signal import welch  # noqa: E402

from bearing_pdm.adapters import get_adapter  # noqa: E402
from bearing_pdm.config import load_data_paths  # noqa: E402

DATASET_COLOR = {"femto": "#2a78d6", "college": "#eb6834", "ims": "#1baf7a", "xjtu": "#eda100"}
DATASET_LABEL = {"femto": "FEMTO", "college": "College", "ims": "IMS", "xjtu": "XJTU-SY"}
LIFE_RAMP = {"early": "#86b6ef", "mid": "#2a78d6", "late": "#104281"}
STAGE_COLOR = {"HEALTHY": "#008300", "DEGRADING": "#eda100", "CRITICAL": "#e34948"}
FIG = Path("reports/figures")
METRICS = Path("reports/metrics")
UNIT = "amplitude (as recorded; unit not stated by the rig)"

plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.25,
                     "axes.spines.top": False, "axes.spines.right": False, "font.size": 9})


def _save(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=130)
    plt.close(fig)
    print("wrote", FIG / name)


def _hours(s):
    return np.asarray(s, dtype=float) / 3600.0


# ---------------------------------------------------------------------------
# College
# ---------------------------------------------------------------------------

def college_figures(college_root: Path) -> None:
    c = pd.read_parquet("data/processed/canonical_college.parquet").sort_values("sequence_index")
    h = _hours(c["elapsed_s"])
    adapter = get_adapter("college")
    run = adapter.discover(college_root)[0]
    n = len(c)
    picks = {"early": 2, "mid": n // 2, "late": n - 1}
    recs = {}
    for rec in adapter.recordings(run):
        for stage, idx in picks.items():
            if rec.sequence_index == idx:
                recs[stage] = rec
        if len(recs) == 3:
            break
    fs = run.sampling_rate_hz

    fig, axes = plt.subplots(3, 2, figsize=(10, 6.5), sharex=True, sharey=True)
    for i, (stage, rec) in enumerate(recs.items()):
        t = np.arange(int(0.2 * fs)) / fs
        for j, ch in enumerate(("vibration_x", "vibration_y")):
            ax = axes[i, j]
            ax.plot(t * 1000, rec.signals[ch][: len(t)], lw=0.6, color=LIFE_RAMP[stage])
            ax.set_title(f"{stage} life - {ch} - {rec.recording_id} "
                         f"(t = {rec.elapsed_s / 3600:.0f} h)", fontsize=8)
    for ax in axes[-1]:
        ax.set_xlabel("time within recording (ms), first 0.2 s of 78.1 s")
    fig.supylabel(UNIT, fontsize=9)
    fig.suptitle("College bearing: measured raw vibration, early / mid / late life")
    _save(fig, "college_raw_vibration.png")

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for ch, lw in (("vibration_x", 1.4), ("vibration_y", 1.0)):
        for stage, rec in recs.items():
            x = rec.signals[ch][: int(10 * fs)]
            f, p = welch(np.nan_to_num(x), fs=fs, nperseg=8192)
            ax = axes[0 if ch == "vibration_x" else 1]
            ax.semilogy(f / 1000, p, lw=lw * 0.7, color=LIFE_RAMP[stage],
                        label=f"{stage} ({rec.elapsed_s / 3600:.0f} h)")
            ax.set_title(f"{ch}: Welch PSD, first 10 s of the recording")
            ax.set_xlabel("frequency (kHz)")
            ax.set_ylabel("PSD (amplitude$^2$/Hz)")
    axes[0].legend()
    fig.suptitle("College bearing: spectrum early / mid / late life")
    _save(fig, "college_fft.png")

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    ax = axes[0]
    ax.plot(h, c["bearing_temp_mean"], color="#e34948", label="bearing")
    ax.plot(h, c["ambient_temp_mean"], color="#4a3aa7", label="ambient (atmospheric)")
    ax.plot(h, c["bearing_minus_ambient_temp_mean"], color="#2a78d6", label="bearing - ambient")
    ax.axhline(85, color="#898781", ls="--", lw=1)
    ax.text(1, 86, "85 °C stop criterion (description)", fontsize=7, color="#555")
    ax.set_xlabel("elapsed time (h)")
    ax.set_ylabel("temperature, per-file mean (°C)")
    ax.set_title("Temperature over life")
    ax.legend(fontsize=7)
    ax = axes[1]
    slope = np.gradient(c["bearing_temp_mean"].to_numpy(), c["elapsed_s"].to_numpy() / 3600)
    ax.plot(h, slope, color="#e34948", lw=1)
    ax.axhline(0, color="#898781", lw=0.8)
    ax.set_xlabel("elapsed time (h)")
    ax.set_ylabel("d(bearing temp)/dt (°C/h)")
    ax.set_title("Bearing temperature trend (between hourly files)")
    _save(fig, "college_temperature.png")

    feats = ["rms", "std", "var", "max", "peak_to_peak", "skewness", "kurtosis", "crest_factor",
             "shape_factor", "impulse_factor", "clearance_factor", "abs_mean"]
    fig, axes = plt.subplots(3, 4, figsize=(12, 7.5), sharex=True)
    for ax, feat in zip(axes.flat, feats):
        for ch, color in (("vibration_x", "#2a78d6"), ("vibration_y", "#eb6834")):
            ax.plot(h, c[f"{ch}_{feat}"], lw=1, color=color, label=ch)
        ax.set_title(feat.replace("_", " "))
    for ax in axes[-1]:
        ax.set_xlabel("elapsed time (h)")
    axes[0, 0].legend(fontsize=7)
    fig.suptitle("College bearing: time-domain features per hourly recording "
                 "(median over 0.1 s windows; amplitude features in recorded units)")
    _save(fig, "college_feature_trends.png")

    spec = [("dominant_frequency_hz", "dominant frequency (Hz)"),
            ("spectral_centroid_hz", "spectral centroid (Hz)"),
            ("total_spectral_energy", "spectral energy per 0.1 s window"),
            ("spectral_entropy", "spectral entropy (bits)"),
            ("band_energy_frac_low", "energy fraction 0-1 kHz"),
            ("band_energy_frac_high", "energy fraction 5-12.8 kHz")]
    fig, axes = plt.subplots(2, 3, figsize=(12, 5.5), sharex=True)
    for ax, (feat, label) in zip(axes.flat, spec):
        for ch, color in (("vibration_x", "#2a78d6"), ("vibration_y", "#eb6834")):
            ax.plot(h, c[f"{ch}_{feat}"], lw=1, color=color, label=ch)
        ax.set_title(label)
        if feat == "total_spectral_energy":
            ax.set_yscale("log")
    for ax in axes[-1]:
        ax.set_xlabel("elapsed time (h)")
    axes[0, 0].legend(fontsize=7)
    fig.suptitle("College bearing: frequency-domain features over life")
    _save(fig, "college_spectral_trends.png")


# ---------------------------------------------------------------------------
# Cross-dataset
# ---------------------------------------------------------------------------

def _stage_bands(ax, x, stages):
    stages = np.asarray(stages)
    start = 0
    for i in range(1, len(stages) + 1):
        if i == len(stages) or stages[i] != stages[start]:
            if stages[start] in STAGE_COLOR:
                ax.axvspan(x[start], x[min(i, len(x) - 1)], color=STAGE_COLOR[stages[start]],
                           alpha=0.12, lw=0)
            start = i


def degradation_figure(health: pd.DataFrame, pred: pd.DataFrame) -> None:
    g = health[health["dataset_id"] == "college"].sort_values("sequence_index")
    lf = g["life_fraction"].to_numpy()
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    ax = axes[0]
    _stage_bands(ax, lf, g["amplitude_stage"])
    ax.plot(lf, g["amplitude_hi"], color="#2a78d6", label="amplitude SN HI (drives stage)")
    ax.plot(lf, g["sn_hi"], color="#eb6834", lw=1, label="fused SN HI (14 features)")
    ax.plot(lf, g["reference_hi"], color="#898781", lw=1, label="reference HI (absolute features)")
    ax.set_xlabel("normalised life (elapsed / total)")
    ax.set_ylabel("health indicator (1 healthy -> 0 failed)")
    ax.set_title("College: HI and stage\n(bands: green healthy, yellow degrading, red critical)")
    ax.legend(fontsize=7)
    ax = axes[1]
    p = pred[(pred["bearing_run_id"] == "college:nsk6205")]
    base = p.drop_duplicates("sequence_index").sort_values("sequence_index")
    ax.plot(_hours(base["elapsed_s"]), _hours(base["actual_rul_seconds"]), color="#0b0b0b",
            lw=1.6, label="actual RUL")
    for (exp, model), q in p.groupby(["experiment", "model"]):
        if not exp.startswith("ZS"):
            continue
        q = q.sort_values("sequence_index")
        color = "#2a78d6" if model == "raw_seconds" else "#eb6834"
        ax.plot(_hours(q["elapsed_s"]), _hours(q["predicted_rul_seconds"]), color=color,
                label=f"zero-shot FEMTO {model}")
    ax.set_yscale("symlog", linthresh=1)
    ax.set_xlabel("elapsed time (h)")
    ax.set_ylabel("RUL (h, symlog)")
    ax.set_title("College: zero-shot RUL\n(wrong in both directions -> suppressed by routing)")
    ax.legend(fontsize=7)
    _save(fig, "college_degradation_rul.png")


def feature_distributions(df: pd.DataFrame) -> None:
    feats = [("vibration_x_rms", "RMS, x (recorded units)", True),
             ("vibration_x_kurtosis", "excess kurtosis, x", False),
             ("vibration_x_crest_factor", "crest factor, x", False),
             ("vibration_x_total_spectral_energy", "spectral energy per 0.1 s, x", True),
             ("vibration_x_dominant_frequency_hz", "dominant frequency, x (Hz)", False),
             ("vibration_x_spectral_centroid_hz", "spectral centroid, x (Hz)", False),
             ("sn_rms", "SN log-RMS change vs own reference", False),
             ("sn_kurtosis", "SN log-kurtosis change vs own reference", False)]
    datasets = [d for d in DATASET_COLOR if d in set(df["dataset_id"])]
    fig, axes = plt.subplots(2, 4, figsize=(13, 6))
    for ax, (feat, label, log) in zip(axes.flat, feats):
        data = [df.loc[df["dataset_id"] == d, feat].dropna() for d in datasets]
        bp = ax.boxplot(data, showfliers=False, patch_artist=True, widths=0.6)
        for patch, d in zip(bp["boxes"], datasets):
            patch.set_facecolor(DATASET_COLOR[d])
            patch.set_alpha(0.75)
        ax.set_xticks(range(1, len(datasets) + 1), [DATASET_LABEL[d] for d in datasets])
        ax.set_title(label, fontsize=8)
        if log:
            ax.set_yscale("log")
    fig.suptitle("Feature distributions by dataset (run-to-failure bearings, all recordings; "
                 "whiskers 1.5 IQR). Absolute features shift; self-normalised (SN) ones overlap.")
    _save(fig, "feature_distributions_by_dataset.png")


def hi_across_datasets(health: pd.DataFrame) -> None:
    datasets = [d for d in DATASET_COLOR if d in set(health["dataset_id"])]
    fig, axes = plt.subplots(1, len(datasets), figsize=(3.3 * len(datasets), 3.4), sharey=True)
    for ax, d in zip(np.atleast_1d(axes), datasets):
        g = health[(health["dataset_id"] == d) & health["rul_seconds"].notna()]
        for _, b in g.groupby("bearing_run_id"):
            b = b.sort_values("sequence_index")
            ax.plot(b["life_fraction"], b["amplitude_hi"], lw=0.7, alpha=0.55, color=DATASET_COLOR[d])
        bins = pd.cut(g["life_fraction"], np.linspace(0, 1, 21))
        med = g.groupby(bins, observed=True)["amplitude_hi"].median()
        ax.plot([i.mid for i in med.index], med.to_numpy(), color="#0b0b0b", lw=2,
                label="median over bearings")
        ax.set_title(f"{DATASET_LABEL[d]} ({g['bearing_run_id'].nunique()} bearings)")
        ax.set_xlabel("normalised life")
    np.atleast_1d(axes)[0].set_ylabel("amplitude SN health indicator")
    np.atleast_1d(axes)[0].legend(fontsize=7)
    fig.suptitle("One FEMTO-fit health indicator (amplitude SN) applied to every dataset")
    _save(fig, "hi_across_datasets.png")


def rul_examples(pred: pd.DataFrame) -> None:
    wanted = [("A: FEMTO -> FEMTO (LOBO)", "raw_seconds", "femto:Bearing2_1"),
              ("ZS: FEMTO -> college", "raw_seconds", "college:nsk6205"),
              ("ZS: FEMTO -> xjtu", "raw_seconds", "xjtu:Bearing2_1"),
              ("ZS: FEMTO -> xjtu", "sn_fraction", "xjtu:Bearing2_1"),
              ("WD: xjtu -> xjtu (LOBO)", "sn_fraction", "xjtu:Bearing2_1"),
              ("MD: all datasets (LOBO)", "sn_fraction", "ims:test2_bearing1")]
    wanted = [w for w in wanted if ((pred["experiment"] == w[0]) & (pred["model"] == w[1])
                                    & (pred["bearing_run_id"] == w[2])).any()]
    fig, axes = plt.subplots(2, 3, figsize=(13, 6.5))
    for ax, (exp, model, bearing) in zip(axes.flat, wanted):
        q = pred[(pred["experiment"] == exp) & (pred["model"] == model)
                 & (pred["bearing_run_id"] == bearing)].sort_values("sequence_index")
        x = _hours(q["elapsed_s"])
        ax.fill_between(x, _hours(q["rul_lo_abs"]), _hours(q["rul_hi_abs"]), color="#86b6ef",
                        alpha=0.35, lw=0, label="90% conformal interval")
        ax.plot(x, _hours(q["actual_rul_seconds"]), color="#0b0b0b", lw=1.6, label="actual")
        ax.plot(x, _hours(q["predicted_rul_seconds"]), color="#2a78d6", lw=1, label="predicted")
        ax.set_ylim(0, max(1e-3, 1.6 * _hours(q["actual_rul_seconds"]).max()))
        ax.set_title(f"{exp}\n{model} | {bearing}", fontsize=8)
        ax.set_xlabel("elapsed time (h)")
        ax.set_ylabel("RUL (h)")
    for ax in axes.flat[len(wanted):]:
        ax.axis("off")
    axes.flat[0].legend(fontsize=7)
    fig.suptitle("Actual vs predicted RUL (held-out bearings only; y-axis clipped at 1.6x the "
                 "true maximum)")
    _save(fig, "rul_actual_vs_predicted.png")


def error_by_bearing(per_bearing: pd.DataFrame) -> None:
    pb = per_bearing.copy()
    pb["label"] = pb["experiment"] + " | " + pb["model"]
    order = pb.groupby("label")["fraction_mae"].median().sort_values().index
    fig, ax = plt.subplots(figsize=(10, 0.32 * len(order) + 1.5))
    for i, label in enumerate(order):
        g = pb[pb["label"] == label]
        for d, gd in g.groupby(g["bearing_run_id"].str.split(":").str[0]):
            ax.scatter(gd["fraction_mae"], np.full(len(gd), i), s=18, color=DATASET_COLOR[d],
                       edgecolor="white", lw=0.5, zorder=3)
        ax.plot(g["fraction_mae"].median(), i, "|", color="#0b0b0b", ms=12, mew=2, zorder=4)
    ax.set_yticks(range(len(order)), order, fontsize=7)
    ax.axvline(0.25, color="#898781", ls="--", lw=1)
    ax.text(0.255, -0.8, "constant f=0.5 guess ~0.25", fontsize=7, color="#555")
    ax.set_xlabel("life-fraction MAE per held-out bearing (0 = perfect); | = median")
    handles = [plt.Line2D([], [], marker="o", ls="", color=c, label=DATASET_LABEL[d])
               for d, c in DATASET_COLOR.items() if d in set(pb["bearing_run_id"].str.split(":").str[0])]
    ax.legend(handles=handles, title="test bearing from", fontsize=7, loc="lower right")
    ax.set_title("RUL error per held-out bearing, every experiment")
    _save(fig, "rul_error_by_bearing.png")


def applicability_vs_error(per_bearing: pd.DataFrame, app: pd.DataFrame, summary: dict) -> None:
    m = per_bearing.merge(app[["experiment", "model", "bearing_run_id", "level", "shift_ratio"]],
                          on=["experiment", "model", "bearing_run_id"])
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, model in zip(axes, ("raw_seconds", "sn_fraction")):
        g = m[m["model"] == model]
        for d, gd in g.groupby(g["bearing_run_id"].str.split(":").str[0]):
            ax.scatter(gd["shift_ratio"], gd["fraction_mae"], s=22, color=DATASET_COLOR[d],
                       edgecolor="white", lw=0.5, label=DATASET_LABEL[d], zorder=3)
        for x in (1.0, 2.0):
            ax.axvline(x, color="#898781", ls="--", lw=1)
        rho = summary.get(model, {}).get("spearman_shift_vs_fraction_mae", float("nan"))
        ax.set_title(f"{model}: Spearman rho = {rho:.2f} (n = {len(g)})")
        ax.set_xscale("log")
        ax.set_yscale("log")
        for axis in (ax.xaxis, ax.yaxis):
            axis.set_major_locator(matplotlib.ticker.LogLocator(subs=(1, 2, 5)))
            axis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%g"))
            axis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.set_xlabel("distribution shift ratio (1 = in-domain limit, 2 = LOW)")
    axes[0].set_ylabel("life-fraction MAE (constant 0.5 guess ~ 0.25)")
    axes[0].legend(fontsize=7, title="test bearing")
    fig.suptitle("Does larger distribution shift go with larger RUL error?")
    _save(fig, "applicability_vs_error.png")


def coverage(summary: pd.DataFrame) -> None:
    s = summary.copy()
    s["label"] = s["experiment"] + " | " + s["model"] + " | " + s["test_domain"]
    s = s.sort_values("label")
    methods = [("coverage_tree_5_95", "tree 5-95% spread (uncalibrated)", "#86b6ef"),
               ("coverage_conformal", "normalised conformal", "#2a78d6"),
               ("coverage_conformal_abs", "absolute conformal", "#104281")]
    y = np.arange(len(s))
    fig, ax = plt.subplots(figsize=(10, 0.35 * len(s) + 1.5))
    for k, (col, label, color) in enumerate(methods):
        ax.barh(y + (k - 1) * 0.26, s[col], height=0.24, color=color, label=label)
    ax.axvline(0.9, color="#e34948", ls="--", lw=1.2)
    ax.text(0.905, len(s) - 0.5, "nominal 90%", fontsize=7, color="#e34948")
    ax.set_yticks(y, s["label"], fontsize=7)
    ax.set_xlim(0, 1.02)
    ax.set_xlabel("empirical coverage of the true RUL (mean over held-out bearings)")
    ax.legend(fontsize=7, loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=3, frameon=False)
    ax.set_title("Prediction-interval coverage by experiment", pad=24)
    _save(fig, "interval_coverage.png")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/data_paths.toml")
    parser.add_argument("--skip-raw", action="store_true", help="skip figures that re-read raw files")
    args = parser.parse_args()
    FIG.mkdir(parents=True, exist_ok=True)

    report = json.loads((METRICS / "cross_dataset.json").read_text())
    pred = pd.read_parquet(METRICS / "cross_dataset_predictions.parquet")
    app = pd.read_parquet(METRICS / "cross_dataset_applicability.parquet")
    health = pd.read_parquet(METRICS / "cross_dataset_health.parquet")
    per_bearing = pd.DataFrame(report["per_bearing"])

    if not args.skip_raw:
        college_figures(load_data_paths(args.config).college_raw_dir)
    degradation_figure(health, pred)

    from bearing_pdm import experiments as E
    frames = [pd.read_parquet(p) for p in sorted(Path("data/processed").glob("canonical_*.parquet"))]
    df = E.run_to_failure(E.prepare(frames))
    feature_distributions(df)
    hi_across_datasets(health)
    rul_examples(pred)
    error_by_bearing(per_bearing)
    applicability_vs_error(per_bearing, app, report["applicability_vs_error"])
    coverage(pd.DataFrame(report["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
