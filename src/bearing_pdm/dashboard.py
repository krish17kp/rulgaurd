"""Streamlit review dashboard (command.md section 16, minimal M8 scope
per section 26.1/26.9). Loads cached Parquet/DuckDB/joblib artifacts only -
never trains on page load. Raw signal/FFT panels re-read the specific
selected window/acquisition from the real source file (bounded, single
small read) so plots are genuine measured data, not fabricated from the
cached feature row.

Run: python scripts/run_dashboard.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from bearing_pdm.college import COLLEGE_COLUMNS
from bearing_pdm.config import load_data_paths, resolve_stored_path
from bearing_pdm.femto import read_acceleration, read_temperature
from bearing_pdm.health import apply_pca_hi, apply_reference_hi, apply_transparent_hi
from bearing_pdm.modeling import predict_naive_baseline, predict_tree_baseline
from bearing_pdm.stages import CRITICAL, DEGRADING, HEALTHY, assign_stages
from bearing_pdm.storage import batch_roles, get_connection

CONFIG_PATH = "config/data_paths.toml"

# Streamlit Community Cloud clones the repo fresh, so none of the gitignored
# local artifacts exist there (config/data_paths.toml, the DuckDB catalogue,
# data/processed/, artifacts/models/, reports/metrics/). When they are absent
# the dashboard falls back to `deploy_data/`, a tracked snapshot of real
# pipeline outputs built by scripts/build_deploy_snapshot.py. Same five views,
# same computations - a representative subset of the data, never synthesised.
DEPLOY_DIR = Path(__file__).resolve().parents[2] / "deploy_data"


def _cloud_mode() -> bool:
    return not Path(CONFIG_PATH).exists() and DEPLOY_DIR.is_dir()


def _artifact(local_path: str) -> str:
    """Local artifact path, or its flat copy inside the deployment snapshot."""
    return str(DEPLOY_DIR / Path(local_path).name) if _cloud_mode() else local_path


@st.cache_resource
def _load_paths():
    return load_data_paths(CONFIG_PATH)


@st.cache_data
def _list_batches() -> pd.DataFrame:
    """Every feature batch, annotated with the role(s) its rows actually carry.

    The role annotation matters: once a `test_censored` batch exists it is the
    newest femto batch, so picking "the latest batch" silently swaps the six
    learning bearings for the eleven censored test bearings - no ground-truth
    RUL, and different bearings entirely (docs/decisions.md D15).
    """
    if _cloud_mode():
        snap = pd.read_parquet(DEPLOY_DIR / "feature_snapshot.parquet",
                               columns=["dataset_id", "role"])
        return pd.DataFrame([
            {
                "dataset_id": dataset_id,
                "feature_batch_id": f"deploy-snapshot-{dataset_id}",
                "parquet_path": str(DEPLOY_DIR / "feature_snapshot.parquet"),
                "row_count": len(g),
                "code_version": "deployment snapshot",
                "created_at": "bundled with the repository",
                "roles": ",".join(sorted(g["role"].unique())),
            }
            for dataset_id, g in snap.groupby("dataset_id")
        ])

    paths = _load_paths()
    con = get_connection(paths.duckdb_path)
    try:
        batches = con.execute(
            "SELECT dataset_id, feature_batch_id, parquet_path, row_count, code_version, created_at "
            "FROM feature_batches ORDER BY created_at DESC"
        ).fetchdf()
    finally:
        con.close()

    roles = []
    for stored in batches["parquet_path"]:
        path = resolve_stored_path(stored)
        roles.append(",".join(sorted(batch_roles(path))) if path.is_file() else "unreadable")
    batches["roles"] = roles
    return batches


# Role shown by default per dataset: the one carrying ground-truth RUL, so the
# dashboard opens on the data the Health Indicator and RUL tabs are about.
_PREFERRED_ROLE = {"femto": "learning", "college": "college_run"}


@st.cache_data
def _load_batch(parquet_path: str) -> pd.DataFrame:
    # Resolved, not used raw: a batch built on Windows recorded the path with
    # backslashes, which is unopenable here (docs/decisions.md D13).
    return pd.read_parquet(resolve_stored_path(parquet_path))


def _resolve_source(stored: str) -> Path:
    """Locate a raw source file recorded by an earlier run, re-rooting it under
    this machine's configured dataset directories when the stored path came
    from another machine."""
    return resolve_stored_path(stored, _load_paths().source_search_roots())


@st.cache_resource
def _load_joblib(path: str):
    import joblib
    p = Path(path)
    if not p.exists():
        return None
    return joblib.load(p)


@st.cache_data
def _load_metrics(path: str) -> dict | None:
    """Same missing-artifact contract as _load_joblib: None, never a traceback."""
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


@st.cache_data
def _load_predictions(path: str) -> pd.DataFrame | None:
    """Per-row held-out predictions written by scripts/evaluate_models.py - the
    same ones the headline MAE is computed from, so a plot built here cannot
    disagree with the reported metric."""
    p = Path(path)
    return pd.read_parquet(p) if p.exists() else None


@st.cache_data
def _load_raw_snapshot() -> pd.DataFrame:
    """The measured windows bundled for cloud mode: genuine recorded waveforms,
    a representative few per bearing, not the full acquisition history."""
    return pd.read_parquet(DEPLOY_DIR / "raw_signal_samples.parquet")


def _raw_from_snapshot(row: pd.Series) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    snap = _load_raw_snapshot()
    match = snap[
        (snap["bearing_run_id"] == row["bearing_run_id"])
        & (snap["sequence_index"] == int(row["sequence_index"]))
    ]
    if match.empty:
        raise FileNotFoundError(
            f"No bundled waveform for {row['bearing_run_id']} #{row['sequence_index']}"
        )
    hit = match.iloc[0]
    temp = hit["temperature_c"]
    return (
        np.asarray(hit["vibration_x"], dtype=float),
        np.asarray(hit["vibration_y"], dtype=float),
        None if temp is None else np.asarray(temp, dtype=float),
    )


def _bundled_positions(df_bearing: pd.DataFrame) -> list[int]:
    """Row positions in `df_bearing` whose waveform ships in the snapshot.

    Must match on the bearing as well as the index: sequence_index restarts at 0
    for every bearing and every dataset, so an index-only match offers windows
    that belong to a different run and have no waveform here.
    """
    if df_bearing.empty:
        return []
    snap = _load_raw_snapshot()
    bearing = df_bearing["bearing_run_id"].iloc[0]
    have = set(snap.loc[snap["bearing_run_id"] == bearing, "sequence_index"].astype(int))
    return [i for i, s in enumerate(df_bearing["sequence_index"].astype(int)) if s in have]


def _life_stage_label(position: int, n_rows: int) -> str:
    """Where a bundled window sits in the bearing's own record. A position label,
    not a degradation stage - stages come from stages.py."""
    frac = position / max(n_rows - 1, 1)
    return "healthy" if frac < 1 / 3 else "mid-life" if frac < 2 / 3 else "late"


def _load_raw_femto_row(row: pd.Series) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    source = _resolve_source(row["source_file_path"])
    bearing_dir = source.parent
    acc_index = int(source.stem.split("_")[1])
    acc_df = read_acceleration(bearing_dir, acc_index)
    temp = None
    if row["temp_available"]:
        # best-effort: re-derive nearest temp index the same way pipeline.py did
        from bearing_pdm.femto import build_temperature_time_index, find_nearest_temperature_index
        idx = find_nearest_temperature_index(bearing_dir, acc_index, build_temperature_time_index(bearing_dir))
        if idx is not None:
            temp = read_temperature(bearing_dir, idx)["temperature_c"].to_numpy()
    return acc_df["accel_horizontal"].to_numpy(), acc_df["accel_vertical"].to_numpy(), temp


def _load_raw_college_row(row: pd.Series) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    skiprows = int(row["row_start"])
    nrows = int(row["row_end"]) - int(row["row_start"]) + 1
    window = pd.read_csv(
        _resolve_source(row["source_file_path"]),
        header=None, names=COLLEGE_COLUMNS, skiprows=skiprows, nrows=nrows,
    )
    return (
        window["vibration_x"].to_numpy(), window["vibration_y"].to_numpy(),
        window["bearing_temp_c"].to_numpy(), window["ambient_temp_c"].to_numpy(),
    )


def _fft_plot_data(x: np.ndarray, sample_rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
    x = x[~np.isnan(x)]
    freqs = np.fft.rfftfreq(len(x), d=1.0 / sample_rate_hz)
    magnitude = np.abs(np.fft.rfft(x))
    return freqs, magnitude


def main() -> None:
    st.set_page_config(page_title="RULGuard - Capstone Review", layout="wide")
    st.title("RULGuard: Bearing Health Monitoring and Remaining Useful Life Prediction")
    st.caption(
        "Research prototype capstone, not production. Cached artifacts only "
        "(no training on page load). See docs/prd.md for explicit non-claims."
    )
    if _cloud_mode():
        st.info(
            "**Running on a precomputed deployment snapshot.** Every number, curve and "
            "waveform here is a real output of the project's own pipeline, but only a "
            "representative subset ships with the repository: three FEMTO bearings (one "
            "per operating condition) with their full feature history, a few genuinely "
            "measured raw windows each, and the evaluation artifacts. The full datasets "
            "are not bundled, nothing is recomputed or streamed live, and no sensor is "
            "connected - see Architecture & Limitations."
        )

    VIEWS = ["Signal & FFT", "Health Indicator", "RUL Prediction",
             "Model Evaluation", "Architecture & Limitations"]
    view = st.sidebar.radio("View", VIEWS)

    # Only the first three views are about one specific bearing and window.
    # Model Evaluation is cross-bearing and Architecture is static, so their
    # controls are not rendered at all rather than shown and silently ignored.
    needs_selection = view in VIEWS[:3]

    batches = _list_batches()
    if batches.empty:
        st.error("No feature batches found. Run scripts/build_features.py first.")
        return

    if needs_selection:
        dataset_id = st.sidebar.selectbox("Dataset", sorted(batches["dataset_id"].unique()))
        dataset_batches = batches[batches["dataset_id"] == dataset_id].reset_index(drop=True)

        # Default to the batch carrying ground-truth RUL rather than merely the
        # newest one (D15); let the user switch when several batches exist.
        preferred = _PREFERRED_ROLE.get(dataset_id)
        default_idx = next(
            (i for i, r in enumerate(dataset_batches["roles"]) if preferred and preferred in r.split(",")),
            0,
        )
        if len(dataset_batches) > 1:
            labels = [
                f"{r.roles} | {r.row_count} rows | {r.feature_batch_id[:8]}"
                for r in dataset_batches.itertuples()
            ]
            choice = st.sidebar.selectbox("Feature batch (role)", labels, index=default_idx)
            batch_row = dataset_batches.iloc[labels.index(choice)]
        else:
            batch_row = dataset_batches.iloc[default_idx]

        st.sidebar.caption(
            f"batch {batch_row['feature_batch_id'][:8]}... | role(s) {batch_row['roles']} | "
            f"{batch_row['row_count']} rows | code {batch_row['code_version']} | {batch_row['created_at']}"
        )
        if "learning" not in str(batch_row["roles"]).split(",") and dataset_id == "femto":
            st.sidebar.warning(
                f"This batch holds role(s) '{batch_row['roles']}', which have no ground-truth "
                "RUL (censored by design). Predictions are shown without a true value to "
                "compare against - see the Model Evaluation view for scored results."
            )
        if dataset_id == "college":
            st.sidebar.info("College batch is a representative sample (command.md section 26.8), not the full 129-file run - see docs/decisions.md.")

        df = _load_batch(batch_row["parquet_path"])
        if _cloud_mode():
            df = df[df["dataset_id"] == dataset_id].reset_index(drop=True)
        bearing_run_id = st.sidebar.selectbox("Bearing / run", sorted(df["bearing_run_id"].unique()))
        df_bearing = df[df["bearing_run_id"] == bearing_run_id].sort_values("sequence_index").reset_index(drop=True)

        if _cloud_mode():
            bundled = _bundled_positions(df_bearing)
            # Plain string options, not format_func: select_slider round-trips the
            # displayed label back as the widget value, so an int-keyed format_func
            # is handed its own output on the next run.
            choices = {
                f"#{int(df_bearing['sequence_index'].iloc[p])} "
                f"({_life_stage_label(p, len(df_bearing))})": p
                for p in bundled
            }
            if choices:
                picked = st.sidebar.select_slider(
                    "Acquisition / window (bundled)", options=list(choices)
                )
                idx = choices[picked]
            else:
                idx = 0
            st.sidebar.caption(
                f"{len(bundled)} of this bearing's {len(df_bearing)} acquisitions ship with "
                "the repository as raw waveforms; the Health Indicator curve below still "
                "covers every acquisition."
            )
        else:
            idx = st.sidebar.slider("Acquisition / window index", 0, len(df_bearing) - 1, 0)
        row = df_bearing.iloc[idx]

    if view == "Signal & FFT":
        # In cloud mode the raw file is not on disk - the waveform comes from the
        # bundled snapshot - so identify the acquisition rather than a local path.
        if _cloud_mode():
            st.subheader(
                f"Row {idx}/{len(df_bearing)-1} - {bearing_run_id} "
                f"acquisition #{int(row['sequence_index'])}"
            )
        else:
            st.subheader(f"Row {idx}/{len(df_bearing)-1} - {_resolve_source(row['source_file_path'])}")
        try:
            if _cloud_mode():
                vib_x, vib_y, temp = _raw_from_snapshot(row)
            elif dataset_id == "femto":
                vib_x, vib_y, temp = _load_raw_femto_row(row)
            else:
                vib_x, vib_y, bearing_temp, ambient_temp = _load_raw_college_row(row)
                temp = bearing_temp

            sample_step = max(1, len(vib_x) // 2000)  # downsample for the browser
            c1, c2 = st.columns(2)
            c1.line_chart(pd.DataFrame({"vibration_x": vib_x[::sample_step]}))
            c2.line_chart(pd.DataFrame({"vibration_y": vib_y[::sample_step]}))
            if temp is not None:
                st.line_chart(pd.DataFrame({"temperature_c": temp}))
            else:
                st.info("No temperature reading available for this row (temp_available=False).")

            freqs, mag = _fft_plot_data(vib_x, row["sample_rate_hz"])
            st.line_chart(pd.DataFrame({"magnitude": mag}, index=freqs).iloc[: len(freqs) // 4])
            st.caption("FFT of vibration_x (real signal re-read from the source file, not the cached feature row).")
        except FileNotFoundError:
            st.warning("Source file not reachable from this machine's config/data_paths.toml - showing cached features only.")

        st.dataframe(row[[c for c in df.columns if c.startswith("vibration_") or c.startswith("bearing_temp") or c.startswith("ambient_temp")]].to_frame("value"))

    if view == "Health Indicator":
        if dataset_id != "femto":
            st.info(
                "The cached HI models (artifacts/models/*_hi_*.joblib) were fit only on FEMTO learning "
                "bearings (scripts/build_health.py). Applying a FEMTO-fit scaler/PCA to college's very "
                "different feature scale is out-of-domain and produces meaningless values (confirmed while "
                "building this dashboard - PCA HI swung below -3 on college data). Not shown for college in "
                "this MVP; a college-specific HI would need its own fit, deferred (docs/decisions.md). "
                "Note: the reference HI (D18) normalises each bearing against its own early life, "
                "so a college-specific fit is now feasible - it is the next step, not done yet."
            )
        else:
            reference_model = _load_joblib(_artifact("artifacts/models/reference_hi_model.joblib"))
            thresholds = _load_joblib(_artifact("artifacts/models/stage_thresholds.joblib"))
            baseline = _load_joblib(_artifact("artifacts/models/transparent_hi_baseline.joblib"))
            pca_model = _load_joblib(_artifact("artifacts/models/pca_hi_model.joblib"))

            if reference_model is None:
                st.warning(
                    "No fitted reference HI found - run scripts/build_health.py to generate "
                    "artifacts/models/reference_hi_model.joblib."
                )
            else:
                hi = apply_reference_hi(df_bearing, reference_model)
                st.metric(
                    "Current health indicator", f"{hi.iloc[idx]:.3f}",
                    help="Reference HI: ~0.95 at this bearing's own healthy baseline, "
                         "->0 as degradation progresses. Dimensionless.",
                )

                # Stage badge. A severity band on the HI, never a fault type.
                if thresholds is None:
                    st.info("Stage thresholds not found - run scripts/build_health.py.")
                else:
                    stage = assign_stages(df_bearing, hi, thresholds).iloc[idx]
                    {HEALTHY: st.success, DEGRADING: st.warning, CRITICAL: st.error}.get(
                        stage, st.info
                    )(f"Degradation stage: **{stage}**")
                    st.caption(
                        f"Severity band on the health indicator, not a fault diagnosis. "
                        f"DEGRADING below {thresholds.hi_warn:.3f} (a fitted quantile of the "
                        f"training bearings' healthy HI); CRITICAL below "
                        f"{thresholds.hi_critical:.3f} (a threshold derived from the score "
                        f"mapping's own end-of-life anchor, not an independently fitted "
                        f"quantile - see docs/decisions.md D20). Committed only after "
                        f"{thresholds.persistence} consecutive acquisitions agree."
                    )

                chart_data = {"reference_hi (selected)": hi}
                if baseline is not None:
                    chart_data["transparent_hi (legacy)"] = apply_transparent_hi(df_bearing, baseline)
                if pca_model is not None:
                    chart_data["pca_hi (legacy)"] = apply_pca_hi(df_bearing, pca_model)
                st.line_chart(pd.DataFrame(chart_data, index=df_bearing["sequence_index"]))
                st.caption(
                    "The two legacy curves are shown because their failure is the evidence for "
                    "the current one (docs/decisions.md D18): transparent_hi pinned 47.5% of all "
                    "learning acquisitions at exactly 1.0 (88.9% of Bearing3_2), and pca_hi's "
                    "usable range collapsed to ~2% on Bearing3_1. Neither is used for staging."
                )

    if view == "RUL Prediction":
        if dataset_id != "femto":
            st.info(
                "The cached RUL models (artifacts/models/rul_*.joblib) were fit only on FEMTO learning "
                "bearings (scripts/train_models.py) - same out-of-domain concern as the Health Indicator tab. "
                "College's real RUL evidence is the walk-forward evaluation in the Model Evaluation view, "
                "which fits fresh models inside each fold on college's own data (src/bearing_pdm/evaluation.py)."
            )
        else:
            naive_model = _load_joblib(_artifact("artifacts/models/rul_naive.joblib"))
            tree_model = _load_joblib(_artifact("artifacts/models/rul_extra_trees.joblib"))
            selected_path = Path(_artifact("artifacts/models/rul_selected_model.json"))
            selected = json.loads(selected_path.read_text())["selected"] if selected_path.exists() else "extra_trees"

            col1, col2, col3 = st.columns(3)
            if tree_model is not None:
                pred_tree = predict_tree_baseline(df_bearing.iloc[[idx]], tree_model).iloc[0]
                col1.metric(f"ExtraTrees prediction {'(selected)' if selected == 'extra_trees' else ''}", f"{pred_tree/3600:.2f} h")
            elif _cloud_mode():
                # The fitted forest is ~104MB, over GitHub's hard limit, so it is
                # not bundled. Its leave-one-bearing-out prediction for this exact
                # acquisition is - and that one is out-of-sample, which the frozen
                # model's own prediction for a bearing it trained on is not.
                lobo_all = _load_predictions(_artifact("reports/metrics/rul_predictions.parquet"))
                hit = pd.DataFrame() if lobo_all is None else lobo_all[
                    (lobo_all["model"] == "extra_trees")
                    & (lobo_all["bearing_run_id"] == bearing_run_id)
                    & (lobo_all["sequence_index"] == int(row["sequence_index"]))
                ]
                if not hit.empty:
                    col1.metric(
                        "ExtraTrees prediction (held-out)",
                        f"{float(hit['predicted_rul_seconds'].iloc[0])/3600:.2f} h",
                        help="From the leave-one-bearing-out evaluation: predicted by a "
                             "model fit on the other five bearings, never on this one.",
                    )
            if naive_model is not None:
                pred_naive = predict_naive_baseline(df_bearing.iloc[[idx]], naive_model).iloc[0]
                col2.metric(f"Naive prediction {'(selected)' if selected == 'naive' else ''}", f"{pred_naive/3600:.2f} h")
            if pd.notna(row["rul_seconds"]):
                col3.metric("Ground truth (role=learning only)", f"{row['rul_seconds']/3600:.2f} h")
            else:
                col3.metric("Ground truth", "unknown (censored/full_test role)")
            st.caption(
                "Uncertainty/confidence interval not implemented in this MVP - see docs/prd.md non-claims. "
                "Model never retrained here; loaded from artifacts/models/*.joblib."
                + (
                    " On this deployment the ~104MB fitted forest is not bundled, so the "
                    "ExtraTrees figure shown is its held-out prediction for this acquisition, "
                    "read from the evaluation artifact."
                    if _cloud_mode() else ""
                )
            )

            # Trajectory over the whole bearing life. Deliberately NOT the cached
            # model above: that one was fit on all 6 learning bearings including
            # this one, so its curve would be in-sample. These come from the
            # leave-one-bearing-out run, where this bearing was the held-out fold.
            lobo = _load_predictions(_artifact("reports/metrics/rul_predictions.parquet"))
            if lobo is not None:
                track = lobo[
                    (lobo["model"] == "extra_trees") & (lobo["bearing_run_id"] == bearing_run_id)
                ].sort_values("sequence_index")
                if not track.empty:
                    st.markdown("**Predicted vs actual RUL across this bearing's life**")
                    st.line_chart(
                        pd.DataFrame({
                            "actual RUL (h)": track["actual_rul_seconds"].to_numpy() / 3600.0,
                            "predicted RUL (h)": track["predicted_rul_seconds"].to_numpy() / 3600.0,
                        }, index=track["sequence_index"].to_numpy()),
                        x_label="acquisition index", y_label="RUL (hours)",
                    )
                    err_h = float(
                        (track["predicted_rul_seconds"] - track["actual_rul_seconds"]).abs().mean()
                    ) / 3600.0
                    st.caption(
                        f"Out-of-sample: every point was predicted by a model fit on the other "
                        f"five bearings only (MAE {err_h:.2f} h over {len(track)} acquisitions). "
                        "Where the predicted line sits above the actual line, the model is "
                        "claiming more remaining life than the bearing had."
                    )

    if view == "Model Evaluation":
        st.caption(
            "Cross-bearing results, pooled over every held-out fold. This view is global, "
            "which is why the sidebar shows no bearing or window selector for it."
        )
        evaluation = _load_metrics(_artifact("reports/metrics/rul_evaluation.json"))
        hi_comparison = _load_metrics(_artifact("reports/metrics/health_indicator_comparison.json"))
        predictions = _load_predictions(_artifact("reports/metrics/rul_predictions.parquet"))

        if evaluation is None:
            st.warning(
                "`reports/metrics/rul_evaluation.json` not found. It is a generated "
                "artifact (gitignored), so a fresh checkout has to build it once:\n\n"
                "```\nPYTHONPATH=src python scripts/evaluate_models.py "
                "--config config/data_paths.toml\n```"
            )
        else:
            st.subheader("FEMTO - leave-one-bearing-out (out-of-sample)")
            overall = evaluation.get("femto_lobo_overall_by_model", {})
            tree, naive = overall.get("extra_trees"), overall.get("naive")
            if tree and naive:
                c1, c2, c3 = st.columns(3)
                c1.metric(
                    "ExtraTrees MAE (FEMTO)", f"{tree['mae_seconds']/3600:.2f} h",
                    delta=f"{(tree['mae_seconds']-naive['mae_seconds'])/3600:.2f} h vs naive",
                    delta_color="inverse",
                    help="Mean absolute error over all 7,534 held-out rows. Lower is better.",
                )
                c2.metric("Naive baseline MAE (FEMTO)", f"{naive['mae_seconds']/3600:.2f} h")
                c3.metric(
                    "ExtraTrees over-estimate rate (FEMTO)",
                    f"{100*tree['overestimate_rate']:.1f}%",
                    help="Share of held-out rows predicted to have MORE life left than "
                         "they actually had - the unsafe direction.",
                )
                st.caption(
                    f"n = {tree['n']} held-out rows, 6 bearings, each scored by a model that "
                    f"never saw it. Median absolute error {tree['median_abs_error_seconds']/3600:.2f} h; "
                    f"mean signed error {tree['mean_signed_error_seconds']/3600:+.2f} h "
                    "(negative = conservative on average)."
                )

            femto_folds = pd.DataFrame(evaluation.get("femto_lobo", []))
            if not femto_folds.empty:
                st.markdown("**Per-bearing error - ExtraTrees vs naive baseline**")
                mae_by_bearing = (
                    femto_folds.pivot(index="held_out_bearing", columns="model", values="mae_seconds") / 3600.0
                )
                st.bar_chart(mae_by_bearing, y_label="MAE (hours)", x_label="held-out bearing")
                st.caption(
                    "The mean hides the spread: ExtraTrees loses to naive on "
                    f"{int((mae_by_bearing['extra_trees'] > mae_by_bearing['naive']).sum())} "
                    "of 6 bearings. Reported rather than averaged away."
                )

                st.markdown("**Which direction is each model wrong in?**")
                signed = (
                    femto_folds.pivot(
                        index="held_out_bearing", columns="model", values="mean_signed_error_seconds"
                    ) / 3600.0
                )
                st.bar_chart(signed, y_label="mean signed error (hours)", x_label="held-out bearing")
                st.warning(
                    "**Bars above zero are the unsafe direction.** A positive signed error means "
                    "the model predicted more remaining life than the bearing actually had, so "
                    "maintenance would be scheduled after the failure it was meant to prevent. "
                    "An equally large negative error only retires a bearing early. This is why "
                    "MAE alone is not a sufficient summary, and why the hidden-set score "
                    "(`phm2012_score`) penalises over-prediction ~4x harder."
                )

            if predictions is not None:
                femto_pred = predictions[
                    (predictions["dataset_id"] == "femto") & (predictions["model"] == "extra_trees")
                ]
                if not femto_pred.empty:
                    st.markdown("**Actual vs predicted RUL (ExtraTrees, held-out rows only)**")
                    scatter = pd.DataFrame({
                        "actual RUL (h)": femto_pred["actual_rul_seconds"] / 3600.0,
                        "predicted (h)": femto_pred["predicted_rul_seconds"] / 3600.0,
                        "perfect prediction (h)": femto_pred["actual_rul_seconds"] / 3600.0,
                    })
                    st.scatter_chart(
                        scatter, x="actual RUL (h)",
                        y=["predicted (h)", "perfect prediction (h)"], height=360,
                    )
                    st.caption(
                        f"All {len(femto_pred)} held-out predictions. The straight line is "
                        "y = x (a perfect model); points above it are over-predictions. "
                        "Flattening at the extremes is the expected tree-ensemble behaviour - "
                        "it cannot extrapolate beyond the RUL range it was trained on."
                    )

        hidden = _load_metrics(_artifact("reports/metrics/hidden_set_evaluation.json"))
        # results.official is the challenge's own ground-truth table; the
        # archive_derived variant exists only because Bearing1_4 disagrees
        # between the two (docs/decisions.md D17). Show the official one.
        hidden_official = (
            (hidden or {}).get("results", {}).get("official", {}).get("summary_by_model", {})
        )
        if hidden_official.get("extra_trees"):
            st.subheader("FEMTO hidden set - the only fully out-of-sample result")
            h = hidden_official["extra_trees"]
            c1, c2, c3 = st.columns(3)
            c1.metric("ExtraTrees MAE (hidden set)", f"{h['mae_seconds']/3600:.2f} h")
            c2.metric(
                "PHM 2012 score", f"{h['phm2012_score']:.4f}",
                help="Official challenge metric, in (0, 1], higher is better. It penalises "
                     "predicting too much remaining life about 4x harder than too little.",
            )
            c3.metric(
                "Over-estimates", f"{h['n_overestimates']}/{h['n_bearings']} bearings",
                help="Bearings predicted to have more life left than they actually had.",
            )
            st.caption(
                "11 bearings the models have never seen, scored once against the challenge's "
                "own continuation archive after the pipeline was frozen. n = 11 predictions, "
                "one per bearing at the end of its censored prefix - small by construction, "
                "and reported as-is (docs/decisions.md D16/D17)."
            )

        if evaluation is not None:
            college_overall = evaluation.get("college_overall_by_model", {})
            if college_overall:
                st.subheader("College rig - chronological walk-forward")
                ct = college_overall.get("extra_trees", {})
                c1, c2 = st.columns(2)
                c1.metric("ExtraTrees MAE (college)", f"{ct.get('mae_seconds', float('nan'))/3600:.2f} h")
                c2.metric("Over-estimate rate (college)", f"{100*ct.get('overestimate_rate', float('nan')):.1f}%")
                st.error(
                    "**Every single held-out college prediction is an over-prediction.** On this "
                    "one run ExtraTrees is optimistic 100% of the time, by "
                    f"{ct.get('mae_seconds', 0)/3600:.1f} h on average. Reported because it is the "
                    "finding, not a failure to hide."
                )
                st.info(evaluation.get("college_naive_caveat", ""))

        st.subheader("Health indicator comparison")
        if hi_comparison is None:
            st.warning(
                "`reports/metrics/health_indicator_comparison.json` not found. Generate it with:\n\n"
                "```\nPYTHONPATH=src python scripts/build_health.py "
                "--config config/data_paths.toml\n```"
            )
        else:
            lobo = hi_comparison.get("reference_hi", {}).get("leave_one_bearing_out", {})
            per_bearing = pd.DataFrame(lobo.get("per_bearing", []))
            if not per_bearing.empty and "spearman" in per_bearing:
                st.bar_chart(
                    per_bearing.set_index("bearing_run_id")["spearman"],
                    y_label="Spearman(HI, life progression)", x_label="bearing",
                )
                st.caption(
                    f"Selected HI: **{hi_comparison.get('selected', 'unknown')}**, calibrated "
                    "leave-one-bearing-out. Negative is correct - the HI should fall as the "
                    "bearing ages. Bearing3_1 and Bearing3_2 are weak because their degradation "
                    "is flat-then-cliff, not gradual (see the Limitations tab)."
                )

        with st.expander("Raw metric files"):
            if evaluation is not None:
                st.json(evaluation)
            if hi_comparison is not None:
                st.json(hi_comparison)

    if view == "Architecture & Limitations":
        st.subheader("What this system actually is")
        st.markdown(
            "```\n"
            "bearing vibration + temperature CSVs   (FEMTO/PRONOSTIA, college rig)\n"
            "  -> dataset adapters                  femto.py / college.py\n"
            "  -> windowing + feature extraction    features.py  (time-domain stats, FFT/spectral)\n"
            "  -> feature table                     Parquet + DuckDB lineage (storage.py)\n"
            "  -> health indicator                  health.py    (reference HI, per-bearing baseline)\n"
            "  -> degradation stage                 stages.py    (severity band on the HI)\n"
            "  -> RUL regression                    modeling.py  (ExtraTrees + naive baseline)\n"
            "  -> leakage-safe evaluation           evaluation.py (leave-one-bearing-out / walk-forward)\n"
            "  -> this dashboard                    dashboard.py (reads cached artifacts only)\n"
            "```"
        )
        st.markdown(
            "Everything above is batch and local. There is **no** backend service, HTTP API, "
            "database server, message queue, cloud component, or live sensor feed. The "
            "dashboard never fits a model - it reads Parquet, DuckDB and `artifacts/models/*.joblib` "
            "that the scripts produced earlier. No deep-learning model (LSTM/CNN/transformer) and "
            "no LLM or RAG layer is implemented in this repository."
        )
        if _cloud_mode():
            st.markdown(
                "**This deployment specifically:** it serves a tracked snapshot "
                "(`deploy_data/`, ~3.5 MB) of artifacts the pipeline produced offline - "
                "three of the six FEMTO learning bearings, twelve genuinely measured raw "
                "windows, the fitted health-indicator and naive models, and the evaluation "
                "JSONs. The ~104 MB fitted ExtraTrees forest exceeds GitHub's file limit and "
                "is not bundled, so the RUL view shows its leave-one-bearing-out prediction "
                "from the evaluation artifact instead. Nothing is trained, downloaded or "
                "measured while the page runs."
            )

        st.subheader("Non-claims (docs/prd.md)")
        st.markdown(
            "- No guaranteed physical root-cause diagnosis (stage != fault type)\n"
            "- No production safety certification\n"
            "- No cross-bearing validation from the single college run\n"
            "- No LLM-generated numeric prediction (RAG/LLM deferred to M7, not on this dashboard)\n"
            "- No uncertainty interval on the RUL point estimate yet\n"
        )
        st.subheader("Known limitations found during development (docs/decisions.md)")
        st.markdown(
            "- College's `rul_seconds` label uses the known final timestamp (uncensored run) - "
            "its naive baseline scores a trivial 0.0 MAE by construction (D10), not a real result.\n"
            "- College feature batch shown here is a representative sample, not the full 129-file run (section 26.8).\n"
            "- Per-acquisition HI monotonicity is low (~0.01-0.11) for every HI tried. "
            "|mean(sign(diff))| is near zero for any noisy real signal, so Spearman rank "
            "correlation and the healthy-vs-end-of-life separation are the headline metrics "
            "instead (D18).\n"
            "- FEMTO degradation is flat-then-cliff, not gradual: Bearing3_2's vibration_x_rms "
            "sits at ~0.30 for ~95% of life then jumps 6x inside the final ~17 acquisitions. "
            "A linear trend statistic understates an otherwise usable HI.\n"
            "- Bearing3_1 and Bearing3_2 have weak HI rank trends (-0.48, -0.18) for that "
            "reason. Their HI does reach failure territory, but only very late - Bearing3_1 "
            "gives 120 s of CRITICAL warning. That is a property of those bearings, not a "
            "tuning choice.\n"
            "- The reference HI assumes the bearing is healthy during acquisitions 10-59 of "
            "its own record. True by construction for PRONOSTIA and the college rig (both run "
            "to failure from new); it would not hold for a bearing instrumented mid-life.\n"
            "- The reference HI normalises each bearing against its own early life, which makes "
            "a college-specific HI feasible for the first time. Not yet fitted - the college "
            "gate on this dashboard still stands.\n"
        )


if __name__ == "__main__":
    main()
