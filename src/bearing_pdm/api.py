"""Read-only prediction service (Goal 1/4: separate the ML inference layer
from the frontend, see START_CAPSTONE_OVERNIGHT.md / goals.md).

Mirrors dashboard.py's artifact-loading contract exactly: this module never
calls .fit(), never trains, and never touches Full_Test_Set/Validation_Set.
It loads the same cached joblib artifacts the Streamlit dashboard reads and
serves them over HTTP so a separate frontend can consume them without
duplicating scientific logic in JS.

Domain gating (docs/decisions.md D11): every cached RUL/HI model here is fit
on FEMTO learning bearings. Applying it to college data produces values
outside the model's valid range, so /predict/rul refuses non-femto input
with 422 rather than silently returning a wrong number.
"""

from __future__ import annotations

import os
import tempfile
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from bearing_pdm.health import apply_reference_hi
from bearing_pdm.profiler import profile_file
from bearing_pdm.stages import assign_stages

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO_ROOT / "artifacts" / "models"

# Hard cap on an uploaded file this service will read, independent of profile_file's
# own sample_rows bound - python.md: "all raw reads are chunked", never a whole-file
# read of an arbitrary upload. 64MB is far more than the header + sample_rows need.
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024

FULLY_SUPPORTED = "FULLY_SUPPORTED"
ADAPTER_REQUIRED = "ADAPTER_REQUIRED"
UNSUPPORTED = "UNSUPPORTED"
INVALID_INPUT = "INVALID_INPUT"

_REQUIRED_ANY = {"vibration_x", "vibration_y", "vibration_z"}


def _classify(profile: dict) -> tuple[str, list[str]]:
    """Compatibility state for the uploaded file, from profile_file's output
    only - see goals.md's fail-closed dataset-state requirement. This is a
    column/header-level check; it does not run the trained applicability
    model in applicability.py (that needs parsed recordings from a known
    adapter, not an arbitrary upload) - see docs/dataset-compatibility.md."""
    if not profile.get("readable"):
        return INVALID_INPUT, profile.get("warnings", ["file could not be read"])

    columns = profile.get("columns", [])
    if not profile.get("has_header"):
        return ADAPTER_REQUIRED, [
            "no header row: column meanings cannot be inferred from names; "
            "a dataset adapter (see src/bearing_pdm/adapters.py) is required"
        ]

    vibration_cols = [c for c in columns if c["canonical"] in _REQUIRED_ANY]
    if not vibration_cols:
        return UNSUPPORTED, [
            "no vibration channel recognised in the header "
            f"(saw: {[c['name'] for c in columns]})"
        ]
    if any(c["confidence"] == "low" for c in vibration_cols):
        return ADAPTER_REQUIRED, [
            f"vibration channel(s) matched only by a low-confidence name guess: "
            f"{[c['name'] for c in vibration_cols if c['confidence'] == 'low']} - confirm before use"
        ]

    # Column-name mapping alone is fail-open: a column named vibration_x that is
    # non-numeric, empty, constant, or mostly missing is still "mapped" by name
    # but unusable as a signal - profile_file already flags exactly this.
    if profile.get("rows", 0) == 0:
        return INVALID_INPUT, ["file has a header but no data rows"]
    usable = [
        c for c in vibration_cols
        if c["numeric"] and not c["constant"] and c["nan_fraction"] <= 0.5 and c["inf_count"] == 0
    ]
    if not usable:
        return INVALID_INPUT, [
            f"{c['name']}: "
            + ("non-numeric values" if not c["numeric"]
               else "constant in the sampled rows" if c["constant"]
               else f"{c['inf_count']} infinite values" if c["inf_count"]
               else f"{c['nan_fraction']:.0%} missing")
            for c in vibration_cols
        ]
    return FULLY_SUPPORTED, []


class DatasetProfileResponse(BaseModel):
    compatibility: str
    reasons: list[str]
    profile: dict[str, Any]

# Frontend origin(s) allowed to call this API, e.g. "https://rulguard.vercel.app,http://localhost:3000".
# No default beyond localhost dev - a production origin must be set explicitly, never wildcarded.
_ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

