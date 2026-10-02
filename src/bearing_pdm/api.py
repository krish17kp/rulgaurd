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

import logging
import os
import tempfile
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from bearing_pdm.features import frequency_domain_features, time_domain_features
from bearing_pdm.femto import ACC_COLUMNS
from bearing_pdm.health import apply_reference_hi
from bearing_pdm.profiler import profile_file
from bearing_pdm.stages import assign_stages

# FEMTO's acc_*.csv is a fixed, headerless, positional 6-column layout at a
# known sampling rate (femto.py's own docstring) - this is a *known adapter*
# the user is explicitly asserting applies (dataset_id="femto"), not a guess
# from column names the way /dataset/inspect works. ml-data.md: never guess
# sampling frequency - this one is a documented constant of a named format,
# not inferred from the upload.
FEMTO_SAMPLE_RATE_HZ = 25600.0
# A real acquisition is "usually 2560 rows" (femto.py docstring); this floor
# is deliberately far below that - just enough that frequency_domain_features
# isn't degenerate (x.size<2) and a handful of rows can't be mistaken for a
# real vibration window, not a claim about the true per-file row count.
MIN_FEMTO_ACQUISITION_ROWS = 256

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO_ROOT / "artifacts" / "models"
METRICS_DIR = REPO_ROOT / "reports" / "metrics"

# Hard cap on an uploaded file this service will read, independent of profile_file's
# own sample_rows bound - python.md: "all raw reads are chunked", never a whole-file
# read of an arbitrary upload. 64MB is far more than the header + sample_rows need.
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024

FULLY_SUPPORTED = "FULLY_SUPPORTED"
ADAPTER_REQUIRED = "ADAPTER_REQUIRED"
RETRAIN_REQUIRED = "RETRAIN_REQUIRED"
UNSUPPORTED = "UNSUPPORTED"
INVALID_INPUT = "INVALID_INPUT"

_REQUIRED_ANY = {"vibration_x", "vibration_y", "vibration_z"}

# The only sampling rate any currently trained model was fit at (FEMTO,
# FEMTO_SAMPLE_RATE_HZ above). A file whose rate is known but doesn't match
# this is structurally usable, just not covered by an existing model -
# RETRAIN_REQUIRED, not ADAPTER_REQUIRED (that's for format/column problems).
_KNOWN_MODEL_SAMPLE_RATES_HZ = {"femto": FEMTO_SAMPLE_RATE_HZ}
_SAMPLE_RATE_TOLERANCE = 0.01  # 1% - real hardware clocks drift slightly


def _derive_sampling_rate_hz(path: Path, profile: dict) -> tuple[float | None, str | None]:
    """From evidence only, matching profiler._sampling_rate's own rule for a
    multi-file folder profile: a timestamp column's median step. Never
    assumed from the file format or row count."""
    time_cols = [c for c in profile.get("columns", []) if c["canonical"] == "timestamp"]
    if not time_cols or profile.get("rows", 0) < 2:
        return None, None
    delimiter = profile.get("delimiter")
    sep = r"\s+" if delimiter in (None, "whitespace") else delimiter
    try:
        df = pd.read_csv(path, sep=sep, nrows=2000)
    except (pd.errors.ParserError, ValueError):
        return None, None
    step = np.median(np.diff(pd.to_numeric(df[time_cols[0]["name"]], errors="coerce")))
    if np.isfinite(step) and step > 0:
        return float(1.0 / step), f"timestamp column '{time_cols[0]['name']}'"
    return None, None


