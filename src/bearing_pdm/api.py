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

import codecs
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
from fastapi import FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from bearing_pdm.health import apply_reference_hi
from bearing_pdm.profiler import MAX_SAMPLING_RATE_HZ, profile_file, sampling_info
from bearing_pdm.routing import MAX_NAN_FRACTION
from bearing_pdm.stages import assign_stages

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
UNSUPPORTED = "UNSUPPORTED"
INVALID_INPUT = "INVALID_INPUT"

_REQUIRED_ANY = {"vibration_x", "vibration_y", "vibration_z"}

# Error contract (docs/api-errors.md): every error body keeps FastAPI's `detail`
# and adds a stable UPPER_SNAKE `code`, a `retryable` bool and a user-readable
# `message`. `retryable` is True only when the same request could succeed later
# without the caller changing it.
_STATUS_DEFAULTS: dict[int, tuple[str, bool]] = {
    400: ("MALFORMED_REQUEST", False),
    404: ("NOT_FOUND", False),
    405: ("METHOD_NOT_ALLOWED", False),
    408: ("REQUEST_TIMEOUT", True),
    413: ("REQUEST_TOO_LARGE", False),
    415: ("UNSUPPORTED_FILE_TYPE", False),
    422: ("VALIDATION_ERROR", False),
    429: ("RATE_LIMITED", True),
    500: ("INTERNAL_ERROR", False),
    503: ("SERVICE_UNAVAILABLE", True),
    504: ("GATEWAY_TIMEOUT", True),
}


class ApiError(HTTPException):
    """HTTPException carrying a stable machine-readable code and retryability."""

    def __init__(self, status_code: int, code: str, detail: str, retryable: bool = False):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code
        self.retryable = retryable


def _error_content(detail: Any, code: str, retryable: bool, message: str | None = None) -> dict[str, Any]:
    if message is None:
        message = detail if isinstance(detail, str) else "The request could not be processed."
    return {"detail": detail, "code": code, "retryable": retryable, "message": message}


def _error_response(status_code: int, code: str, detail: Any, retryable: bool = False,
                    message: str | None = None, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=_error_content(detail, code, retryable, message),
        headers=headers,
    )


_STRUCTURAL_ONLY = (
    "FULLY_SUPPORTED here means the file is structurally parseable (a header maps to at "
    "least one usable vibration column). It does NOT mean a trained model is validated for "
    "this machine, and sampling rate and units are not determined by this check. Whether an "
    "existing model applies (or a retrain is needed) is decided downstream by routing and "
    "applicability, never at this endpoint, so RETRAIN_REQUIRED is never emitted here."
)


def _action(kind: str, message: str, missing: list[str]) -> dict[str, Any]:
    return {"kind": kind, "message": message, "missing": missing}