app = FastAPI(
    title="RULGuard prediction service",
    description="Read-only inference over cached bearing_pdm artifacts. Never fits a model.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

_MODEL_CACHE: dict[str, Any] = {}

# In-process prediction history (goals.md: "add prediction history and result
# tracking"). Deliberately NOT a database: this is an in-memory ring buffer
# that resets on restart and is NOT shared across a serverless deployment's
# concurrent/cold-started instances - a real deployment needs a persistent
# store (Vercel Postgres/KV, etc.), which needs credentials this environment
# doesn't have. Documented as a known limitation, not claimed as durable.
_HISTORY_LIMIT = 200
_prediction_history: deque[dict[str, Any]] = deque(maxlen=_HISTORY_LIMIT)


def _record_history(kind: str, request_summary: dict[str, Any], result_summary: dict[str, Any]) -> None:
    _prediction_history.append({
        "timestamp": datetime.now(UTC).isoformat(),
        "kind": kind,
        "request": request_summary,
        "result": result_summary,
    })


def _load_joblib(name: str) -> Any | None:
    """Same missing-artifact contract as dashboard._load_joblib: None, never
    a traceback, cached in-process rather than per-request."""
    if name in _MODEL_CACHE:
        return _MODEL_CACHE[name]
    path = MODELS_DIR / name
    if not path.exists():
        return None
    model = joblib.load(path)
    _MODEL_CACHE[name] = model
    return model


class PredictRulRequest(BaseModel):
    dataset_id: str = Field(..., description="Must be 'femto' - see docs/decisions.md D11.")
    features: dict[str, float] = Field(
        ..., description="Feature-row values keyed by column name, matching model.feature_columns."
    )


class PredictRulResponse(BaseModel):
    model_name: str
    rul_seconds: float
    rul_hours: float
    features_used: list[str]
    features_missing: list[str]


@app.get("/health")
def health() -> dict[str, Any]:
    tree_model = _load_joblib("rul_extra_trees.joblib")
    naive_model = _load_joblib("rul_naive.joblib")
    return {
        "status": "ok",
        "models_loaded": {
            "rul_extra_trees": tree_model is not None,
            "rul_naive": naive_model is not None,
        },
    }


@app.get("/models/info")
def models_info() -> dict[str, Any]:
    selected_path = MODELS_DIR / "rul_selected_model.json"
    selected = None
    if selected_path.exists():
        import json

        selected = json.loads(selected_path.read_text())
    tree_model = _load_joblib("rul_extra_trees.joblib")
    hi_model = _load_joblib("reference_hi_model.joblib")
    return {
        "selected_model": selected,
        "extra_trees_feature_columns": (
            list(tree_model.feature_columns) if tree_model is not None else None
        ),
        "hi_feature_columns": list(hi_model.features) if hi_model is not None else None,
        "supported_datasets": ["femto"],
        "note": (
            "college and other adapters are not gated in behind a compatible model here - "
            "see docs/decisions.md D11 and dashboard.py's domain gate."
        ),
    }


@app.post("/predict/rul", response_model=PredictRulResponse)
def predict_rul(request: PredictRulRequest) -> PredictRulResponse:
    if request.dataset_id != "femto":
        raise HTTPException(
            status_code=422,
            detail=(
                f"dataset_id={request.dataset_id!r} is not supported for RUL prediction. "
                "Every cached model is fit on FEMTO learning bearings only "
                "(docs/decisions.md D11); applying it elsewhere would fabricate a result."
            ),
        )

    model = _load_joblib("rul_extra_trees.joblib")
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="rul_extra_trees.joblib is missing. Run scripts/train_models.py first.",
        )

    missing = [c for c in model.feature_columns if c not in request.features]
    max_missing_fraction = 0.5  # below this, too few real measurements to trust the prediction
    if len(missing) / len(model.feature_columns) > max_missing_fraction:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{len(missing)}/{len(model.feature_columns)} required features are missing "
                f"(max allowed {max_missing_fraction:.0%}). A prediction built mostly from "
                "training medians would not reflect the submitted sample."
            ),
        )

    row = {
        c: request.features.get(c, model.median_fill.get(c))
        for c in model.feature_columns
    }
    if any(v is None for v in row.values()):
        unresolvable = [c for c, v in row.items() if v is None]
        raise HTTPException(
            status_code=422,
            detail=f"Missing required features with no fallback median: {unresolvable}",
        )

    import pandas as pd

    x = pd.DataFrame([row])[list(model.feature_columns)]
    prediction = float(model.model.predict(x)[0])

    response = PredictRulResponse(
        model_name="extra_trees",
        rul_seconds=prediction,
        rul_hours=prediction / 3600.0,
        features_used=list(model.feature_columns),
        features_missing=missing,
    )
    _record_history(
        "predict_rul",
        {"dataset_id": request.dataset_id, "n_features_provided": len(request.features)},
        {"rul_hours": response.rul_hours, "n_features_missing": len(missing)},
    )
    return response