def _classify(
    profile: dict,
    path: Path | None = None,
    declared_sampling_rate_hz: float | None = None,
    declared_units: str | None = None,
) -> tuple[str, list[str]]:
    """Compatibility state for the uploaded file, from profile_file's output
    plus (for the sampling-rate/units steps only) the caller's own
    declaration or a timestamp column already in the file - never guessed.
    This is a column/header-level check; it does not run the trained
    applicability model in applicability.py (that needs parsed recordings
    from a known adapter, not an arbitrary upload) - see
    docs/dataset-compatibility.md."""
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

    # Everything above is structural (can the columns be read at all). Below
    # is the scientific question ml-data.md requires: is this file's sampling
    # rate/units known, and if so, does any trained model actually cover it?
    # Neither is ever inferred from the data's shape or scale - only from a
    # real timestamp column already in the file, or the caller's own
    # declaration.
    declared_units = declared_units.strip() if declared_units else declared_units

    derived_rate, derived_source = _derive_sampling_rate_hz(path, profile) if path else (None, None)
    # Real evidence (a timestamp column already in the file) always wins over
    # a declaration - a declared rate is only a fallback for when there is no
    # such evidence, never a way to override it (found in review: declaring a
    # rate that contradicted the file's own timestamps silently produced
    # FULLY_SUPPORTED, exactly the guess ml-data.md forbids).
    if derived_rate is not None:
        sampling_rate_hz, rate_source = derived_rate, derived_source
        if (
            declared_sampling_rate_hz is not None
            and abs(declared_sampling_rate_hz - derived_rate) > _SAMPLE_RATE_TOLERANCE * derived_rate
        ):
            return ADAPTER_REQUIRED, [
                f"declared_sampling_rate_hz={declared_sampling_rate_hz:.1f} conflicts with the rate "
                f"derived from the file's own {derived_source} ({derived_rate:.1f} Hz) - the file's "
                "own evidence is used, not the declaration; fix the declaration or the file"
            ]
    else:
        sampling_rate_hz, rate_source = declared_sampling_rate_hz, "declared_sampling_rate_hz"

    missing_metadata = []
    if sampling_rate_hz is None:
        missing_metadata.append(
            "sampling rate unknown: no usable timestamp column (none found, or its values "
            "could not be read as a numeric, varying time series) and no declared_sampling_rate_hz "
            "- frequency-domain features cannot be computed without it"
        )
    if not declared_units:
        missing_metadata.append(
            "units not declared (declared_units) - this project keeps no verified units "
            "contract to check a declaration against, but requires one for traceability "
            "before a prediction is made"
        )
    if missing_metadata:
        return ADAPTER_REQUIRED, missing_metadata

    for model_id, model_rate_hz in _KNOWN_MODEL_SAMPLE_RATES_HZ.items():
        if abs(sampling_rate_hz - model_rate_hz) <= _SAMPLE_RATE_TOLERANCE * model_rate_hz:
            return FULLY_SUPPORTED, [
                f"sampling rate {sampling_rate_hz:.1f} Hz (source: {rate_source}) matches the "
                f"{model_id} model's trained rate ({model_rate_hz:.1f} Hz)"
            ]
    return RETRAIN_REQUIRED, [
        f"sampling rate {sampling_rate_hz:.1f} Hz (source: {rate_source}) does not match any "
        f"trained model's domain ({', '.join(f'{k}: {v:.1f} Hz' for k, v in _KNOWN_MODEL_SAMPLE_RATES_HZ.items())}). "
        "The vibration channel(s) and metadata are structurally usable, but no existing model "
        "was fit at this rate - this machine/configuration would need a model trained for it, "
        "not just a parsing adapter."
    ]


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

# Structured logging (goals.md: "monitoring and logging for prediction
# requests, failures, and deployment issues"). Plain stdlib logging to
# stdout/stderr - Vercel's Python runtime and any container platform capture
# that automatically, so this needs no new service or credential. Never logs
# request bodies (feature vectors, uploaded filenames go elsewhere) - only
# method, path, status, latency, and a request id for correlation.
logger = logging.getLogger("bearing_pdm.api")
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))