def _classify_detailed(profile: dict) -> tuple[str, list[str], dict[str, Any]]:
    """Compatibility state, reasons and the machine-readable required action for
    the uploaded file, from profile_file's output only - see goals.md's
    fail-closed dataset-state requirement. This is a column/header-level check;
    it does not run the trained applicability model in applicability.py (that
    needs parsed recordings from a known adapter, not an arbitrary upload) and
    cannot decide RETRAIN_REQUIRED - see docs/dataset-compatibility.md."""
    if not profile.get("readable"):
        return INVALID_INPUT, profile.get("warnings", ["file could not be read"]), _action(
            "FIX_INPUT_FILE",
            "The file could not be read as a delimited numeric table. Upload a non-empty, "
            "readable CSV/TSV/whitespace-separated file.",
            ["a readable, non-empty tabular file"],
        )

    columns = profile.get("columns", [])
    if not profile.get("has_header"):
        return ADAPTER_REQUIRED, [
            "no header row: column meanings cannot be inferred from names; "
            "a dataset adapter (see src/bearing_pdm/adapters.py) is required"
        ], _action(
            "ADAPTER_REQUIRED",
            "Without a header the columns cannot be mapped by name. A dataset adapter in "
            "src/bearing_pdm/adapters.py must map the columns, and the sampling rate and units "
            "must be provided as metadata because a headerless file does not carry them.",
            [
                "column mapping (a dataset adapter in src/bearing_pdm/adapters.py)",
                "sampling_rate_hz (user-provided metadata; not derivable from this file)",
                "vibration units (user-provided metadata; not derivable from this file)",
            ],
        )

    vibration_cols = [c for c in columns if c["canonical"] in _REQUIRED_ANY]
    if not vibration_cols:
        return UNSUPPORTED, [
            "no vibration channel recognised in the header "
            f"(saw: {[c['name'] for c in columns]})"
        ], _action(
            "NO_VIBRATION_CHANNEL",
            "No column resembles a vibration channel. This service predicts bearing RUL from "
            "vibration, so a file without one is a different prediction problem and no adapter "
            "or retraining of the current models can make it usable. (If vibration is present "
            "under a name this check does not recognise, an adapter with an explicit column "
            "mapping is needed instead.)",
            ["a vibration channel (vibration_x, vibration_y or vibration_z)"],
        )
    low = [c["name"] for c in vibration_cols if c["confidence"] == "low"]
    if low:
        return ADAPTER_REQUIRED, [
            f"vibration channel(s) matched only by a low-confidence name guess: {low} "
            "- confirm before use"
        ], _action(
            "ADAPTER_REQUIRED",
            "Vibration columns were matched only by a fuzzy name guess. Add an adapter in "
            "src/bearing_pdm/adapters.py (or an explicit column mapping) that confirms which "
            "columns are vibration channels; the guess is never used silently.",
            [f"confirmed column mapping for: {', '.join(low)} "
             "(a dataset adapter in src/bearing_pdm/adapters.py)"],
        )

    # Column-name mapping alone is fail-open: a column named vibration_x that is
    # non-numeric, empty, constant, or mostly missing is still "mapped" by name
    # but unusable as a signal - profile_file already flags exactly this.
    if profile.get("rows", 0) == 0:
        return INVALID_INPUT, ["file has a header but no data rows"], _action(
            "FIX_INPUT_FILE", "The file has a header but no data rows.", ["data rows"],
        )
    usable = [
        c for c in vibration_cols
        if c["numeric"] and not c["constant"]
        and c["nan_fraction"] <= MAX_NAN_FRACTION and c["inf_count"] == 0
    ]
    if not usable:
        limit = f"{MAX_NAN_FRACTION:.0%}"
        reasons = [
            f"{c['name']}: "
            + ("non-numeric values" if not c["numeric"]
               else "constant in the sampled rows" if c["constant"]
               else f"{c['inf_count']} infinite values" if c["inf_count"]
               else f"more than {limit} missing ({c['nan_fraction']:.0%} rounded); "
                    f"at most {limit} is accepted")
            for c in vibration_cols
        ]
        return INVALID_INPUT, reasons, _action(
            "FIX_INPUT_FILE",
            "Every recognised vibration column is unusable as a signal (see reasons). Fix or "
            "re-export the data; no adapter or model change addresses this.",
            [f"at least one vibration channel that is numeric, non-constant, free of infinite "
             f"values and at most {limit} missing"],
        )
    return FULLY_SUPPORTED, [], _action("STRUCTURAL_CHECK_ONLY", _STRUCTURAL_ONLY, [])


def _classify(profile: dict) -> tuple[str, list[str]]:
    state, reasons, _ = _classify_detailed(profile)
    return state, reasons


class RequiredAction(BaseModel):
    kind: str
    message: str
    missing: list[str]


class DatasetProfileResponse(BaseModel):
    compatibility: str
    reasons: list[str]
    profile: dict[str, Any]
    required_action: RequiredAction
    sampling: dict[str, Any]

# Frontend origin(s) allowed to call this API, e.g. "https://rulguard.vercel.app,http://localhost:3000".
# No default beyond localhost dev - a production origin must be set explicitly, never wildcarded.
_ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