class HiRequest(BaseModel):
    dataset_id: str = Field(..., description="Must be 'femto' - see docs/decisions.md D11.")
    rows: list[dict[str, float]] = Field(
        ...,
        min_length=1,
        description=(
            "Feature rows for ONE bearing run, in acquisition order. Each row must include "
            "sequence_index plus the reference HI model's feature columns "
            "(see GET /models/info's hi_feature_columns)."
        ),
    )


class HiRow(BaseModel):
    sequence_index: int
    health_indicator: float
    stage: str


class HiResponse(BaseModel):
    rows: list[HiRow]
    hi_warn_threshold: float
    hi_critical_threshold: float
    note: str = (
        "Stage is a severity band on the health indicator, not a physical fault-type "
        "diagnosis (no inner/outer-race/ball/cage claim)."
    )


@app.post("/predict/hi", response_model=HiResponse)
def predict_hi(request: HiRequest) -> HiResponse:
    """Mirrors dashboard.py's Health Indicator tab exactly: same
    apply_reference_hi/assign_stages calls, same FEMTO-only domain gate
    (D11 - a FEMTO-fit reference HI applied to college's feature scale is
    out-of-domain, confirmed in dashboard.py's own history to swing outside
    the HI's valid (0,1) range)."""
    if request.dataset_id != "femto":
        raise HTTPException(
            status_code=422,
            detail=(
                f"dataset_id={request.dataset_id!r} is not supported for HI prediction. "
                "The cached reference HI model is fit on FEMTO learning bearings only "
                "(docs/decisions.md D11)."
            ),
        )

    reference_model = _load_joblib("reference_hi_model.joblib")
    thresholds = _load_joblib("stage_thresholds.joblib")
    if reference_model is None or thresholds is None:
        raise HTTPException(
            status_code=503,
            detail="HI artifacts missing. Run scripts/build_health.py first.",
        )

    missing = [c for c in reference_model.features if any(c not in row for row in request.rows)]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Every row must include all HI feature columns. Missing from at least one row: {missing}",
        )

    # apply_reference_hi normalises each row against THIS run's own leading
    # (reference_skip, reference_n) window, assuming that window is healthy.
    # A run shorter than that window still "runs" (pandas doesn't error), but
    # the reference and the scored rows overlap, so every row - degraded or
    # not - is normalised against itself and comes back healthy. That's the
    # goals.md fail-open case reported in review: a 5-row or 60-row-all-bad
    # upload silently returned HEALTHY for every row. Refuse instead.
    min_rows = reference_model.reference_skip + reference_model.reference_n
    if len(request.rows) < min_rows:
        raise HTTPException(
            status_code=422,
            detail=(
                f"At least {min_rows} rows are required (the model's reference window: "
                f"reference_skip={reference_model.reference_skip} + "
                f"reference_n={reference_model.reference_n}) so the healthy-baseline rows "
                "and the rows being scored don't overlap. Got "
                f"{len(request.rows)}."
            ),
        )

    import numpy as np
    import pandas as pd

    feature_cols = list(reference_model.features)
    non_finite = [
        c for c in feature_cols
        if any(not np.isfinite(row[c]) for row in request.rows)
    ]
    if non_finite:
        raise HTTPException(
            status_code=422,
            detail=f"Non-finite (NaN/inf) feature values are not allowed: {non_finite}",
        )

    df = pd.DataFrame(request.rows)
    df["bearing_run_id"] = "uploaded_run"  # single synthetic run - only grouping key these functions need
    df = df.sort_values("sequence_index").reset_index(drop=True)

    # apply_reference_hi assumes the reference window (see health.py's
    # _per_bearing_reference) is a genuine healthy baseline. A window that is
    # exactly constant across every feature isn't evidence of health - it's
    # degenerate input (a stuck sensor, a synthetic/placeholder upload) that
    # the model cannot distinguish from "healthy," and it was silently scored
    # as HEALTHY in review (a run of 60+ constant rows). Reject instead of
    # guessing.
    skip, n_ref = reference_model.reference_skip, reference_model.reference_n
    window = df.iloc[skip:skip + n_ref]
    if all(window[c].nunique() <= 1 for c in feature_cols):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Rows {skip}-{skip + n_ref - 1} (the reference window) are constant across "
                "every feature. The model normalises against this window as the healthy "
                "baseline; a constant window carries no evidence of actual healthy "
                "variation and cannot be scored meaningfully."
            ),
        )

    hi = apply_reference_hi(df, reference_model)
    stage = assign_stages(df, hi, thresholds)

    response = HiResponse(
        rows=[
            HiRow(sequence_index=int(seq), health_indicator=float(h), stage=str(s))
            for seq, h, s in zip(df["sequence_index"], hi, stage)
        ],
        hi_warn_threshold=float(thresholds.hi_warn),
        hi_critical_threshold=float(thresholds.hi_critical),
    )
    _record_history(
        "predict_hi",
        {"dataset_id": request.dataset_id, "n_rows": len(request.rows)},
        {"latest_hi": response.rows[-1].health_indicator, "latest_stage": response.rows[-1].stage},
    )
    return response


