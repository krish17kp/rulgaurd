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
import contextvars
import hashlib
import json
import logging
import math
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import wraps
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

from bearing_pdm import reliability
from bearing_pdm.adapters import ADAPTERS, VIBRATION_CHANNELS
from bearing_pdm.health import apply_reference_hi
from bearing_pdm.history import configured_history_store
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
RETRAIN_REQUIRED = "RETRAIN_REQUIRED"
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

    def __init__(self, status_code: int, code: str, detail: str, retryable: bool = False,
                 extra: dict[str, Any] | None = None):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code
        self.retryable = retryable
        # Additional top-level body fields (e.g. /analyze/features' `stages`).
        self.extra = extra


def _error_content(detail: Any, code: str, retryable: bool, message: str | None = None) -> dict[str, Any]:
    if message is None:
        message = detail if isinstance(detail, str) else "The request could not be processed."
    return {"detail": detail, "code": code, "retryable": retryable, "message": message}


def _error_response(status_code: int, code: str, detail: Any, retryable: bool = False,
                    message: str | None = None, headers: dict[str, str] | None = None,
                    extra: dict[str, Any] | None = None) -> JSONResponse:
    _note(code=code)
    return JSONResponse(
        status_code=status_code,
        content={**(extra or {}), **_error_content(detail, code, retryable, message)},
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
            _note(exc_type=type(exc).__name__)
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
        extra=getattr(exc, "extra", None),
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
# that automatically, so this needs no new service or credential.
#
# One access record per request (docs/observability.md): a key=value message
# plus the same fields as attributes on the LogRecord. Only a fixed vocabulary
# and derived identifiers are recorded - request id, method, path, status,
# duration, endpoint stage, model name/version, feature-schema version,
# compatibility outcome, error code, exception type. Never a request body,
# feature/sensor value, uploaded filename, query value, exception message or
# filesystem path.
logger = logging.getLogger("bearing_pdm.api")
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

_STAGES = {
    "/health": "health",
    "/models/info": "model_info",
    "/models/evaluation": "model_evaluation",
    "/predict/rul": "predict_rul",
    "/predict/hi": "predict_hi",
    "/predictions/history": "prediction_history",
    "/dataset/inspect": "dataset_inspect",
    "/models/compatibility": "model_compatibility",
    "/analyze/features": "analyze_features",
    "/analyze/rul": "analyze_rul",
}
_REQUEST_OBS: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "bearing_pdm_request_obs", default=None
)


def _note(**fields: Any) -> None:
    """Attach fields to the current request's access-log record (no-op outside a request)."""
    current = _REQUEST_OBS.get()
    if current is not None:
        current.update({k: v for k, v in fields.items() if v is not None})


def _safe_path(path: str) -> str:
    # The ASGI path is percent-decoded, so it can carry newlines or other control characters.
    return "".join(ch if ch.isprintable() else "?" for ch in path)[:200]


def _stage_for(path: str) -> str:
    route = path[len("/api"):] if path.startswith("/api/") else path  # Vercel mount prefix
    return _STAGES.get(route, "unmatched")