# Upper bound on a whole request body: MAX_UPLOAD_BYTES plus a small margin for
# multipart boundary/header overhead on a file right at the limit. Enforced two
# ways inside _BodyLimitMiddleware: from a declared Content-Length before
# anything is read, and by counting bytes as they arrive when there is no
# Content-Length, so a chunked request can't be buffered unbounded.
# /dataset/inspect's own read loop (MAX_UPLOAD_BYTES) then limits the file
# itself, separately from the multipart overhead allowed here.
_MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 2 * 1024 * 1024


def _request_too_large_detail() -> str:
    return f"Request body exceeds {_MAX_REQUEST_BYTES // (1024 * 1024)}MB."


def _request_too_large() -> ApiError:
    return ApiError(413, "REQUEST_TOO_LARGE", _request_too_large_detail())


class _BodyLimitMiddleware:
    """Pure-ASGI body limit. Rejects a declared Content-Length over
    _MAX_REQUEST_BYTES before reading anything, and otherwise raises a 413
    ApiError as soon as the running byte total passes the limit, so the rest of
    the body is never requested from the server or buffered by Starlette.
    FastAPI's body parsing re-raises HTTPException as-is (any other exception
    would be rewritten to a 4xx parse error). It sits inside CORSMiddleware and
    inside _log_requests, so both 413 paths carry CORS headers and X-Request-ID."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = dict(scope.get("headers") or []).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > _MAX_REQUEST_BYTES:
            error = _request_too_large()
            await _error_response(error.status_code, error.code, error.detail)(scope, receive, send)
            return

        received = 0

        async def counting_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > _MAX_REQUEST_BYTES:
                    raise _request_too_large()
            return message

        await self.app(scope, counting_receive, send)


class _ErrorBoundaryMiddleware:
    """Last-resort JSON 500 for anything a route did not handle, so a client
    never gets a bare traceback or an HTML error page. Sits inside CORS. Logs
    only the exception type: exception messages from parsers can quote cell
    values, and raw sensor data must not reach the logs."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            if started:
                raise
            logger.error(
                "method=%s path=%s status=500 unhandled exception type=%s",
                scope.get("method"), scope.get("path"), type(exc).__name__,
            )
            await _error_response(
                500, "INTERNAL_ERROR", "Internal server error.",
                message="The service hit an unexpected error. Retrying the same request is "
                        "unlikely to help; report the X-Request-ID if it persists.",
            )(scope, receive, send)


