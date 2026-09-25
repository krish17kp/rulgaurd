"""Dashboard pages for the cross-dataset workflow (called from dashboard.py).

Same contract as the rest of the dashboard: cached artifacts only, never a
.fit(). Everything shown is produced offline by:

    scripts/build_canonical_features.py  canonical feature Parquets
    scripts/audit_dataset.py             reports/metrics/audit_<dataset>.json
    scripts/run_cross_dataset.py         reports/metrics/cross_dataset*.{json,parquet}
    scripts/analyze_dataset.py           reports/metrics/routing_<dataset>.{json,parquet}

Missing artifact -> an explanatory message naming the script, never a traceback.
The raw-signal panel re-reads the actual recording through its adapter; if the
source file is unreachable it says so instead of drawing anything.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

METRICS = Path("reports/metrics")
PROCESSED = Path("data/processed")

# Verified dataset facts (docs/external-datasets.md, one source per fact there).
DATASET_FACTS = pd.DataFrame([
    {"Dataset": "FEMTO / PRONOSTIA", "Institution": "FEMTO-ST (France)", "Bearings":
     "17 (6 learning + 11 censored test)", "Sampling rate": "25.6 kHz", "Record": "0.1 s every 10 s",
     "Sensors": "2 accel. (H,V) + temp.", "RPM": "1800 / 1650 / 1500", "Load": "4.0 / 4.2 / 5.0 kN",
     "Run-to-failure": "yes (20 g)", "RUL labels": "yes", "Use here": "training domain"},
    {"Dataset": "College rig", "Institution": "our college", "Bearings": "1 (NSK 6205)",
     "Sampling rate": "25.6 kHz", "Record": "78.1 s every ~1 h", "Sensors":
     "2 accel. + bearing & ambient temp.", "RPM": "1770-1780", "Load": "5.88 kN + 2.94 kN axial",
     "Run-to-failure": "yes (85 °C / 9 m/s²)", "RUL labels": "yes (1 run)",
     "Use here": "unseen-machine validation"},
    {"Dataset": "IMS (NASA)", "Institution": "Univ. of Cincinnati IMS", "Bearings":
     "3 runs x 4; 4 failed", "Sampling rate": "20 kHz", "Record": "1.02 s every 10 min",
     "Sensors": "2 (test 1) or 1 accel. per bearing", "RPM": "2000", "Load": "26.7 kN radial",
     "Run-to-failure": "yes (no stated criterion)", "RUL labels": "4 failed bearings",
     "Use here": "external validation"},
    {"Dataset": "XJTU-SY", "Institution": "Xi'an Jiaotong Univ.", "Bearings": "15 (LDK UER204)",
     "Sampling rate": "25.6 kHz", "Record": "1.28 s every 1 min", "Sensors": "2 accel. (H,V)",
     "RPM": "2100 / 2250 / 2400", "Load": "12 / 11 / 10 kN", "Run-to-failure": "yes (10 x A_h)",
     "RUL labels": "yes", "Use here": "external validation, multi-dataset training"},
    {"Dataset": "CWRU / Paderborn / MFPT", "Institution": "various", "Bearings": "seeded/real faults",
     "Sampling rate": "12-97.7 kHz", "Record": "short steady-state", "Sensors": "accel. (+ current)",
     "RPM": "-", "Load": "-", "Run-to-failure": "no", "RUL labels": "no",
     "Use here": "not used: fault classification only"},
])

STATUS_TEXT = {
    "RUL_AVAILABLE": ("success", "RUL available - validated model, HIGH applicability"),
    "RUL_EXPERIMENTAL": ("warning", "Experimental RUL - MEDIUM applicability, reduced reliability"),
    "RUL_SUPPRESSED": ("error", "LOW MODEL APPLICABILITY - reliable RUL prediction suppressed"),
}


def status_banner(decision: dict) -> tuple[str, str, str]:
    """(streamlit level, title, body) for a routing decision. Pure - tested."""
    level, title = STATUS_TEXT[decision["status"]]
    if decision["status"] == "RUL_SUPPRESSED":
        body = ("This machine differs significantly from the training population, or no model "
                "has validated skill for it. Available: signal analysis, health indicator, "
                "degradation stage, applicability reasons. Unavailable: validated RUL prediction.")
    else:
        body = f"Model: {decision['model']} (applicability {decision['level']})."
        if decision.get("validated_skill") is not None:
            body += (f" Held-out skill on this dataset: {decision['validated_skill']:+.2f} "
                     "(life-fraction MAE improvement over a constant guess; 0 = no skill, "
                     "1 = perfect).")
    return level, title, body


def is_within(path: Path, roots: list[Path]) -> bool:
    """Profiling is restricted to folders this project already knows about."""
    path = path.expanduser().resolve()
    return any(path == r or r in path.parents for r in roots)


def allowed_roots() -> list[Path]:
    roots = [Path.cwd().resolve()]
    for manifest in PROCESSED.glob("canonical_*.json"):
        src = json.loads(manifest.read_text()).get("source_root")
        if src:
            p = Path(src).resolve()
            roots.append(p if p.is_dir() else p.parent)
    return roots


@st.cache_data
def _json(path: str) -> dict | None:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


@st.cache_data
def _parquet(path: str) -> pd.DataFrame | None:
    p = Path(path)
    return pd.read_parquet(p) if p.exists() else None


def _missing(what: str, script: str) -> None:
    st.warning(f"{what} not found. Generate it with `python {script}`.")


# ---------------------------------------------------------------------------
# Universal Machine Analysis
# ---------------------------------------------------------------------------

def render_universal() -> None:
    st.subheader("Universal Machine Analysis")
    st.caption("Offline analysis of recorded data (not a live feed): profile -> quality -> "
               "adapter -> features -> applicability -> RUL or health-only.")
    available = sorted(p.stem.removeprefix("routing_") for p in METRICS.glob("routing_*.json"))
    if not available:
        _missing("Routing results", "scripts/analyze_dataset.py --root <dataset folder>")
        return
    c1, c2 = st.columns(2)
    dataset = c1.selectbox("Dataset", available, key="ua_dataset")
    routing = _json(str(METRICS / f"routing_{dataset}.json"))
    frame = _parquet(str(METRICS / f"routing_{dataset}.parquet"))
    bearing = c2.selectbox("Bearing", sorted(routing["decisions"]), key="ua_bearing")
    decision = routing["decisions"][bearing]
    rows = frame[frame["bearing_run_id"] == bearing].sort_values("sequence_index")
    profile = routing["profile"]

    st.markdown("#### Dataset profile")
    k = st.columns(4)
    k[0].metric("Files", f"{profile['n_files']:,}")
    k[1].metric("Sampling rate", f"{profile['sampling_rate_hz'] or 0:,.0f} Hz")
    k[2].metric("Recordings (this bearing)", f"{len(rows):,}")
    k[3].metric("Recognised as", ", ".join(d["dataset_id"] for d in profile["known_datasets"])
                or "unknown")
    st.caption(f"Sampling rate source: {profile['sampling_rate_source']}. "
               f"Channels named in headers: {profile['channels_found'] or 'none (headerless)'}.")

    st.markdown("#### Data quality")
    audit = _json(str(METRICS / f"audit_{dataset}.json"))
    if decision["quality_ok"]:
        st.success("Quality gate passed.")
    else:
        st.error("Quality gate failed.")
    for r in decision["quality_reasons"] + profile["warnings"]:
        st.write("-", r)
    if audit and bearing in audit.get("bearings", {}):
        a = audit["bearings"][bearing]
        st.caption(f"Full audit: {a['n_recordings']} recordings, {a['duplicate_files']} duplicate "
                   f"files, samples/recording {a['samples_per_recording']}, estimated missing "
                   f"recordings {a.get('missing_recordings_estimate', 'n/a')}.")

    st.markdown("#### Model applicability")
    app = pd.DataFrame([{"model": m, "level": v["level"], "shift ratio": round(v["shift_ratio"], 2)}
                        for m, v in decision["applicability"].items()])
    st.dataframe(app, hide_index=True)
    with st.expander("Reasons"):
        for m, v in decision["applicability"].items():
            st.markdown(f"**{m}**")
            for r in v["reasons"]:
                st.write("-", r)

    # The banner is the CAUSAL decision at the latest recording (what the system
    # says now); the whole-run summary above is retrospective.
    current = decision.get("current", decision)
    model = current.get("model")
    now_level = rows[f"level_{model}"].iloc[-1] if model else decision.get("level")
    level, title, body = status_banner({"status": current["status"], "model": model,
                                        "level": now_level,
                                        "validated_skill": current.get("validated_skill")})
    getattr(st, level)(f"**{title}**\n\n{body}")
    if "rul_status" in rows:
        counts = rows["rul_status"].value_counts().to_dict()
        st.caption("Decision per recording (causal - each uses only that recording and earlier "
                   f"ones): {counts}. Applicability table above: whole-run summary.")

    st.markdown("#### Health")
    hours = rows["elapsed_s"] / 3600
    stage_now = rows["stage"].iloc[-1]
    st.metric("Current degradation stage (severity band, not a fault diagnosis)", stage_now)
    st.line_chart(pd.DataFrame({"health indicator": rows["health_indicator"].to_numpy()},
                               index=hours.round(3).to_numpy()), x_label="elapsed time (h)",
                  y_label="HI (1 healthy -> 0 failed)")

    st.markdown("#### Remaining useful life")
    has_truth = "actual_rul_seconds" in rows and rows["actual_rul_seconds"].notna().any()
    if rows["predicted_rul_seconds"].isna().all():
        st.info("No RUL is shown for this bearing. See the applicability reasons above.")
        if has_truth:
            st.caption("Ground truth exists (evaluation mode) but is not compared against a "
                       "suppressed prediction.")
    else:
        last = rows.dropna(subset=["predicted_rul_seconds"]).iloc[-1]
        k = st.columns(3)
        k[0].metric(f"Predicted RUL at recording {int(last['sequence_index'])} "
                    f"({last['rul_status']})", f"{last['predicted_rul_seconds'] / 3600:.2f} h")
        k[1].metric("90% conformal interval",
                    f"{last['rul_lo'] / 3600:.2f} - {last['rul_hi'] / 3600:.2f} h")
        if has_truth and pd.notna(last["actual_rul_seconds"]):
            err = (last["predicted_rul_seconds"] - last["actual_rul_seconds"]) / 3600
            k[2].metric("Error vs ground truth", f"{err:+.2f} h",
                        help="positive = over-estimate (unsafe direction)")
        chart = pd.DataFrame({"predicted (h)": rows["predicted_rul_seconds"] / 3600,
                              "interval low (h)": rows["rul_lo"] / 3600,
                              "interval high (h)": rows["rul_hi"] / 3600}).set_index(hours)
        if has_truth:
            chart["actual (h)"] = (rows["actual_rul_seconds"] / 3600).to_numpy()
        st.line_chart(chart, x_label="elapsed time (h)", y_label="RUL (h)")

    canonical = Path(routing.get("canonical_path") or PROCESSED / f"canonical_{dataset}.parquet")
    _raw_panel(dataset, bearing, rows, canonical)
    _feature_trends(dataset, bearing, canonical)
    _profile_box()


def _raw_panel(dataset: str, bearing: str, rows: pd.DataFrame, canonical: Path) -> None:
    st.markdown("#### Measured signal and spectrum")
    manifest = _json(str(canonical.with_suffix(".json")))
    if manifest is None:
        st.caption("No canonical manifest - raw source location unknown.")
        return
    seq = st.slider("Recording (sequence index)", int(rows["sequence_index"].min()),
                    int(rows["sequence_index"].max()), int(rows["sequence_index"].max()),
                    key="ua_seq")
    if not st.button("Load this recording from the source file", key="ua_load"):
        st.caption("Raw panels re-read the real file on request (a college file is 2M samples).")
        return
    from bearing_pdm.adapters import get_adapter
    adapter = get_adapter(dataset)
    try:
        run = [r for r in adapter.discover(manifest["source_root"], role=manifest.get("role"))
               if r.run_id == bearing][0]
        rec = next(r for r in adapter.recordings(run) if r.sequence_index == seq)
    except (FileNotFoundError, IndexError, StopIteration, OSError) as e:
        st.warning(f"Source data unreachable ({type(e).__name__}) - showing cached features only.")
        return
    fs = run.sampling_rate_hz
    for ch, x in rec.signals.items():
        if not ch.startswith("vibration"):
            continue
        x = np.nan_to_num(np.asarray(x, dtype=float)[: int(fs)])
        st.caption(f"{ch} - {rec.recording_id}, first {len(x) / fs:.2f} s, measured at "
                   f"{fs:,.0f} Hz (amplitude in the source's recorded unit)")
        st.line_chart(pd.DataFrame({ch: x[: int(0.1 * fs)]},
                                   index=np.arange(int(0.1 * fs)) / fs * 1000),
                      x_label="time (ms)", y_label="amplitude")
        freqs = np.fft.rfftfreq(len(x), 1 / fs)
        mag = np.abs(np.fft.rfft(x - x.mean())) / len(x)
        st.line_chart(pd.DataFrame({"magnitude": mag}, index=freqs), x_label="frequency (Hz)",
                      y_label="|FFT|")


def _feature_trends(dataset: str, bearing: str, canonical: Path) -> None:
    st.markdown("#### Feature trends (cached canonical features)")
    df = _parquet(str(canonical))
    if df is None:
        _missing("Canonical features", f"scripts/build_canonical_features.py --dataset {dataset}")
        return
    g = df[df["bearing_run_id"] == bearing].sort_values("sequence_index")
    feats = st.multiselect("Features", ["vibration_x_rms", "vibration_x_kurtosis",
                                        "vibration_x_crest_factor", "vibration_x_spectral_centroid_hz",
                                        "vibration_y_rms", "bearing_temp_mean"],
                           default=["vibration_x_rms"], key="ua_feats")
    feats = [f for f in feats if f in g and g[f].notna().any()]
    if feats:
        st.line_chart(g.set_index(g["elapsed_s"] / 3600)[feats], x_label="elapsed time (h)")


def _profile_box() -> None:
    with st.expander("Profile another folder (any dataset, read-only)"):
        roots = allowed_roots()
        st.caption("Allowed: this project and the dataset roots it already knows: "
                   + ", ".join(r.name for r in roots))
        folder = st.text_input("Folder path", key="ua_folder")
        if not folder:
            return
        path = Path(folder)
        if not is_within(path, roots) or not path.expanduser().is_dir():
            st.error("Not an allowed, existing folder.")
            return
        from bearing_pdm.profiler import profile_folder
        p = profile_folder(path.expanduser())
        st.json({k: p[k] for k in ("n_files", "known_datasets", "sampling_rate_hz",
                                   "sampling_rate_source", "channels_found", "warnings")})


# ---------------------------------------------------------------------------
# Cross-Dataset Validation
# ---------------------------------------------------------------------------

def render_validation() -> None:
    st.subheader("Cross-Dataset Validation")
    report = _json(str(METRICS / "cross_dataset.json"))
    st.markdown("#### Datasets")
    st.dataframe(DATASET_FACTS, hide_index=True)
    if report is None:
        _missing("Cross-dataset results", "scripts/run_cross_dataset.py")
        return
    from bearing_pdm.experiments import RESULTS_SCHEMA_VERSION
    if report.get("schema_version") != RESULTS_SCHEMA_VERSION:
        st.warning("reports/metrics/cross_dataset.json was produced by an older version of the "
                   "code (schema " + str(report.get("schema_version")) + "). Regenerate it with "
                   "`python scripts/run_cross_dataset.py`.")
        return
    st.caption(f"Seed {report['config']['seed']}; 90% intervals; every number below comes from "
               "reports/metrics/cross_dataset.json. Life-fraction skill > 0 means better than a "
               "label-free constant guess (half of life used).")

    s = pd.DataFrame(report["summary"])
    categories = ["WITHIN-DOMAIN", "ZERO-SHOT", "CALIBRATED", "MULTI-DATASET"]
    category = st.radio("Experiment category", categories, horizontal=True, key="cv_cat")
    cols = {"experiment": "experiment", "model": "model", "test_domain": "test dataset",
            "n_bearings": "bearings", "mae_seconds": "MAE (s)", "rmse_seconds": "RMSE (s)",
            "fraction_mae": "life-fraction MAE", "fraction_skill": "skill vs constant",
            "overestimate_pct": "over-estimates (%)", "coverage_conformal_abs": "coverage (abs.)",
            "coverage_tree_5_95": "coverage (tree spread)"}
    view = s[s["category"] == category][list(cols)].rename(columns=cols)
    st.dataframe(view.round(3), hide_index=True)

    pb = pd.DataFrame(report["per_bearing"])
    with st.expander("Per-bearing results"):
        st.dataframe(pb[pb["category"] == category][
            ["experiment", "model", "bearing_run_id", "n", "mae_seconds", "median_abs_error_seconds",
             "fraction_mae", "fraction_skill", "overestimate_pct", "underestimate_pct",
             "coverage_conformal_abs", "width_conformal_abs_seconds"]].round(3), hide_index=True)

    st.markdown("#### Applicability vs error")
    ave = report["applicability_vs_error"]
    for model in ("raw_seconds", "sn_fraction"):
        if model in ave:
            st.write(f"**{model}** - Spearman(shift ratio, life-fraction MAE) = "
                     f"{ave[model]['spearman_shift_vs_fraction_mae']:.2f} (n = {ave[model]['n']})")
            st.dataframe(pd.DataFrame(ave[model]["by_level"]).T.round(3))

    st.markdown("#### Actual vs predicted RUL (held-out bearings)")
    pred = _parquet(str(METRICS / "cross_dataset_predictions.parquet"))
    if pred is not None:
        c1, c2, c3 = st.columns(3)
        exp = c1.selectbox("Experiment", sorted(pred["experiment"].unique()), key="cv_exp")
        sub = pred[pred["experiment"] == exp]
        model = c2.selectbox("Model", sorted(sub["model"].unique()), key="cv_model")
        sub = sub[sub["model"] == model]
        bearing = c3.selectbox("Bearing", sorted(sub["bearing_run_id"].unique()), key="cv_bearing")
        q = sub[sub["bearing_run_id"] == bearing].sort_values("sequence_index")
        st.line_chart(pd.DataFrame({"actual (h)": q["actual_rul_seconds"].to_numpy() / 3600,
                                    "predicted (h)": q["predicted_rul_seconds"].to_numpy() / 3600,
                                    "interval low (h)": q["rul_lo_abs"].to_numpy() / 3600,
                                    "interval high (h)": q["rul_hi_abs"].to_numpy() / 3600},
                                   index=(q["elapsed_s"] / 3600).to_numpy()),
                      x_label="elapsed time (h)", y_label="RUL (h)")

    st.markdown("#### Health indicator across datasets")
    hi = report.get("health_indicator", {})
    st.dataframe(pd.DataFrame([{"dataset": d, "HI": h, "bearings": m["n_bearings"],
                                "monotonicity": m.get("monotonicity_mean"),
                                "trendability (min |rho|)": m.get("trendability_min_abs_spearman"),
                                "prognosability": m.get("prognosability"),
                                "Spearman(HI, RUL)": m.get("spearman_rul_mean")}
                               for d, v in hi.items() for h, m in v.items()]).round(3),
                 hide_index=True)

    figures = sorted(Path("reports/figures").glob("*.png"))
    if figures:
        with st.expander("Report figures (reports/figures/)"):
            for f in figures:
                st.image(str(f), caption=f.name)