@app.middleware("http")
async def _log_requests(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    path = _safe_path(request.url.path)
    fields: dict[str, Any] = {"stage": _stage_for(path)}
    token = _REQUEST_OBS.set(fields)
    start = time.monotonic()
    status = 500
    try:
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as exc:
            fields.update(code="INTERNAL_ERROR", exc_type=type(exc).__name__)
            raise
        finally:
            record = {
                "request_id": request_id, "method": request.method, "path": path,
                "status": status,
                "duration_ms": round((time.monotonic() - start) * 1000, 1),
                **fields,
            }
            line = " ".join(f"{key}={value}" for key, value in record.items())
            (logger.warning if status >= 500 else logger.info)(line, extra=record)
    finally:
        _REQUEST_OBS.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


_MODEL_CACHE: dict[str, Any] = {}

_history_store = configured_history_store()
_MODEL_VERSIONS: dict[str, str] = {}


def _fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _model_provenance(kind: str, artifact: str) -> tuple[str | None, str | None]:
    """(model_version, feature_schema_version) of the loaded artifact, or None for
    whatever is not loaded. Shared by the history record and the access log."""
    model = _MODEL_CACHE.get(artifact)
    columns = getattr(model, "feature_columns", getattr(model, "features", None))
    version = _MODEL_VERSIONS.get(artifact)
    if kind == "predict_hi":
        versions = [_MODEL_VERSIONS.get(name) for name in (artifact, "stage_thresholds.joblib")]
        version = _fingerprint(versions) if all(versions) else None
    return version, _fingerprint(list(columns)) if columns is not None else None


def _note_model(kind: str, artifact: str, model_name: str) -> None:
    version, schema = _model_provenance(kind, artifact)
    _note(model_name=model_name, model_version=version, feature_schema_version=schema)


def _track_prediction(kind: str, artifact: str):
    def decorate(func):
        @wraps(func)
        def tracked(request):
            record = {
                "id": uuid.uuid4().hex,
                "timestamp": datetime.now(UTC).isoformat(),
                "kind": kind,
                "request": {"dataset_id": "femto" if request.dataset_id == "femto" else "other"},
                "input_fingerprint": _fingerprint(request.model_dump()),
                "model_version": None,
                "feature_schema_version": None,
                "compatibility_state": "UNSUPPORTED" if request.dataset_id != "femto" else "NOT_EVALUATED",
                "status": "failed",
                "warnings": [],
                "result": None,
            }
            if kind == "predict_rul":
                record["request"]["n_features_provided"] = len(request.features)
            else:
                record["request"]["n_rows"] = len(request.rows)
            try:
                response = func(request)
                record["status"] = "succeeded"
                record["compatibility_state"] = "FULLY_SUPPORTED"
                if kind == "predict_rul":
                    record["result"] = {
                        "rul_hours": response.rul_hours,
                        "n_features_missing": len(response.features_missing),
                    }
                    if response.features_missing:
                        record["warnings"].append("MISSING_FEATURES_MEDIAN_FILLED")
                else:
                    record["result"] = {
                        "latest_hi": response.rows[-1].health_indicator,
                        "latest_stage": response.rows[-1].stage,
                    }
                    record["warnings"].append("HI_STAGE_IS_SEVERITY_NOT_FAULT_DIAGNOSIS")
                return response
            except ApiError as exc:
                record["error_code"] = exc.code
                if exc.status_code == 422 and exc.code != "UNSUPPORTED_DATASET":
                    record["compatibility_state"] = "INVALID_INPUT"
                raise
            except Exception:
                record["error_code"] = "INTERNAL_ERROR"
                raise
            finally:
                if request.dataset_id == "femto":
                    record["model_version"], record["feature_schema_version"] = (
                        _model_provenance(kind, artifact)
                    )
                try:
                    _history_store.append(record)
                except Exception as exc:
                    _note(exc_type=type(exc).__name__)
                    raise ApiError(503, "HISTORY_UNAVAILABLE",
                                   "Prediction history could not be saved.", retryable=True) from None
        return tracked
    return decorate


def _load_joblib(name: str) -> Any | None:
    """Same missing-artifact contract as dashboard._load_joblib: None, never
    a traceback, cached in-process rather than per-request."""
    if name in _MODEL_CACHE:
        return _MODEL_CACHE[name]
    path = MODELS_DIR / name
    if not path.exists():
        return None
    with path.open("rb") as stream:
        _MODEL_VERSIONS[name] = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
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
    # Goal 21 (docs/prediction-reliability.md): held-out error, tree disagreement,
    # conformal interval and applicability, each traced to a file or computation
    # and null-with-reason when unavailable. Never a confidence or probability.
    reliability: dict[str, Any] | None = None


# The cross-domain bundle (~200MB) is cached per path, outside _MODEL_CACHE, so it
# is read once per process. It supplies only the cached conformal calibrator and
# applicability model; its models are never used for the served prediction.
_BUNDLE_NAME = "cross_domain_bundle.joblib"
_BUNDLE_CACHE: dict[Path, Any] = {}


def _load_bundle() -> Any | None:
    path = MODELS_DIR / _BUNDLE_NAME
    if path not in _BUNDLE_CACHE:
        if not path.exists():
            return None
        _BUNDLE_CACHE[path] = joblib.load(path)
    return _BUNDLE_CACHE[path]


def _reliability(model: Any, x: Any, features: dict[str, float], prediction: float) -> dict:
    """Reliability block; an unexpected failure withholds it (with a reason)
    rather than failing a prediction that was itself computed correctly."""
    try:
        return reliability.build(METRICS_DIR / "rul_evaluation.json", _load_bundle(), model,
                                 "extra_trees", x, features, prediction)
    except Exception as exc:
        _note(exc_type=type(exc).__name__)
        return reliability.unavailable(
            "Reliability information could not be computed from the cached artifacts; "
            "none is reported.")


@app.get("/health")
def health() -> dict[str, Any]:
    tree_model = _load_joblib("rul_extra_trees.joblib")
    naive_model = _load_joblib("rul_naive.joblib")
    hi_model = _load_joblib("reference_hi_model.joblib")
    thresholds = _load_joblib("stage_thresholds.joblib")
    loaded = {
        "rul_extra_trees": tree_model is not None,
        "rul_naive": naive_model is not None,
    }
    version, schema = _model_provenance("predict_rul", "rul_extra_trees.joblib")
    hi_version, hi_schema = _model_provenance("predict_hi", "reference_hi_model.joblib")
    # Identifiers only (content hashes), never file names or paths.
    models = {
        "rul_extra_trees": {
            "loaded": loaded["rul_extra_trees"], "version": version,
            "feature_schema_version": schema,
        },
        "reference_hi": {
            "loaded": hi_model is not None and thresholds is not None, "version": hi_version,
            "feature_schema_version": hi_schema,
        },
    }
    return {
        "status": "ok",
        "models_loaded": loaded,
        "models": models,
        "ready": models["rul_extra_trees"]["loaded"] and models["reference_hi"]["loaded"],
        "api_version": app.version,
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
@_track_prediction("predict_rul", "rul_extra_trees.joblib")
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
    _note_model("predict_rul", "rul_extra_trees.joblib", "extra_trees")

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
        reliability=_reliability(model, x, request.features, prediction),
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
@_track_prediction("predict_hi", "reference_hi_model.joblib")
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
    _note_model("predict_hi", "reference_hi_model.joblib", "reference_hi")

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
    return response


# Model-compatibility gate (docs/dataset-compatibility.md, "Model compatibility").
# Every cached RUL model is fit on FEMTO learning bearings only (D11); the model
# artifact itself carries no domain field, so the domain is stated here, once.
TRAINED_DATASET_ID = "femto"
# rul_selected_model.json's "selected" name -> the artifact holding its feature schema.
_SELECTED_MODEL_ARTIFACTS = {"extra_trees": "rul_extra_trees.joblib"}
# A supplied sampling rate must equal the adapter's documented rate: the model's
# spectral features (Hz-valued, band fractions) are only defined at that rate.
SAMPLING_RATE_REL_TOL = 1e-6


class CompatibilityRequest(BaseModel):
    dataset_id: str = Field(..., max_length=100, description="Adapter id, e.g. 'femto'.")
    feature_names: list[str] = Field(
        ..., max_length=10_000,
        description="Feature column names the dataset provides (names only, never values).",
    )
    sampling_rate_hz: float | None = Field(
        default=None, gt=0, le=MAX_SAMPLING_RATE_HZ, allow_inf_nan=False,
        description="Acquisition rate of the recordings the features were computed from.",
    )


class CompatibilityResponse(BaseModel):
    compatibility: str
    dataset_id: str
    reasons: list[str]
    required_action: RequiredAction
    model: dict[str, Any]
    adapter: dict[str, Any] | None
    feature_schema: dict[str, Any]
    required_signals: list[str]
    sampling: dict[str, Any]
    prediction_produced: bool = False


def _selected_rul_model() -> tuple[str, str, Any]:
    """(model name, artifact, loaded model) for the selected RUL model, or a 503:
    without its metadata nothing can be compared, so the gate fails closed."""
    try:
        name = json.loads((MODELS_DIR / "rul_selected_model.json").read_text())["selected"]
    except (OSError, ValueError, KeyError, TypeError):
        name = None
    artifact = _SELECTED_MODEL_ARTIFACTS.get(name) if isinstance(name, str) else None
    model = _load_joblib(artifact) if artifact else None
    columns = getattr(model, "feature_columns", None)
    if not columns or not all(isinstance(c, str) for c in columns):
        raise ApiError(
            503, "MODEL_UNAVAILABLE",
            "Selected RUL model metadata (rul_selected_model.json and the model's feature "
            "schema) is unavailable, so compatibility cannot be decided. Run "
            "scripts/train_models.py first.",
            retryable=True,
        )
    _note_model("predict_rul", artifact, name)
    return name, artifact, model


@app.post("/models/compatibility", response_model=CompatibilityResponse)
def model_compatibility(request: CompatibilityRequest) -> CompatibilityResponse:
    """Is a dataset compatible with the selected cached RUL model? Metadata only:
    no raw data is accepted and no prediction is produced. The mapping of each
    state to model.md section 8 is justified in docs/dataset-compatibility.md."""
    dataset_id = request.dataset_id.strip().lower()
    names = [n.strip() for n in request.feature_names]
    user_rate = request.sampling_rate_hz

    def respond(state: str, reasons: list[str], kind: str, message: str, missing: list[str],
                **fields: Any) -> CompatibilityResponse:
        _note(compatibility=state)
        return CompatibilityResponse(
            compatibility=state, dataset_id=dataset_id, reasons=reasons,
            required_action=RequiredAction(kind=kind, message=message, missing=missing),
            **fields,
        )

    invalid = []
    if not dataset_id:
        invalid.append("dataset_id is empty")
    if not names:
        invalid.append("feature_names is empty")
    if any(not n for n in names):
        invalid.append("feature_names contains an empty name")
    duplicates = sorted({n for n in names if n and names.count(n) > 1})
    if duplicates:
        invalid.append(f"feature_names contains duplicates: {duplicates}")
    if invalid:
        return respond(
            INVALID_INPUT, invalid, "FIX_REQUEST",
            "The request does not describe a dataset; fix it and resubmit.",
            ["a non-empty dataset_id and a non-empty list of unique, non-empty feature names"],
            model={}, adapter=None, feature_schema={}, required_signals=[],
            sampling={"rate_hz": user_rate, "source": "user" if user_rate else None,
                      "compatible": None},
        )

    model_name, artifact, model = _selected_rul_model()
    expected = list(model.feature_columns)
    version, schema_version = _model_provenance("predict_rul", artifact)
    provided, expected_set = set(names), set(expected)
    missing = [c for c in expected if c not in provided]
    extra = [n for n in names if n not in expected_set]
    # Signals the model's features are computed from (canonical channel prefix).
    required_signals = [ch for ch in VIBRATION_CHANNELS if any(c.startswith(f"{ch}_") for c in expected)]
    fields: dict[str, Any] = {
        "model": {"name": model_name, "version": version,
                  "feature_schema_version": schema_version,
                  "trained_dataset_id": TRAINED_DATASET_ID},
        "feature_schema": {"expected_count": len(expected), "provided_count": len(names),
                           "missing": missing, "extra": extra},
        "required_signals": required_signals,
    }

    adapter = ADAPTERS.get(dataset_id)
    if adapter is None:
        return respond(
            UNSUPPORTED,
            [f"no registered adapter for dataset_id {dataset_id!r} "
             f"(registered: {sorted(ADAPTERS)}); its signals, units and sampling are unknown"],
            "UNSUPPORTED_DATASET",
            "No validated adapter exists for this dataset, so its signals, units and sampling "
            "cannot be established. A new adapter (src/bearing_pdm/adapters.py) and a model "
            "trained and validated on this dataset are both required before any prediction.",
            ["a registered dataset adapter", "a model trained and validated on this dataset"],
            adapter=None,
            sampling={"rate_hz": user_rate, "source": "user" if user_rate else None,
                      "compatible": None},
            **fields,
        )

    documented = adapter.sampling_rate_hz
    fields["adapter"] = {"dataset_id": adapter.dataset_id, "display_name": adapter.display_name,
                         "sampling_rate_hz": documented}
    if user_rate is not None:
        rate_ok = documented is not None and math.isclose(
            user_rate, documented, rel_tol=SAMPLING_RATE_REL_TOL)
        fields["sampling"] = {"rate_hz": user_rate, "source": "user", "compatible": rate_ok}
    else:
        rate_ok = documented is not None
        fields["sampling"] = {"rate_hz": documented,
                              "source": "adapter_metadata" if rate_ok else None,
                              "compatible": True if rate_ok else None}

    if dataset_id != TRAINED_DATASET_ID:
        return respond(
            RETRAIN_REQUIRED,
            [f"the selected model is trained only on {TRAINED_DATASET_ID!r}; {dataset_id!r} "
             "is a different machine/operating domain (docs/decisions.md D11), whatever its "
             "feature schema"],
            "RETRAIN_REQUIRED",
            f"A registered adapter exists for {dataset_id!r}, but the cached model is fit on "
            f"{TRAINED_DATASET_ID!r} only and is never applied to other datasets. A model must "
            "be trained and validated on this dataset's domain first.",
            [f"a model trained and validated on {dataset_id!r}"],
            **fields,
        )

    if not rate_ok:
        return respond(
            RETRAIN_REQUIRED,
            [f"sampling_rate_hz {user_rate:g} differs from the {dataset_id!r} adapter's "
             f"documented {documented:g} Hz that the model was trained at; its "
             "frequency-domain features are not comparable"],
            "RETRAIN_REQUIRED",
            "The recordings were not acquired at the rate the model was trained on. The model "
            "must be retrained and validated at this rate, or the supplied rate corrected if "
            "it was wrong.",
            [f"recordings at {documented:g} Hz, or a model trained and validated at "
             f"{user_rate:g} Hz"],
            **fields,
        )

    if missing:
        return respond(
            ADAPTER_REQUIRED,
            [f"{len(missing)}/{len(expected)} model features are not provided: {missing}"],
            "ADAPTER_REQUIRED",
            f"Same domain as the model, but the provided features do not reproduce its schema. "
            f"Re-extract features from the raw recordings through the registered "
            f"{dataset_id!r} adapter and the project feature pipeline, which produce exactly "
            "this schema. This gate never fills missing features.",
            [f"feature: {c}" for c in missing] + [f"signal: {s}" for s in required_signals],
            **fields,
        )

    reasons = []
    if extra:
        reasons.append(f"{len(extra)} extra feature(s) are not used by the model "
                       "(features are selected by name; no semantic change)")
    return respond(
        FULLY_SUPPORTED, reasons, "NONE",
        "Dataset domain, sampling rate and feature schema match the selected model's training "
        "metadata. This is a metadata check only: it does not check data quality or whether "
        "the actual feature values lie inside the training distribution (applicability.py), "
        "and it is not a validation of any prediction.",
        [],
        **fields,
    )


@app.get("/predictions/history")
def prediction_history() -> dict[str, Any]:
    """Bounded prediction summaries, newest first, from the configured store."""
    try:
        records = _history_store.recent()
    except Exception:
        raise ApiError(503, "HISTORY_UNAVAILABLE",
                       "Prediction history could not be read.", retryable=True) from None
    return {"count": len(records), "limit": _history_store.limit, "predictions": records}


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


@contextmanager
def _temporary_upload():
    """Own exactly one server-created raw file; never accept a deletion path."""
    _note(upload_id=uuid.uuid4().hex, cleanup_state="not_created")
    tmp = tempfile.NamedTemporaryFile(suffix=".csv")
    _note(cleanup_state="pending")
    try:
        yield tmp
    finally:
        # Synchronous close/unlink also runs when an async task is cancelled.
        try:
            tmp.close()
        except OSError:
            _note(cleanup_state="failed")
            raise
        else:
            _note(cleanup_state="deleted")


async def _spool_upload(file: UploadFile, tmp: Any) -> int:
    """Copy the upload into `tmp` in bounded chunks, enforcing MAX_UPLOAD_BYTES and
    the text-head check. The caller owns `tmp` (a NamedTemporaryFile context, so
    the raw file is deleted on every exit path)."""
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
        _note(exc_type=type(exc).__name__)
        raise ApiError(
            503, "STORAGE_UNAVAILABLE",
            "The service could not store the upload for inspection. Retry the upload.",
            retryable=True,
        ) from exc

    if written == 0:
        raise ApiError(422, "EMPTY_UPLOAD", "Uploaded file is empty.")
    return written


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
    with _temporary_upload() as tmp:
        await _spool_upload(file, tmp)
        try:
            profile = profile_file(tmp.name)
            sampling = sampling_info(profile, tmp.name)
            if sampling_rate_hz is not None:
                sampling.update(rate_hz=sampling_rate_hz, source="user", required=False,
                                message="User-supplied sampling rate; this does not validate "
                                        "timestamp regularity or dataset/model compatibility.")
            profile["file"] = file.filename or profile["file"]  # real name, not the temp path
            compatibility, reasons, required_action = _classify_detailed(profile)
            _note(compatibility=compatibility)
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
            _note(exc_type=type(exc).__name__)
            raise ApiError(
                422, "MALFORMED_FILE",
                "The file could not be parsed as a delimited numeric table. Upload a "
                "UTF-8 CSV/TSV/whitespace-separated file with a header row.",
            ) from exc


# Upload -> dataset detection -> validation -> preprocessing -> feature extraction
# (docs/feature-analysis.md). Deliberately stops before any health indicator or
# model: no cached artifact is loaded, so D11's FEMTO-only gate is never in play.
ANALYZE_STAGES = ("upload", "dataset_detection", "validation", "preprocessing",
                  "feature_extraction")
# The FEMTO acquisition length (0.1 s at 25.6 kHz, the project's fixed feature window).
# Only a default window length in samples; it makes no claim about any other machine.
DEFAULT_WINDOW_SAMPLES = 2560
MAX_WINDOW_SAMPLES = 1_048_576
# Response size bound; windows past it are not computed (the total is still exact).
MAX_RETURNED_WINDOWS = 200
ANALYZE_CHUNK_ROWS = 65_536


class PipelineStage(BaseModel):
    name: str
    status: str = Field(..., description="ok | failed | skipped")
    detail: str


class AnalyzedWindow(BaseModel):
    index: int
    row_start: int = Field(..., description="Zero-based data row (header excluded), inclusive.")
    row_stop: int = Field(..., description="Zero-based data row, exclusive.")
    features: dict[str, float | None]


class AnalyzeFeaturesResponse(BaseModel):
    stages: list[PipelineStage]
    file: str
    channel: dict[str, Any]
    compatibility: str
    reasons: list[str]
    sampling: dict[str, Any]
    window: dict[str, Any]
    signal: dict[str, Any]
    windows_total: int
    windows_returned: int
    truncated: bool
    truncation_note: str | None
    feature_names: list[str]
    non_finite_feature_values: int
    windows: list[AnalyzedWindow]
    health_indicator_produced: bool = False
    prediction_produced: bool = False
    note: str = (
        "Per-window signal features only. No health indicator, stage or RUL is computed, "
        "and no model is applied. Amplitude features are in the channel's recorded units, "
        "which this endpoint does not determine; frequency features (Hz) depend on the "
        "sampling rate reported in `sampling`."
    )


class _StageTracker:
    """Explicit per-stage state: every stage starts `skipped` and is set exactly
    once, so a failure is attributed to the stage that raised it."""

    def __init__(self, names: tuple[str, ...] = ANALYZE_STAGES) -> None:
        self._stages = {name: PipelineStage(name=name, status="skipped",
                                            detail="Not run: an earlier stage failed.")
                        for name in names}

    def ok(self, name: str, detail: str) -> None:
        self._stages[name] = PipelineStage(name=name, status="ok", detail=detail)

    def skip(self, name: str, detail: str) -> None:
        self._stages[name] = PipelineStage(name=name, status="skipped", detail=detail)

    def fail(self, name: str, status_code: int, code: str, detail: str,
             retryable: bool = False, **extra: Any) -> ApiError:
        self._stages[name] = PipelineStage(name=name, status="failed", detail=detail)
        _note(pipeline_stage=name)
        return ApiError(status_code, code, detail, retryable,
                        extra={"failed_stage": name, "stages": self.as_list(), **extra})

    def as_list(self) -> list[dict[str, str]]:
        return [stage.model_dump() for stage in self._stages.values()]


def _resolve_channel(columns: list[dict], channel: str) -> tuple[dict | None, str | None, str]:
    """(column, error code, reason). `channel` is a header name, or a canonical
    vibration name that exactly one high-confidence header maps to."""
    matches = [c for c in columns if c["name"] == channel] or [
        c for c in columns if c["canonical"] == channel and c["confidence"] == "high"]
    if not matches:
        return None, "CHANNEL_NOT_FOUND", (
            f"channel {channel!r} is neither a header column nor the canonical name of one "
            f"(header: {[c['name'] for c in columns]})")
    if len(matches) > 1:
        return None, "CHANNEL_AMBIGUOUS", (
            f"channel {channel!r} matches several columns {[c['name'] for c in matches]}; "
            "name the header column exactly")
    column = matches[0]
    if column["canonical"] not in _REQUIRED_ANY or column["confidence"] != "high":
        return None, "CHANNEL_NOT_VIBRATION", (
            f"column {column['name']!r} is not a confirmed vibration channel "
            f"(mapped to {column['canonical']!r}, {column['confidence']} confidence); "
            "features are computed from vibration only")
    return column, None, ""


def _finite_or_none(value: float) -> float | None:
    return value if math.isfinite(value) else None


@app.post("/analyze/features", response_model=AnalyzeFeaturesResponse)
async def analyze_features(
    file: UploadFile,
    channel: str = Query(..., min_length=1, max_length=200,
                         description="Vibration header column (or its canonical name)."),
    sampling_rate_hz: float | None = Query(
        default=None, gt=0, le=MAX_SAMPLING_RATE_HZ, allow_inf_nan=False,
        description="Required unless regular timestamps in seconds determine it."),
    window_samples: int = Query(default=DEFAULT_WINDOW_SAMPLES, ge=2, le=MAX_WINDOW_SAMPLES),
    overlap_samples: int = Query(default=0, ge=0, le=MAX_WINDOW_SAMPLES),
) -> AnalyzeFeaturesResponse:
    """Upload -> dataset detection -> validation -> preprocessing -> feature
    extraction, with a `stages` array on success and on every staged failure
    (docs/feature-analysis.md). The raw upload lives only in a temporary file
    removed when the request ends."""
    stages = _StageTracker()
    with _temporary_upload() as tmp:
        try:
            written = await _spool_upload(file, tmp)
        except ApiError as exc:
            raise stages.fail("upload", exc.status_code, exc.code, exc.detail,
                              exc.retryable) from None
        stages.ok("upload", f"{written} bytes received and held in a temporary file that is "
                            "deleted when the request ends.")
        return _analyze_spooled(tmp.name, file.filename, stages, channel=channel,
                                user_rate=sampling_rate_hz, window_samples=window_samples,
                                overlap_samples=overlap_samples)


def _analyze_spooled(path: str, filename: str | None, stages: _StageTracker, *, channel: str,
                     user_rate: float | None, window_samples: int,
                     overlap_samples: int) -> AnalyzeFeaturesResponse:
    import pandas as pd

    from bearing_pdm.chunked import WindowReport, iter_csv_window_features, scan_csv_column
    from bearing_pdm.profiler import SAMPLING_RTOL

    memory_detail = ("The file needs more memory than this service allows. Upload a smaller "
                     "file or a shorter recording.")

    # --- dataset detection: the same profile/classify /dataset/inspect uses.
    stage = "dataset_detection"
    try:
        profile = profile_file(path)
        sampling = sampling_info(profile, path)
    except MemoryError:
        raise stages.fail(stage, 503, "MEMORY_LIMIT_EXCEEDED", memory_detail) from None
    except Exception as exc:
        _note(exc_type=type(exc).__name__)
        raise stages.fail(stage, 422, "MALFORMED_FILE",
                          "The file could not be parsed as a delimited numeric table.") from None
    compatibility, reasons, action = _classify_detailed(profile)
    _note(compatibility=compatibility)
    if not profile.get("readable"):
        raise stages.fail(stage, 422, "MALFORMED_FILE",
                          "The file could not be read as a delimited table: " + "; ".join(reasons),
                          compatibility=compatibility)
    if compatibility in (ADAPTER_REQUIRED, UNSUPPORTED):
        raise stages.fail(stage, 422, action["kind"], "; ".join(reasons),
                          compatibility=compatibility, required_action=action)
    # A one-column file has no delimiter to sniff and reads identically as CSV.
    if profile.get("delimiter") != "," and profile.get("n_columns") != 1:
        raise stages.fail(stage, 422, "UNSUPPORTED_DELIMITER",
                          f"Delimiter {profile.get('delimiter')!r} detected; this endpoint reads "
                          "comma-separated files only. Re-export as CSV.",
                          compatibility=compatibility)
    column, code, reason = _resolve_channel(profile["columns"], channel)
    if column is None:
        raise stages.fail(stage, 422, code, reason, compatibility=compatibility)
    stages.ok(stage, f"Header parsed; channel {column['name']!r} maps to {column['canonical']} "
                     f"(high confidence). Structural state: {compatibility} (a column-mapping "
                     "check only; no model applicability is decided here).")

    # --- validation: timing metadata, window parameters and a whole-file scan of
    # the channel (the profile above samples only the first rows).
    stage = "validation"
    problems: list[tuple[str, str]] = []
    if overlap_samples >= window_samples:
        problems.append(("INVALID_WINDOW", f"overlap_samples ({overlap_samples}) must be smaller "
                                           f"than window_samples ({window_samples})"))
    derived = sampling["rate_hz"] if sampling["source"] == "timestamps" else None
    if sampling["regular"] is False:
        problems.append(("TIMESTAMPS_IRREGULAR", sampling["message"]))
    if user_rate is not None:
        if derived is not None and not math.isclose(user_rate, derived, rel_tol=SAMPLING_RTOL):
            problems.append(("SAMPLING_RATE_CONFLICT",
                             f"sampling_rate_hz {user_rate:g} disagrees with the {derived:g} Hz "
                             "implied by the file's timestamps (1% tolerance)"))
        rate, rate_source = user_rate, "user"
    elif derived is not None:
        rate, rate_source = derived, "timestamps"
    else:
        rate, rate_source = None, None
        problems.append(("SAMPLING_RATE_REQUIRED",
                         "no sampling_rate_hz was supplied and the file has no regular timestamp "
                         "column in seconds to derive one from; frequency features need it"))

    timestamps = [c for c in profile["columns"] if c["canonical"] == "timestamp"]
    order_column = timestamps[0]["name"] if len(timestamps) == 1 and timestamps[0]["numeric"] else None
    try:
        scan = scan_csv_column(path, column=column["name"], chunk_rows=ANALYZE_CHUNK_ROWS,
                               order_column=order_column)
    except MemoryError:
        raise stages.fail(stage, 503, "MEMORY_LIMIT_EXCEEDED", memory_detail) from None
    except (ValueError, pd.errors.ParserError) as exc:
        _note(exc_type=type(exc).__name__)
        raise stages.fail(stage, 422, "MALFORMED_FILE",
                          "The file could not be read in full as a comma-separated table "
                          "(e.g. ragged rows after the sampled head).") from None
    name = column["name"]
    if scan.rows < window_samples:
        problems.append(("INSUFFICIENT_SAMPLES",
                         f"{scan.rows} samples in {name!r}; at least one complete window of "
                         f"{window_samples} samples is required"))
    if scan.non_numeric:
        problems.append(("NON_NUMERIC_SIGNAL", f"{name!r} has {scan.non_numeric} non-numeric "
                                               "value(s)"))
    if scan.infinite:
        problems.append(("NON_FINITE_SIGNAL", f"{name!r} has {scan.infinite} infinite value(s)"))
    if scan.rows and (scan.finite_min is None or scan.finite_min == scan.finite_max):
        problems.append(("CONSTANT_SIGNAL", f"{name!r} has no variation across the whole file "
                                            "(constant or no finite values)"))
    missing_fraction = scan.missing / scan.rows if scan.rows else 0.0
    if missing_fraction > MAX_NAN_FRACTION:
        problems.append(("EXCESSIVE_MISSING",
                         f"{missing_fraction:.1%} of {name!r} is missing; at most "
                         f"{MAX_NAN_FRACTION:.0%} is accepted"))
    if scan.order_column_rows_out_of_order:
        problems.append(("SAMPLES_OUT_OF_ORDER",
                         f"timestamp column {order_column!r} is not strictly increasing in "
                         f"{scan.order_column_rows_out_of_order} row(s)"))
    if problems:
        raise stages.fail(stage, 422, problems[0][0], "; ".join(r for _, r in problems),
                          compatibility=compatibility,
                          validation_errors=[{"code": c, "reason": r} for c, r in problems])
    stages.ok(stage, f"{scan.rows} samples, all numeric and finite where present, "
                     f"{scan.missing} missing ({missing_fraction:.1%}), not constant; "
                     f"sampling rate {rate:g} Hz from {rate_source}"
                     + (f"; {order_column!r} strictly increasing" if order_column else "") + ".")

    # --- preprocessing: framing only; windows_total is exact from the scan.
    step = window_samples - overlap_samples
    windows_total = (scan.rows - window_samples) // step + 1
    covered = (windows_total - 1) * step + window_samples
    stages.ok("preprocessing",
              f"Framing only: {windows_total} complete window(s) of {window_samples} samples "
              f"({window_samples / rate:g} s), overlap {overlap_samples}, stride {step}; the "
              f"last {scan.rows - covered} sample(s) do not fill a window and are not used. No "
              "filtering, detrending, resampling, padding or imputation; missing samples are "
              "omitted inside each window by the feature formulas.")

    # --- feature extraction: the bounded-memory chunked extractor, stopped at the cap.
    stage = "feature_extraction"
    expected = min(windows_total, MAX_RETURNED_WINDOWS)
    stream = iter_csv_window_features(
        path, vibration_column=name, window_samples=window_samples,
        overlap_samples=overlap_samples, chunk_rows=ANALYZE_CHUNK_ROWS, sample_rate_hz=rate,
        report=WindowReport())
    extracted = []
    try:
        for item in stream:
            extracted.append(item)
            if len(extracted) >= expected:
                break
    except MemoryError:
        raise stages.fail(stage, 503, "MEMORY_LIMIT_EXCEEDED", memory_detail) from None
    except (ValueError, pd.errors.ParserError) as exc:
        _note(exc_type=type(exc).__name__)
        raise stages.fail(stage, 422, "FEATURE_EXTRACTION_FAILED",
                          "The feature extractor could not read the validated channel.") from None
    finally:
        stream.close()
    if len(extracted) != expected:
        raise stages.fail(stage, 500, "FEATURE_EXTRACTION_FAILED",
                          f"Extracted {len(extracted)} window(s) where the validated sample "
                          f"count implies {expected}; no partial result is returned.")

    windows, non_finite = [], 0
    for index, item in enumerate(extracted):
        features = {k: _finite_or_none(float(v)) for k, v in item.features.items()}
        non_finite += sum(v is None for v in features.values())
        windows.append(AnalyzedWindow(index=index, row_start=item.row_start,
                                      row_stop=item.row_stop, features=features))
    truncated = windows_total > len(windows)
    stages.ok(stage, f"{len(windows)} of {windows_total} window(s) featurised"
                     + (f" (response capped at {MAX_RETURNED_WINDOWS})" if truncated else "")
                     + f"; {non_finite} non-finite feature value(s) returned as null.")
    return AnalyzeFeaturesResponse(
        stages=stages.as_list(), file=filename or "upload",
        channel={"column": name, "canonical": column["canonical"]},
        compatibility=compatibility, reasons=reasons,
        sampling={"rate_hz": rate, "source": rate_source,
                  "timestamp_check": sampling["message"], "timestamps_regular": sampling["regular"]},
        window={"samples": window_samples, "overlap_samples": overlap_samples,
                "step_samples": step, "seconds": window_samples / rate},
        signal={"rows": scan.rows, "missing": scan.missing, "missing_fraction": missing_fraction},
        windows_total=windows_total, windows_returned=len(windows), truncated=truncated,
        truncation_note=(f"Only the first {len(windows)} of {windows_total} windows are "
                         "returned; later windows were not computed." if truncated else None),
        feature_names=list(extracted[0].features), non_finite_feature_values=non_finite,
        windows=windows,
    )


# Code-owned contract for legacy artifacts without embedded preprocessing metadata.
FEMTO_PREPROCESSING_VERSION = "femto-acquisition-v1"
RUL_ANALYZE_STAGES = (*ANALYZE_STAGES, "model_compatibility", "health_indicator", "prediction")


class AnalyzeRulResponse(BaseModel):
    stages: list[PipelineStage]
    compatibility: str
    model: dict[str, Any]
    preprocessing_version: str
    rul_seconds: float
    rul_hours: float
    prediction_produced: bool = True
    health_indicator_produced: bool
    health: HiResponse | None
    warnings: list[str]
    reliability: dict[str, Any] | None
    supporting: dict[str, Any]


@app.post("/analyze/rul", response_model=AnalyzeRulResponse)
async def analyze_rul(
    file: UploadFile,
    dataset_id: str = Query(..., min_length=1, max_length=100),
    units: str = Query(..., min_length=1, max_length=40),
    preprocessing_version: str = Query(..., min_length=1, max_length=100),
    sampling_rate_hz: float | None = Query(
        default=None, gt=0, le=MAX_SAMPLING_RATE_HZ, allow_inf_nan=False),
    window_samples: int = Query(default=DEFAULT_WINDOW_SAMPLES, ge=2,
                                le=MAX_WINDOW_SAMPLES),
    overlap_samples: int = Query(default=0, ge=0, le=MAX_WINDOW_SAMPLES),
) -> AnalyzeRulResponse:
    """Ordered FEMTO acquisitions (two named axes, g) to the latest RUL.

    Dataset/units are caller attestations, never inferred from signal shape.
    Reuse the staged feature pipeline for each axis and public prediction paths;
    never fit, fill a missing feature, or predict from a truncated run.
    """
    stages = _StageTracker(RUL_ANALYZE_STAGES)
    try:
        return await _analyze_upload(
            file, stages, dataset_id=dataset_id, units=units,
            preprocessing_version=preprocessing_version, sampling_rate_hz=sampling_rate_hz,
            window_samples=window_samples, overlap_samples=overlap_samples)
    except ApiError as exc:
        exc.extra = {**(exc.extra or {}), "prediction_produced": False,
                     "rul_seconds": None, "rul_hours": None}
        raise


async def _analyze_upload(file, stages, *, dataset_id, units, preprocessing_version,
                          sampling_rate_hz, window_samples, overlap_samples):
    with _temporary_upload() as tmp:
        try:
            written = await _spool_upload(file, tmp)
        except ApiError as exc:
            raise stages.fail("upload", exc.status_code, exc.code, exc.detail,
                              exc.retryable) from None
        stages.ok("upload", f"{written} bytes received; temporary upload deleted after analysis.")
        axes = []
        for axis in VIBRATION_CHANNELS:
            # A failed second channel must not inherit successful later stages
            # from the first. Only combine stage success once both have passed.
            channel_stages = _StageTracker(RUL_ANALYZE_STAGES)
            channel_stages.ok("upload", stages._stages["upload"].detail)
            axes.append(_analyze_spooled(
                tmp.name, file.filename, channel_stages, channel=axis,
                user_rate=sampling_rate_hz, window_samples=window_samples,
                overlap_samples=overlap_samples))
        for name in ANALYZE_STAGES[1:]:
            details = [next(s.detail for s in a.stages if s.name == name) for a in axes]
            stages.ok(name, " | ".join(details))

    rows = []
    for index in range(axes[0].windows_returned):
        row = {}
        for axis in axes:
            # The extractor prefixes with the source header, routing uses the
            # canonical name resolved by the existing high-confidence mapper.
            prefix = axis.channel["column"] + "_"
            row.update({axis.channel["canonical"] + "_" + key[len(prefix):]: value
                        for key, value in axis.windows[index].features.items()})
        rows.append(row)

    stage = "model_compatibility"
    try:
        gate = model_compatibility(CompatibilityRequest(
            dataset_id=dataset_id, feature_names=list(rows[0]),
            sampling_rate_hz=axes[0].sampling["rate_hz"]))
    except ApiError as exc:
        raise stages.fail(stage, exc.status_code, exc.code, exc.detail, exc.retryable) from None
    if gate.compatibility != FULLY_SUPPORTED:
        raise stages.fail(stage, 422, gate.required_action.kind, "; ".join(gate.reasons),
                          compatibility=gate.compatibility,
                          required_action=gate.required_action.model_dump(), model=gate.model)
    if gate.model.get("name") != "extra_trees":
        raise stages.fail(stage, 503, "MODEL_UNAVAILABLE",
                          "No raw acquisition serving contract exists for the selected model.")
    if units != "g":
        raise stages.fail(stage, 422, "UNITS_MISMATCH",
                          "Both FEMTO acceleration axes must be confirmed in g; no conversion "
                          "or inferred units are supported.", compatibility=ADAPTER_REQUIRED)
    if (preprocessing_version != FEMTO_PREPROCESSING_VERSION or window_samples != 2560
            or overlap_samples != 0):
        raise stages.fail(stage, 422, "PREPROCESSING_MISMATCH",
                          "The cached FEMTO pipeline requires femto-acquisition-v1: complete "
                          "2560-sample acquisitions, no overlap or prior signal transforms.",
                          compatibility=ADAPTER_REQUIRED)
    if any(a.truncated or a.signal["rows"] % 2560 for a in axes):
        raise stages.fail(stage, 422, "INCOMPLETE_RUN",
                          "Supply complete acquisitions within the returned-window limit; "
                          "a truncated prefix cannot represent the latest recording.",
                          compatibility=INVALID_INPUT)
    if any(value is None or not math.isfinite(value) for row in rows for value in row.values()):
        raise stages.fail(stage, 422, "NON_FINITE_FEATURES",
                          "Every derived feature must be finite; no median filling is allowed.",
                          compatibility=INVALID_INPUT)
    stages.ok(stage, "FEMTO domain, two axes in g, sampling, feature schema and "
                    "preprocessing contract match the selected cached model.")
    warnings = list(gate.reasons)
    health = None
    try:
        health = predict_hi(HiRequest(dataset_id="femto", rows=[
            {**row, "sequence_index": index} for index, row in enumerate(rows)]))
    except ApiError as exc:
        if exc.code != "INSUFFICIENT_ROWS":
            raise stages.fail("health_indicator", exc.status_code, exc.code, exc.detail,
                              exc.retryable) from None
        # RUL uses signal features, not HI; retain /predict/rul's independent
        # contract while explicitly withholding health for a short history.
        warnings.append("Health indicator unavailable: " + exc.detail)
        stages.skip("health_indicator", warnings[-1])
    else:
        stages.ok("health_indicator", "Reference HI and severity stages computed by /predict/hi.")
    try:
        prediction = predict_rul(PredictRulRequest(dataset_id="femto", features=rows[-1]))
    except ApiError as exc:
        raise stages.fail("prediction", exc.status_code, exc.code, exc.detail,
                          exc.retryable) from None
    if not math.isfinite(prediction.rul_seconds) or prediction.rul_seconds < 0:
        raise stages.fail("prediction", 503, "INVALID_MODEL_OUTPUT",
                          "The cached model did not produce a finite non-negative RUL.")
    stages.ok("prediction", "RUL for the last complete acquisition computed by /predict/rul.")
    warnings.append("Dataset identity, units and acquisition order are caller declarations; "
                    "schema matching does not establish machine provenance or held-out accuracy.")
    return AnalyzeRulResponse(
        stages=stages.as_list(), compatibility=gate.compatibility, model=gate.model,
        preprocessing_version=FEMTO_PREPROCESSING_VERSION,
        rul_seconds=prediction.rul_seconds, rul_hours=prediction.rul_hours,
        health_indicator_produced=health is not None, health=health, warnings=warnings,
        reliability=prediction.reliability,
        supporting={"latest_features": rows[-1], "latest_sequence_index": len(rows) - 1,
                    "recordings": len(rows), "sampling": axes[0].sampling,
                    "window": axes[0].window, "units": units,
                    "hi_model_version": _model_provenance(
                        "predict_hi", "reference_hi_model.joblib")[0]})


# Vercel's Python runtime forwards the original request path (e.g. /api/health)
# to this function unchanged - it does not strip the /api prefix the way a
# typical reverse-proxy rewrite would. Mounting the unprefixed `app` under /api
# in a separate wrapper keeps local dev (`uvicorn bearing_pdm.api:app`, routes
# at /health) and the test suite (imports `app` directly) on unprefixed paths,
# while api/index.py imports `vercel_app` for the actual deployed function.
vercel_app = FastAPI()
vercel_app.mount("/api", app)