app = FastAPI(
    title="RULGuard prediction service",
    description="Read-only inference over cached bearing_pdm artifacts. Never fits a model.",
    version="0.1.0",
)


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    default_code, default_retryable = _STATUS_DEFAULTS.get(exc.status_code, ("HTTP_ERROR", False))
    return _error_response(
        exc.status_code,
        getattr(exc, "code", default_code),
        exc.detail,
        getattr(exc, "retryable", default_retryable),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    summary = "; ".join(
        f"{'.'.join(str(part) for part in err.get('loc', ()))}: {err.get('msg', 'invalid')}"
        for err in errors[:5]
    )
    if len(errors) > 5:
        summary += f"; and {len(errors) - 5} more"
    return _error_response(
        422, "VALIDATION_ERROR", jsonable_encoder(errors),
        message=f"The request is invalid: {summary}",
    )


# The error boundary and body limit are added before CORS so they sit inside
# it: every error they produce carries CORS headers a browser client can read.
app.add_middleware(_BodyLimitMiddleware)
app.add_middleware(_ErrorBoundaryMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    expose_headers=["X-Request-ID"],
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


@app.middleware("http")
async def _log_requests(request: Request, call_next):
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
        raise ApiError(
            503, "METRICS_UNAVAILABLE",
            "reports/metrics/rul_evaluation.json missing. Run scripts/evaluate_models.py first.",
            retryable=True,
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


@app.post("/predict/rul", response_model=PredictRulResponse)
def predict_rul(request: PredictRulRequest) -> PredictRulResponse:
    if request.dataset_id != "femto":
        raise ApiError(
            422, "UNSUPPORTED_DATASET",
            f"dataset_id={request.dataset_id!r} is not supported for RUL prediction. "
            "Every cached model is fit on FEMTO learning bearings only "
            "(docs/decisions.md D11); applying it elsewhere would fabricate a result.",
        )

    model = _load_joblib("rul_extra_trees.joblib")
    if model is None:
        raise ApiError(
            503, "MODEL_UNAVAILABLE",
            "rul_extra_trees.joblib is missing. Run scripts/train_models.py first.",
            retryable=True,
        )

    missing = [c for c in model.feature_columns if c not in request.features]
    max_missing_fraction = 0.5  # below this, too few real measurements to trust the prediction
    if len(missing) / len(model.feature_columns) > max_missing_fraction:
        raise ApiError(
            422, "FEATURES_MISSING",
            f"{len(missing)}/{len(model.feature_columns)} required features are missing "
            f"(max allowed {max_missing_fraction:.0%}). A prediction built mostly from "
            "training medians would not reflect the submitted sample.",
        )

    row = {
        c: request.features.get(c, model.median_fill.get(c))
        for c in model.feature_columns
    }
    if any(v is None for v in row.values()):
        unresolvable = [c for c, v in row.items() if v is None]
        raise ApiError(
            422, "FEATURES_MISSING",
            f"Missing required features with no fallback median: {unresolvable}",
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
        raise ApiError(
            422, "UNSUPPORTED_DATASET",
            f"dataset_id={request.dataset_id!r} is not supported for HI prediction. "
            "The cached reference HI model is fit on FEMTO learning bearings only "
            "(docs/decisions.md D11).",
        )

    reference_model = _load_joblib("reference_hi_model.joblib")
    thresholds = _load_joblib("stage_thresholds.joblib")
    if reference_model is None or thresholds is None:
        raise ApiError(
            503, "MODEL_UNAVAILABLE",
            "HI artifacts missing. Run scripts/build_health.py first.",
            retryable=True,
        )

    missing = [c for c in reference_model.features if any(c not in row for row in request.rows)]
    if missing:
        raise ApiError(
            422, "FEATURES_MISSING",
            f"Every row must include all HI feature columns. Missing from at least one row: {missing}",
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
        raise ApiError(
            422, "INSUFFICIENT_ROWS",
            f"At least {min_rows} rows are required (the model's reference window: "
            f"reference_skip={reference_model.reference_skip} + "
            f"reference_n={reference_model.reference_n}) so the healthy-baseline rows "
            "and the rows being scored don't overlap. Got "
            f"{len(request.rows)}.",
        )

    import numpy as np
    import pandas as pd

    feature_cols = list(reference_model.features)
    non_finite = [
        c for c in feature_cols
        if any(not np.isfinite(row[c]) for row in request.rows)
    ]
    if non_finite:
        raise ApiError(
            422, "NON_FINITE_FEATURES",
            f"Non-finite (NaN/inf) feature values are not allowed: {non_finite}",
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
        raise ApiError(
            422, "DEGENERATE_REFERENCE_WINDOW",
            f"Rows {skip}-{skip + n_ref - 1} (the reference window) show negligible "
            f"variation relative to this model's training scale in all but {len(varying)} "
            "feature(s). The model normalises against this window as the healthy "
            "baseline; a window this flat carries no evidence of actual healthy "
            "variation (e.g. a stuck sensor) and cannot be scored meaningfully.",
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


_BINARY_SIGNATURES = (b"PK\x03\x04", b"%PDF", b"\x1f\x8b", b"\x89PNG")


def _check_text_head(head: bytes) -> None:
    """Reject non-text uploads from the first chunk, before profile_file (which
    decodes with errors='replace') could turn binary junk into a misleading
    profile, or a single enormous line into a huge in-memory sample."""
    if b"\x00" in head or head.startswith(_BINARY_SIGNATURES):
        raise ApiError(
            415, "UNSUPPORTED_FILE_TYPE",
            "The upload is a binary file, not delimited text. Export the data as a "
            "UTF-8 CSV/TSV file and upload that.",
        )
    try:
        codecs.getincrementaldecoder("utf-8")().decode(head, final=False)
    except UnicodeDecodeError as exc:
        raise ApiError(
            422, "UNDECODABLE_FILE",
            "The file is not valid UTF-8 text. Re-save it as UTF-8 and upload it again.",
        ) from exc
    if len(head) >= UPLOAD_CHUNK_BYTES and b"\n" not in head and b"\r" not in head:
        raise ApiError(
            422, "MALFORMED_FILE",
            f"No line break in the first {UPLOAD_CHUNK_BYTES // 1024}KB: this is not a "
            "row-oriented CSV/TSV file.",
        )


@app.post("/dataset/inspect", response_model=DatasetProfileResponse)
async def inspect_dataset(
    file: UploadFile,
    sampling_rate_hz: float | None = Query(
        default=None, gt=0, le=MAX_SAMPLING_RATE_HZ, allow_inf_nan=False,
    ),
) -> DatasetProfileResponse:
    """Upload -> inspect -> classify (goals.md's dataset-detection step), before
    anything is validated/preprocessed/fed to a model. Column-mapping only -
    see docs/dataset-compatibility.md for what this does and does not check."""
    with tempfile.NamedTemporaryFile(suffix=Path(file.filename or "upload").suffix) as tmp:
        written = 0
        try:
            while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                if written == 0:
                    _check_text_head(chunk)
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise ApiError(
                        413, "UPLOAD_TOO_LARGE",
                        f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB inspection limit.",
                    )
                tmp.write(chunk)
            tmp.flush()
        except OSError as exc:
            logger.error("upload spool failed type=%s", type(exc).__name__)
            raise ApiError(
                503, "STORAGE_UNAVAILABLE",
                "The service could not store the upload for inspection. Retry the upload.",
                retryable=True,
            ) from exc

        if written == 0:
            raise ApiError(422, "EMPTY_UPLOAD", "Uploaded file is empty.")

        try:
            profile = profile_file(tmp.name)
            sampling = sampling_info(profile, tmp.name)
            if sampling_rate_hz is not None:
                sampling.update(rate_hz=sampling_rate_hz, source="user", required=False,
                                message="User-supplied sampling rate; this does not validate "
                                        "timestamp regularity or dataset/model compatibility.")
            profile["file"] = file.filename or profile["file"]  # real name, not the temp path
            compatibility, reasons, required_action = _classify_detailed(profile)
            return DatasetProfileResponse(
                compatibility=compatibility, reasons=reasons, profile=profile,
                required_action=RequiredAction(**required_action), sampling=sampling,
            )
        except MemoryError as exc:
            raise ApiError(
                503, "MEMORY_LIMIT_EXCEEDED",
                "The file needs more memory to inspect than this service allows. "
                "Upload a smaller file or a shorter recording.",
            ) from exc
        except Exception as exc:
            # Parser messages can quote cell values; log the type only, never the text.
            logger.warning("inspect failed on malformed upload type=%s", type(exc).__name__)
            raise ApiError(
                422, "MALFORMED_FILE",
                "The file could not be parsed as a delimited numeric table. Upload a "
                "UTF-8 CSV/TSV/whitespace-separated file with a header row.",
            ) from exc


# Vercel's Python runtime forwards the original request path (e.g. /api/health)
# to this function unchanged - it does not strip the /api prefix the way a
# typical reverse-proxy rewrite would. Mounting the unprefixed `app` under /api
# in a separate wrapper keeps local dev (`uvicorn bearing_pdm.api:app`, routes
# at /health) and the test suite (imports `app` directly) on unprefixed paths,
# while api/index.py imports `vercel_app` for the actual deployed function.
vercel_app = FastAPI()
vercel_app.mount("/api", app)