# Reject an oversized body from its declared Content-Length before Starlette
# buffers it into a spooled temp file - review noted the previous approach
# (checking cumulative bytes read inside /dataset/inspect) only limits what's
# processed, not what's received. A small margin over MAX_UPLOAD_BYTES covers
# multipart boundary/header overhead for a file right at the limit.
_MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 2 * 1024 * 1024


@app.middleware("http")
async def _log_requests(request: Request, call_next):
    # Only catches a request that declares its size via Content-Length. A
    # chunked request with no Content-Length isn't covered here - it still
    # relies on /dataset/inspect's own chunked-read loop (MAX_UPLOAD_BYTES)
    # to reject an oversized body after the fact, same as before this check.
    content_length = request.headers.get("content-length")
    if (
        content_length is not None
        and content_length.isdigit()
        and int(content_length) > _MAX_REQUEST_BYTES
    ):
        return JSONResponse(
            status_code=413,
            content={"detail": f"Request body exceeds {_MAX_REQUEST_BYTES // (1024 * 1024)}MB."},
        )

    request_id = uuid.uuid4().hex[:12]
    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_id=%s method=%s path=%s status=500 (unhandled exception)",
            request_id, request.method, request.url.path,
        )
        raise
    duration_ms = (time.monotonic() - start) * 1000
    log = logger.warning if response.status_code >= 500 else logger.info
    log(
        "request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
        request_id, request.method, request.url.path, response.status_code, duration_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response

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


@app.get("/models/evaluation")
def models_evaluation() -> dict[str, Any]:
    """Real leave-one-bearing-out (FEMTO) and walk-forward (college) numbers,
    read verbatim from reports/metrics/rul_evaluation.json - goals.md's
    "provide confidence/validation/reliability information" requirement,
    without hand-typing a metric (general.md: every number traces to a
    generated file).

    ml-data.md D10 is non-negotiable: college's naive baseline scores
    MAE=0.0 by construction (it has access to the true total run length),
    not because it predicts well. college_naive_caveat is returned alongside
    the college numbers specifically so a client cannot show the college
    naive/extra_trees comparison without also carrying that caveat - it must
    never be presented as a fair comparison."""
    path = METRICS_DIR / "rul_evaluation.json"
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail="reports/metrics/rul_evaluation.json missing. Run scripts/evaluate_models.py first.",
        )
    import json

    return json.loads(path.read_text())


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


def _predict_rul_from_features(features: dict[str, float]) -> PredictRulResponse:
    """Shared by /predict/rul (caller supplies a pre-extracted feature row)
    and /predict/rul/femto-acquisition (feature row extracted here from a raw
    upload) - one feature-contract/missing-value/inference path, not two."""
    model = _load_joblib("rul_extra_trees.joblib")
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="rul_extra_trees.joblib is missing. Run scripts/train_models.py first.",
        )

    # A present-but-non-finite value (features.py returns NaN by design for a
    # zero-variance/degenerate signal, see frequency_domain_features) is not a
    # real measurement either - treating it as "present" let it bypass both
    # the median-fill below and the missing-fraction gate, reaching the model
    # with a NaN feature instead of the training median (found in review:
    # produced a materially different RUL than modeling.predict_tree_baseline
    # on the same input). Fold it into "missing" so both paths see it.
    missing = [
        c for c in model.feature_columns
        if c not in features or not np.isfinite(features[c])
    ]
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
        c: features[c] if c not in missing else model.median_fill.get(c)
        for c in model.feature_columns
    }
    if any(v is None for v in row.values()):
        unresolvable = [c for c, v in row.items() if v is None]
        raise HTTPException(
            status_code=422,
            detail=f"Missing required features with no fallback median: {unresolvable}",
        )

    x = pd.DataFrame([row])[list(model.feature_columns)]
    try:
        prediction = float(model.model.predict(x)[0])
    except ValueError as exc:
        # Extreme-but-finite input (e.g. 1e300 raw samples) can still overflow
        # a derived feature like RMS to inf despite passing the raw-value
        # isfinite check upstream. Fail closed with 422, not a raw 500.
        raise HTTPException(
            status_code=422,
            detail=f"Feature values are unusable for prediction: {exc}",
        ) from None

    return PredictRulResponse(
        model_name="extra_trees",
        rul_seconds=prediction,
        rul_hours=prediction / 3600.0,
        features_used=list(model.feature_columns),
        features_missing=missing,
    )


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

    response = _predict_rul_from_features(request.features)
    _record_history(
        "predict_rul",
        {"dataset_id": request.dataset_id, "n_features_provided": len(request.features)},
        {"rul_hours": response.rul_hours, "n_features_missing": len(response.features_missing)},
    )
    return response


