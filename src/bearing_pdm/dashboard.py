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
from bearing_pdm.config import load_data_paths
from bearing_pdm.femto import read_acceleration, read_temperature
from bearing_pdm.health import apply_pca_hi, apply_transparent_hi
from bearing_pdm.modeling import predict_naive_baseline, predict_tree_baseline
from bearing_pdm.storage import get_connection

CONFIG_PATH = "config/data_paths.toml"


@st.cache_resource
def _load_paths():
    return load_data_paths(CONFIG_PATH)


@st.cache_data
def _list_batches() -> pd.DataFrame:
    paths = _load_paths()
    con = get_connection(paths.duckdb_path)
    try:
        return con.execute(
            "SELECT dataset_id, feature_batch_id, parquet_path, row_count, code_version, created_at "
            "FROM feature_batches ORDER BY created_at DESC"
        ).fetchdf()
    finally:
        con.close()


@st.cache_data
def _load_batch(parquet_path: str) -> pd.DataFrame:
    return pd.read_parquet(parquet_path)


@st.cache_resource
def _load_joblib(path: str):
    import joblib
    p = Path(path)
    if not p.exists():
        return None
    return joblib.load(p)


def _load_raw_femto_row(row: pd.Series) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    bearing_dir = Path(row["source_file_path"]).parent
    acc_index = int(Path(row["source_file_path"]).stem.split("_")[1])
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
        row["source_file_path"], header=None, names=COLLEGE_COLUMNS, skiprows=skiprows, nrows=nrows,
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

    batches = _list_batches()
    if batches.empty:
        st.error("No feature batches found. Run scripts/build_features.py first.")
        return

    dataset_id = st.sidebar.selectbox("Dataset", sorted(batches["dataset_id"].unique()))
    batch_row = batches[batches["dataset_id"] == dataset_id].iloc[0]
    st.sidebar.caption(
        f"batch {batch_row['feature_batch_id'][:8]}... | {batch_row['row_count']} rows | "
        f"code {batch_row['code_version']} | {batch_row['created_at']}"
    )
    if dataset_id == "college":
        st.sidebar.info("College batch is a representative sample (command.md section 26.8), not the full 129-file run - see docs/decisions.md.")

    df = _load_batch(batch_row["parquet_path"])
    bearing_run_id = st.sidebar.selectbox("Bearing / run", sorted(df["bearing_run_id"].unique()))
    df_bearing = df[df["bearing_run_id"] == bearing_run_id].sort_values("sequence_index").reset_index(drop=True)

    idx = st.sidebar.slider("Acquisition / window index", 0, len(df_bearing) - 1, 0)
    row = df_bearing.iloc[idx]

    tab_signal, tab_health, tab_rul, tab_metrics, tab_limits = st.tabs(
        ["Signal & FFT", "Health Indicator", "RUL Prediction", "Model Evaluation", "Architecture & Limitations"]
    )

    with tab_signal:
        st.subheader(f"Row {idx}/{len(df_bearing)-1} - {row['source_file_path']}")
        try:
            if dataset_id == "femto":
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

    with tab_health:
        if dataset_id != "femto":
            st.info(
                "The cached HI models (artifacts/models/*_hi_*.joblib) were fit only on FEMTO learning "
                "bearings (scripts/build_health.py). Applying a FEMTO-fit scaler/PCA to college's very "
                "different feature scale is out-of-domain and produces meaningless values (confirmed while "
                "building this dashboard - PCA HI swung below -3 on college data). Not shown for college in "
                "this MVP; a college-specific HI would need its own fit, deferred (docs/decisions.md)."
            )
        else:
            baseline = _load_joblib("artifacts/models/transparent_hi_baseline.joblib")
            pca_model = _load_joblib("artifacts/models/pca_hi_model.joblib")
            if baseline is None:
                st.warning("No fitted HI baseline found - run scripts/build_health.py.")
            else:
                hi_t = apply_transparent_hi(df_bearing, baseline)
                chart_data = {"transparent_hi": hi_t}
                if pca_model is not None:
                    chart_data["pca_hi"] = apply_pca_hi(df_bearing, pca_model)
                st.line_chart(pd.DataFrame(chart_data, index=df_bearing["sequence_index"]))
                st.metric("Current transparent HI", f"{hi_t.iloc[idx]:.3f}", help="1.0=healthy, ->0 as degradation progresses")

    with tab_rul:
        if dataset_id != "femto":
            st.info(
                "The cached RUL models (artifacts/models/rul_*.joblib) were fit only on FEMTO learning "
                "bearings (scripts/train_models.py) - same out-of-domain concern as the Health Indicator tab. "
                "College's real RUL evidence is the walk-forward evaluation in the Model Evaluation tab, "
                "which fits fresh models inside each fold on college's own data (src/bearing_pdm/evaluation.py)."
            )
        else:
            naive_model = _load_joblib("artifacts/models/rul_naive.joblib")
            tree_model = _load_joblib("artifacts/models/rul_extra_trees.joblib")
            selected_path = Path("artifacts/models/rul_selected_model.json")
            selected = json.loads(selected_path.read_text())["selected"] if selected_path.exists() else "extra_trees"

            col1, col2, col3 = st.columns(3)
            if tree_model is not None:
                pred_tree = predict_tree_baseline(df_bearing.iloc[[idx]], tree_model).iloc[0]
                col1.metric(f"ExtraTrees prediction {'(selected)' if selected == 'extra_trees' else ''}", f"{pred_tree/3600:.2f} h")
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
            )

    with tab_metrics:
        for label, path in [
            ("RUL evaluation (leave-one-bearing-out / walk-forward)", "reports/metrics/rul_evaluation.json"),
            ("Health indicator comparison", "reports/metrics/health_indicator_comparison.json"),
        ]:
            st.subheader(label)
            p = Path(path)
            if p.exists():
                st.json(json.loads(p.read_text()))
            else:
                st.info(f"{path} not found - run the corresponding script first.")

    with tab_limits:
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
            "- Per-acquisition HI monotonicity is low (~0.01-0.02); trend correlation is the more meaningful signal.\n"
        )


if __name__ == "__main__":
    main()