@app.get("/predictions/history")
def prediction_history() -> dict[str, Any]:
    """Most recent predictions this process has served, newest first.
    In-memory only - see the module-level note on _prediction_history for why
    this is not a durable store."""
    return {
        "count": len(_prediction_history),
        "limit": _HISTORY_LIMIT,
        "predictions": list(reversed(_prediction_history)),
    }


@app.post("/dataset/inspect", response_model=DatasetProfileResponse)
async def inspect_dataset(file: UploadFile) -> DatasetProfileResponse:
    """Upload -> inspect -> classify (goals.md's dataset-detection step), before
    anything is validated/preprocessed/fed to a model. Column-mapping only -
    see docs/dataset-compatibility.md for what this does and does not check."""
    with tempfile.NamedTemporaryFile(suffix=Path(file.filename or "upload").suffix) as tmp:
        written = 0
        while chunk := await file.read(UPLOAD_CHUNK_BYTES):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB inspection limit.",
                )
            tmp.write(chunk)
        tmp.flush()

        if written == 0:
            raise HTTPException(status_code=422, detail="Uploaded file is empty.")

        profile = profile_file(tmp.name)
        profile["file"] = file.filename or profile["file"]  # real name, not the temp path

    compatibility, reasons = _classify(profile)
    return DatasetProfileResponse(compatibility=compatibility, reasons=reasons, profile=profile)


# Vercel's Python runtime forwards the original request path (e.g. /api/health)
# to this function unchanged - it does not strip the /api prefix the way a
# typical reverse-proxy rewrite would. Mounting the unprefixed `app` under /api
# in a separate wrapper keeps local dev (`uvicorn bearing_pdm.api:app`, routes
# at /health) and the test suite (imports `app` directly) on unprefixed paths,
# while api/index.py imports `vercel_app` for the actual deployed function.
vercel_app = FastAPI()
vercel_app.mount("/api", app)