def _extract_femto_acquisition_features(path: str) -> dict[str, float]:
    """Exactly the extraction tests/test_api_e2e.py proves matches the
    trained model's feature contract: time- and frequency-domain features
    per axis from the real functions in features.py, nothing reimplemented."""
    df = pd.read_csv(path, header=None, names=ACC_COLUMNS, dtype="float64")
    features: dict[str, float] = {}
    for axis, column in (("x", "accel_horizontal"), ("y", "accel_vertical")):
        signal = df[column].to_numpy()
        features.update(time_domain_features(signal, f"vibration_{axis}"))
    for axis, column in (("x", "accel_horizontal"), ("y", "accel_vertical")):
        signal = df[column].to_numpy()
        features.update(frequency_domain_features(signal, FEMTO_SAMPLE_RATE_HZ, f"vibration_{axis}"))
    return features


@app.post("/predict/rul/femto-acquisition", response_model=PredictRulResponse)
async def predict_rul_from_femto_acquisition(file: UploadFile) -> PredictRulResponse:
    """Raw single-acquisition FEMTO acc_*.csv -> features.py -> /predict/rul,
    over one HTTP call (goals.md: "automatically extract the required
    features" / "automatically run the correct trained prediction pipeline").

    Only the FEMTO acc format (docs/decisions.md D11, femto.py) is accepted
    here - the caller is asserting a known, fixed, headerless 6-column layout
    at a known sampling rate, not asking this endpoint to guess one from an
    arbitrary upload (that guess belongs to /dataset/inspect, and it correctly
    refuses to guess). A dataset_id parameter isn't needed: this route's
    entire contract already *is* "this is a femto acquisition."
    """
    with tempfile.NamedTemporaryFile(suffix=".csv") as tmp:
        written = 0
        while chunk := await file.read(UPLOAD_CHUNK_BYTES):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit.",
                )
            tmp.write(chunk)
        tmp.flush()

        if written == 0:
            raise HTTPException(status_code=422, detail="Uploaded file is empty.")

        try:
            raw = pd.read_csv(tmp.name, header=None, dtype="float64")
        except (ValueError, pd.errors.ParserError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Not a numeric, headerless FEMTO acc_*.csv file: {exc}",
            ) from None

        if raw.shape[1] != len(ACC_COLUMNS):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Expected {len(ACC_COLUMNS)} columns (FEMTO's fixed acc_*.csv layout: "
                    f"{ACC_COLUMNS}), got {raw.shape[1]}. This is not a FEMTO acquisition file."
                ),
            )
        if raw.shape[0] < MIN_FEMTO_ACQUISITION_ROWS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Only {raw.shape[0]} rows - at least {MIN_FEMTO_ACQUISITION_ROWS} are required "
                    "for a meaningful vibration window (a real FEMTO acquisition is usually ~2560)."
                ),
            )
        if not np.isfinite(raw[[4, 5]].to_numpy()).all():
            raise HTTPException(
                status_code=422,
                detail="Non-finite (NaN/inf) values in the vibration columns are not allowed.",
            )

        try:
            features = _extract_femto_acquisition_features(tmp.name)
        except OverflowError as exc:
            # Finite but extreme raw samples (e.g. a huge-amplitude signal)
            # can overflow a derived statistic (std**4 etc.) before any
            # feature value is even produced to check for non-finiteness -
            # found in review. Fail closed with 422, not a raw 500.
            raise HTTPException(
                status_code=422,
                detail=f"Raw sample values are too extreme to extract features from: {exc}",
            ) from None

    response = _predict_rul_from_features(features)
    _record_history(
        "predict_rul_femto_acquisition",
        {"filename": file.filename, "n_rows": int(raw.shape[0])},
        {"rul_hours": response.rul_hours, "n_features_missing": len(response.features_missing)},
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
    # _per_bearing_reference) is a genuine healthy baseline. A window with no
    # real variation isn't evidence of health - it's degenerate input (a
    # stuck sensor, float jitter, a synthetic/placeholder upload) that the
    # model cannot distinguish from "healthy." An earlier version of this
    # check used exact nunique()<=1, which review defeated with a 1e-7
    # perturbation (still scored 100% HEALTHY). Compare each feature's window
    # spread against reference_model.scales - the same robust per-feature
    # spread fitted from real training bearings - so "no real variation"
    # means "negligible relative to the variation this model was calibrated
    # on," not "not bit-for-bit identical." Also require more than one
    # feature to show real variation: a single genuinely-varying sensor
    # alongside seven stuck ones is not credible evidence of a real healthy
    # reference either.
    skip, n_ref = reference_model.reference_skip, reference_model.reference_n
    window = df.iloc[skip:skip + n_ref]
    degenerate_tolerance = 0.01  # window std must be >=1% of the model's fitted spread
    varying = [
        c for c in feature_cols
        if reference_model.scales.get(c, 0) > 0
        and float(window[c].std()) >= degenerate_tolerance * reference_model.scales[c]
    ]
    if len(varying) < 2:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Rows {skip}-{skip + n_ref - 1} (the reference window) show negligible "
                f"variation relative to this model's training scale in all but {len(varying)} "
                "feature(s). The model normalises against this window as the healthy "
                "baseline; a window this flat carries no evidence of actual healthy "
                "variation (e.g. a stuck sensor) and cannot be scored meaningfully."
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
async def inspect_dataset(
    file: UploadFile,
    declared_sampling_rate_hz: float | None = Form(None),
    declared_units: str | None = Form(None),
) -> DatasetProfileResponse:
    """Upload -> inspect -> classify (goals.md's dataset-detection step), before
    anything is validated/preprocessed/fed to a model. Column-mapping only -
    see docs/dataset-compatibility.md for what this does and does not check.

    declared_sampling_rate_hz/declared_units are the caller's own assertion,
    used only when the file carries no timestamp column to derive a rate from
    - never a guess this endpoint makes itself (ml-data.md)."""
    if declared_sampling_rate_hz is not None and not (
        np.isfinite(declared_sampling_rate_hz) and declared_sampling_rate_hz > 0
    ):
        raise HTTPException(
            status_code=422,
            detail=f"declared_sampling_rate_hz must be a finite positive number, got {declared_sampling_rate_hz!r}.",
        )

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

        compatibility, reasons = _classify(
            profile,
            path=Path(tmp.name),
            declared_sampling_rate_hz=declared_sampling_rate_hz,
            declared_units=declared_units,
        )

    return DatasetProfileResponse(compatibility=compatibility, reasons=reasons, profile=profile)


# Vercel's Python runtime forwards the original request path (e.g. /api/health)
# to this function unchanged - it does not strip the /api prefix the way a
# typical reverse-proxy rewrite would. Mounting the unprefixed `app` under /api
# in a separate wrapper keeps local dev (`uvicorn bearing_pdm.api:app`, routes
# at /health) and the test suite (imports `app` directly) on unprefixed paths,
# while api/index.py imports `vercel_app` for the actual deployed function.
vercel_app = FastAPI()
vercel_app.mount("/api", app)
