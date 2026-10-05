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
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from bearing_pdm import artifacts, reliability
from bearing_pdm.adapters import ADAPTERS, VIBRATION_CHANNELS
from bearing_pdm.applicability import MEDIUM_SHIFT_RATIO
from bearing_pdm.applicability import assess as applicability_assess
from bearing_pdm.features import frequency_domain_features, time_domain_features
from bearing_pdm.femto import ACC_COLUMNS
from bearing_pdm.health import apply_reference_hi
from bearing_pdm.history import configured_history_store
from bearing_pdm.profiler import MAX_SAMPLING_RATE_HZ, SAMPLING_RTOL, profile_file, sampling_info
from bearing_pdm.routing import MAX_NAN_FRACTION, candidates_from_bundle
from bearing_pdm.stages import assign_stages

CROSS_DOMAIN_BUNDLE_NAME = "cross_domain_bundle.joblib"

# FEMTO's acc_*.csv is a fixed, headerless, positional 6-column layout at a
# known sampling rate (femto.py's own docstring) - this is a *known adapter*
# the user is explicitly asserting applies (dataset_id="femto"), not a guess
# from column names the way /dataset/inspect works. ml-data.md: never guess
# sampling frequency - this one is a documented constant of a named format,
# not inferred from the upload.
FEMTO_SAMPLE_RATE_HZ = 25600.0
# The applicability reference population is fitted on FEMTO's acquisition
# window (2560 samples). Several features (total_spectral_energy, min/max,
# peak-to-peak, crest factor, spectral resolution) scale with window length,
# so scoring a differently-sized window against that reference compares
# apples to oranges regardless of how in-domain the signal itself is - found
# in review: two real, individually-HIGH fixture acquisitions concatenated
# into one longer file scored MEDIUM purely from length. Any generic upload
# must be chopped into this same window size before extraction, never
# treated as one arbitrarily-long window.
#
# It is also the exact row count of one raw acquisition accepted by
# /predict/rul/femto-acquisition (the femto-acquisition-v1 contract that
# /analyze/rul enforces too): the model's features were computed on complete
# 2560-sample acquisitions, so a shorter or longer file would feed it
# length-dependent features it was never trained on.
FEMTO_ACQUISITION_SAMPLES = 2560

REPO_ROOT = Path(__file__).resolve().parents[2]
# Every artifact is resolved through artifacts.ensure_artifact (which reads
# artifacts.MODELS_DIR, then the checksum-verified manifest fetch path); this
# alias only documents the default location for local checks.
MODELS_DIR = artifacts.MODELS_DIR
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
_SAMPLE_RATE_TOLERANCE = SAMPLING_RTOL  # 1% - real hardware clocks drift slightly

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
    """Structural compatibility state, reasons and the machine-readable required
    action for the uploaded file, from profile_file's output only - see goals.md's
    fail-closed dataset-state requirement. This is the column/header-level check
    /analyze/features uses; /dataset/inspect layers the sampling-rate, units and
    applicability.py model-domain checks on top of it (_classify_for_model).
    On its own it cannot decide RETRAIN_REQUIRED - see docs/dataset-compatibility.md."""
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
    usable = _usable_vibration_columns(vibration_cols)
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


def _usable_vibration_columns(columns: list[dict]) -> list[dict]:
    return [
        c for c in columns
        if c["canonical"] in _REQUIRED_ANY
        and c["numeric"] and not c["constant"]
        and c["nan_fraction"] <= MAX_NAN_FRACTION and c["inf_count"] == 0
    ]


def _applicability_candidate(dataset_id: str):
    """The routing candidate (fitted RUL model + its matching fitted
    applicability.ApplicabilityModel) whose training domain this dataset_id
    is. Only 'femto' has a feature-extraction path wired up anywhere in this
    module (_extract_femto_acquisition_features / _extract_generic_vibration_features),
    so that's the only id this resolves. None (never a guess) when the
    cross-domain bundle artifact itself is missing - the caller degrades
    gracefully, it does not silently claim HIGH applicability instead."""
    if dataset_id != "femto":
        return None
    bundle = _load_bundle()
    if bundle is None:
        return None
    for cand in candidates_from_bundle(bundle):
        if cand.name == "raw_seconds":
            return cand
    return None


def _assess_applicability(
    features: dict[str, float] | list[dict[str, float]], dataset_id: str
) -> dict | None:
    """Real model-domain compatibility - reuses applicability.py's own
    HIGH/MEDIUM/LOW decision exactly as routing.py does for the batch
    pipeline, not reimplemented here. None only when the fitted
    candidate/bundle itself is unavailable.

    `single_recording=True` (applicability.assess's own missing-feature
    semantics: "fraction of this row's features present", not a whole-run
    "worst column across many rows") is used whenever there is exactly ONE
    acquisition-sized row to score - whether that arrived as a single dict
    (e.g. the raw FEMTO upload endpoint) or a one-element list (a generic
    upload exactly one window long, see _extract_generic_vibration_features).
    Review found these two single-row cases must be scored identically -
    keying off `isinstance(features, dict)` alone gave a 2560-row upload a
    different (wrong, harsher) missing-feature penalty than the same feature
    row submitted as a dict. Only a genuine multi-window list (more than one
    recording of one run) uses the normal single_recording=False path."""
    candidate = _applicability_candidate(dataset_id)
    if candidate is None:
        return None
    cols = list(candidate.applicability.feature_columns)
    rows = [features] if isinstance(features, dict) else features
    df = pd.DataFrame([{c: row.get(c, np.nan) for c in cols} for row in rows], dtype=float)
    result = applicability_assess(df, candidate.applicability, single_recording=len(rows) == 1)
    return {
        "level": result["level"],
        "shift_ratio": result["shift_ratio"],
        "reasons": result["reasons"],
        "missing_features": result["missing_features"],
        "partial_features": result["partial_features"],
    }


def _extract_generic_vibration_features(
    path: Path, profile: dict, sampling_rate_hz: float
) -> tuple[list[dict[str, float]], int]:
    """The same features.py functions _extract_femto_acquisition_features uses,
    generalised from FEMTO's fixed positional columns to whichever high-confidence,
    usable vibration column(s) a header-based file has - profile_file has already
    identified which columns those are and confirmed they're numeric/non-constant/
    mostly-present; this only reads their real values and extracts features from
    them, it does not re-decide which columns are usable.

    Chopped into FEMTO_ACQUISITION_SAMPLES-sized windows so a longer upload is
    scored as several acquisition-sized recordings, not one arbitrarily long
    window whose length-dependent features (energy, peak-to-peak, spectral
    resolution) would not be comparable to the training reference regardless
    of how in-domain the signal itself is. A file SHORTER than one window is
    never scored here at all (that length mismatch is exactly the same
    artifact in the other direction) - the caller checks row count first and
    skips calling this when too short. Returns (one dict per full window,
    count of trailing rows that didn't fill a full window and were dropped -
    the caller must disclose that, never drop data silently)."""
    delimiter = profile.get("delimiter")
    sep = r"\s+" if delimiter in (None, "whitespace") else delimiter
    df = pd.read_csv(path, sep=sep, header=0)
    usable_cols = _usable_vibration_columns(profile.get("columns", []))
    if not usable_cols:
        return [], 0

    n = len(df)
    window = FEMTO_ACQUISITION_SAMPLES
    n_windows = n // window
    windows: list[dict[str, float]] = []
    for i in range(n_windows):
        start = i * window
        row: dict[str, float] = {}
        for col in usable_cols:
            axis = col["canonical"].rsplit("_", 1)[-1]  # vibration_x -> x
            signal = pd.to_numeric(
                df[col["name"]].iloc[start:start + window], errors="coerce"
            ).to_numpy()
            row.update(time_domain_features(signal, f"vibration_{axis}"))
            row.update(frequency_domain_features(signal, sampling_rate_hz, f"vibration_{axis}"))
        windows.append(row)
    return windows, n - n_windows * window


def _classify_for_model(
    profile: dict,
    path: Path,
    declared_sampling_rate_hz: float | None = None,
    declared_units: str | None = None,
) -> tuple[str, list[str], dict[str, Any], dict[str, Any]]:
    """(state, reasons, required action, sampling) for /dataset/inspect: the
    structural check above, plus (for the sampling-rate/units steps only) the
    caller's own declaration or regular timestamps in seconds already in the
    file - never guessed. Once sampling rate/units are resolved and match a
    trained model's domain, this also runs the real applicability.py
    model-domain check (extracting features from the usable vibration
    column(s), windowed to the training acquisition size) rather than treating
    a matching rate alone as sufficient - see docs/dataset-compatibility.md."""
    # Sampling evidence is reported for every readable file (goals.md: detect or
    # obtain sampling information), whatever the structural verdict below.
    sampling = sampling_info(profile, path)
    if declared_sampling_rate_hz is not None and sampling["source"] != "timestamps":
        sampling = sampling | {
            "rate_hz": declared_sampling_rate_hz, "source": "user", "required": False,
            "message": (
                "Declared sampling rate as supplied; the file's own timestamps are irregular "
                "or invalid, so it is not accepted for analysis."
                if sampling["regular"] is False else
                "Declared sampling rate (declared_sampling_rate_hz); it is not cross-checked "
                "against timing data in the file."),
        }
    state, reasons, action = _classify_detailed(profile)
    if state != FULLY_SUPPORTED:
        return state, reasons, action, sampling

    # Everything above is structural (can the columns be read at all). Below
    # is the scientific question ml-data.md requires: is this file's sampling
    # rate/units known, and if so, does any trained model actually cover it?
    # Neither is ever inferred from the data's shape or scale - only from
    # regular timestamps in seconds already in the file (profiler.sampling_info,
    # the same rule /analyze/features uses), or the caller's own declaration.
    declared_units = declared_units.strip() if declared_units else declared_units
    if sampling["regular"] is False:
        return ADAPTER_REQUIRED, [
            "the file's timestamp column is invalid or irregular (every interval must be "
            "within 1% of the median) - its sampling rate cannot be established, and a "
            "declaration cannot override the file's own timing evidence"
        ], _action(
            "TIMESTAMPS_IRREGULAR",
            "The file's own timestamps are irregular or invalid, so no sampling rate can be "
            "justified from them. Resolve the timing in the file (or remove the column and "
            "declare the rate) before analysis.",
            ["regular timestamps in seconds, or no timestamp column plus declared_sampling_rate_hz"],
        ), sampling

    derived_rate = sampling["rate_hz"] if sampling["source"] == "timestamps" else None
    timing_notes: list[str] = []
    # Real evidence (regular timestamps already in the file) always wins over
    # a declaration - a declared rate is only a fallback for when there is no
    # such evidence, never a way to override it (found in review: declaring a
    # rate that contradicted the file's own timestamps silently produced
    # FULLY_SUPPORTED, exactly the guess ml-data.md forbids).
    if derived_rate is not None:
        sampling_rate_hz, rate_source = derived_rate, "the file's timestamp column (seconds)"
        if (
            declared_sampling_rate_hz is not None
            and abs(declared_sampling_rate_hz - derived_rate) > _SAMPLE_RATE_TOLERANCE * derived_rate
        ):
            return ADAPTER_REQUIRED, [
                f"declared_sampling_rate_hz={declared_sampling_rate_hz:.1f} conflicts with the rate "
                f"derived from {rate_source} ({derived_rate:.1f} Hz) - the file's "
                "own evidence is used, not the declaration; fix the declaration or the file"
            ], _action(
                "SAMPLING_RATE_CONFLICT",
                "The declared sampling rate disagrees with the file's own timestamps by more "
                "than 1%. Correct whichever is wrong; the file's evidence is never silently "
                "overridden.",
                ["a declared_sampling_rate_hz that agrees with the file's timestamps (1%)"],
            ), sampling
    else:
        sampling_rate_hz, rate_source = declared_sampling_rate_hz, "declared_sampling_rate_hz"
        timestamp_cols = [c["name"] for c in profile.get("columns", [])
                          if c["canonical"] == "timestamp"]
        if timestamp_cols:
            # Seconds are never assumed from a generic name like "time" (it could
            # be milliseconds or sample indices) - say so instead of guessing.
            timing_notes.append(
                f"timestamp column {timestamp_cols[0]!r} was not used to derive or cross-check "
                "the sampling rate: only a column named time_s/seconds, or ISO datetimes, are "
                "read as seconds")

    missing_metadata = []
    if sampling_rate_hz is None:
        missing_metadata.append(
            "sampling rate unknown: no regular timestamp column in seconds and no "
            "declared_sampling_rate_hz - frequency-domain features cannot be computed without it"
        )
    if not declared_units:
        missing_metadata.append(
            "units not declared (declared_units) - this project keeps no verified units "
            "contract to check a declaration against, but requires one for traceability "
            "before a prediction is made"
        )
    if missing_metadata:
        missing = []
        if sampling_rate_hz is None:
            missing.append("declared_sampling_rate_hz (or regular timestamps in a time_s column)")
        if not declared_units:
            missing.append("declared_units")
        return ADAPTER_REQUIRED, missing_metadata + timing_notes, _action(
            "METADATA_REQUIRED",
            "The vibration columns are usable, but the sampling rate and/or units are not "
            "established. They are never guessed: declare them, or include regular timestamps "
            "in seconds.",
            missing,
        ), sampling

    rate_model_id = None
    for model_id, model_rate_hz in _KNOWN_MODEL_SAMPLE_RATES_HZ.items():
        if abs(sampling_rate_hz - model_rate_hz) <= _SAMPLE_RATE_TOLERANCE * model_rate_hz:
            rate_model_id = model_id
            break
    if rate_model_id is None:
        return RETRAIN_REQUIRED, [
            f"sampling rate {sampling_rate_hz:.1f} Hz (source: {rate_source}) does not match any "
            f"trained model's domain ({', '.join(f'{k}: {v:.1f} Hz' for k, v in _KNOWN_MODEL_SAMPLE_RATES_HZ.items())}). "
            "The vibration channel(s) and metadata are structurally usable, but no existing model "
            "was fit at this rate - this machine/configuration would need a model trained for it, "
            "not just a parsing adapter."
        ] + timing_notes, _action(
            "RETRAIN_REQUIRED",
            "No existing model was trained at this sampling rate. A model trained and validated "
            "at this rate is required; this service never retrains automatically.",
            [f"a model trained and validated at {sampling_rate_hz:g} Hz"],
        ), sampling

    rate_reason = (
        f"sampling rate {sampling_rate_hz:.1f} Hz (source: {rate_source}) matches the "
        f"{rate_model_id} model's trained rate ({_KNOWN_MODEL_SAMPLE_RATES_HZ[rate_model_id]:.1f} Hz)"
    )

    # A matching sampling rate alone does not mean the signal itself looks
    # like what the model was trained on - this is exactly the real
    # model-domain check applicability.py exists for (a sensor reading
    # plausible numbers at the right rate can still be statistically nothing
    # like a bearing in this model's training population). Never skipped in
    # favour of the rate check alone.
    #
    # A file shorter than one training-sized window can't be scored at all
    # without hitting the same length-vs-reference mismatch windowing exists
    # to avoid (found in review: a short, genuinely in-domain file scored
    # LOW purely from being short, not from looking out-of-domain). Degrade
    # honestly instead of guessing - same pattern as "bundle unavailable".
    n_rows = profile.get("rows", 0)
    dropped_rows = 0
    if n_rows < FEMTO_ACQUISITION_SAMPLES:
        applicability = None
        unavailable_reason = (
            f"model applicability could not be assessed: {n_rows} rows is less than the "
            f"{FEMTO_ACQUISITION_SAMPLES}-sample window the reference population is fitted on - "
            "this result reflects sampling-rate compatibility only, not a real domain-fit check"
        )
    else:
        try:
            windows, dropped_rows = _extract_generic_vibration_features(path, profile, sampling_rate_hz)
        except (pd.errors.ParserError, ValueError, KeyError, OverflowError):
            windows = []
        applicability = _assess_applicability(windows, rate_model_id) if windows else None
        unavailable_reason = (
            "model applicability could not be assessed (cross_domain_bundle.joblib missing, "
            "unreadable, or feature extraction failed) - this result reflects sampling-rate "
            "compatibility only, not a real domain-fit check"
        )

    dropped_reason = (
        [f"{dropped_rows} trailing row(s) did not fill a full {FEMTO_ACQUISITION_SAMPLES}-sample "
         "window and were not scored"]
        if dropped_rows else []
    )
    supported_message = (
        "Usable vibration channel(s), a sampling rate matching the {model} model's trained rate, "
        "and declared units{applicability}. This is a dataset-level check, not a validation of "
        "any prediction; declared units are trusted, not verified."
    )

    if applicability is None:
        return FULLY_SUPPORTED, [rate_reason, unavailable_reason] + dropped_reason + timing_notes, _action(
            "NONE",
            supported_message.format(
                model=rate_model_id,
                applicability=" - model applicability could NOT be assessed (see reasons)"),
            [],
        ), sampling
    if applicability["level"] == "HIGH":
        return FULLY_SUPPORTED, [rate_reason] + dropped_reason + timing_notes + applicability["reasons"], _action(
            "NONE",
            supported_message.format(model=rate_model_id,
                                     applicability=", with HIGH model applicability"),
            [],
        ), sampling

    # Attribute the downgrade to its real cause: an elevated feature-distribution
    # shift, missing features (the applicability missing-feature cap can force
    # MEDIUM/LOW even when the shift ratio itself is small), or both - found in
    # review: a message that always blames "the signal itself" was misleading
    # when the true cause was a sensor channel this upload simply lacks.
    causes = []
    if applicability["shift_ratio"] > MEDIUM_SHIFT_RATIO:
        causes.append(f"feature distribution shift ({applicability['shift_ratio']:.2f}x the in-domain reference)")
    if applicability["missing_features"]:
        causes.append(f"{len(applicability['missing_features'])} missing model feature(s)")
    if applicability["partial_features"]:
        # A feature missing in 10-50% of windows caps the level via
        # applicability.py's _missing_cap without ever appearing in
        # missing_features (that list is only >50%-missing) - found in
        # review: a multi-window upload with a channel that drops out
        # partway through could fall into neither bucket above, producing
        # a vacuous "due to the applicability check" message.
        causes.append(f"{len(applicability['partial_features'])} partly missing model feature(s)")
    cause_text = " and ".join(causes) if causes else "the applicability check"
    return RETRAIN_REQUIRED, [
        rate_reason,
        f"sampling rate matches, but model applicability is {applicability['level']} due to "
        f"{cause_text} - a matching rate alone does not make this dataset supported",
    ] + dropped_reason + timing_notes + applicability["reasons"], _action(
        "RETRAIN_REQUIRED",
        f"The signal does not look like the {rate_model_id} model's training population "
        f"(applicability {applicability['level']}). A model trained and validated on data "
        "like this is required; this service never retrains automatically.",
        [f"a model trained and validated on data like this (applicability "
         f"{applicability['level']}: {cause_text})"],
    ), sampling


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


def _json_safe(value: Any) -> Any:
    """Stringify non-finite floats (e.g. an echoed NaN `input` or `ctx` limit),
    which strict JSON cannot represent and JSONResponse refuses to encode."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return value


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
        422, "VALIDATION_ERROR", _json_safe(jsonable_encoder(errors)),
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
    "/predict/rul/femto-acquisition": "predict_rul_femto_acquisition",
    "/predict/rul/femto-acquisition/blob": "predict_rul_femto_acquisition_blob",
    "/predict/hi": "predict_hi",
    "/predictions/history": "prediction_history",
    "/dataset/inspect": "dataset_inspect",
    "/dataset/inspect/blob": "dataset_inspect_blob",
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

# Durable prediction history behind an interface (docs/prediction-history.md):
# process-local by default, SQLite when RULGUARD_HISTORY_DB is set. Records are
# bounded summaries - never raw sensor data, feature values or filenames.
_history_store = configured_history_store()
_MODEL_VERSIONS: dict[str, str] = {}
# Set while one public request (e.g. /analyze/rul) reuses the /predict/* route
# functions internally, so that request produces exactly one history record
# describing its own outcome rather than one per internal call.
_HISTORY_SUPPRESSED: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "bearing_pdm_history_suppressed", default=False
)


def _fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _file_fingerprint(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(UPLOAD_CHUNK_BYTES):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


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


@contextmanager
def _history_entry(kind: str, artifact: str, request_summary: dict[str, Any],
                   input_fingerprint: str, supported: bool):
    """One bounded history record per prediction request, written on success
    AND failure (a failed request is distinguishable by status/error_code). The
    caller fills `result`, `warnings` and `compatibility_state` on success."""
    record: dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "timestamp": datetime.now(UTC).isoformat(),
        "kind": kind,
        "request": request_summary,
        "input_fingerprint": input_fingerprint,
        "model_version": None,
        "feature_schema_version": None,
        "compatibility_state": "NOT_EVALUATED" if supported else UNSUPPORTED,
        "status": "failed",
        "warnings": [],
        "result": None,
    }
    try:
        yield record
        record["status"] = "succeeded"
    except ApiError as exc:
        record["error_code"] = exc.code
        declared = (exc.extra or {}).get("compatibility")
        if declared:
            record["compatibility_state"] = declared
        elif exc.status_code == 422 and exc.code != "UNSUPPORTED_DATASET":
            record["compatibility_state"] = INVALID_INPUT
        raise
    except Exception:
        record["error_code"] = "INTERNAL_ERROR"
        raise
    finally:
        if supported:
            record["model_version"], record["feature_schema_version"] = (
                _model_provenance(kind, artifact)
            )
        if not _HISTORY_SUPPRESSED.get():
            try:
                _history_store.append(record)
            except Exception as exc:
                _note(exc_type=type(exc).__name__)
                raise ApiError(503, "HISTORY_UNAVAILABLE",
                               "Prediction history could not be saved.", retryable=True) from None


def _rul_history_result(record: dict[str, Any], response: PredictRulResponse) -> None:
    record["compatibility_state"] = response.compatibility
    record["result"] = {
        "rul_hours": response.rul_hours,
        "n_features_missing": len(response.features_missing),
        "applicability_level": response.applicability_level,
    }
    if response.features_missing:
        record["warnings"].append("MISSING_FEATURES_MEDIAN_FILLED")
    if response.applicability_level is None:
        record["warnings"].append("APPLICABILITY_NOT_ASSESSED")
    elif response.applicability_level != "HIGH":
        record["warnings"].append(f"APPLICABILITY_{response.applicability_level}")


def _track_prediction(kind: str, artifact: str):
    def decorate(func):
        @wraps(func)
        def tracked(request):
            summary: dict[str, Any] = {"dataset_id": "femto" if request.dataset_id == "femto" else "other"}
            if kind == "predict_rul":
                summary["n_features_provided"] = len(request.features)
            else:
                summary["n_rows"] = len(request.rows)
            with _history_entry(kind, artifact, summary, _fingerprint(request.model_dump()),
                                supported=request.dataset_id == "femto") as record:
                response = func(request)
                if kind == "predict_rul":
                    _rul_history_result(record, response)
                else:
                    record["compatibility_state"] = FULLY_SUPPORTED
                    record["result"] = {
                        "latest_hi": response.rows[-1].health_indicator,
                        "latest_stage": response.rows[-1].stage,
                    }
                    record["warnings"].append("HI_STAGE_IS_SEVERITY_NOT_FAULT_DIAGNOSIS")
                return response
        return tracked
    return decorate


_load_locks: dict[str, threading.Lock] = {}
_load_locks_guard = threading.Lock()


def _lock_for_load(name: str) -> threading.Lock:
    with _load_locks_guard:
        return _load_locks.setdefault(name, threading.Lock())


def _load_joblib(name: str) -> Any | None:
    """Same missing-artifact contract as dashboard._load_joblib: None, never
    a traceback, cached in-process rather than per-request.

    artifacts.ensure_artifact resolves `name` to a local path - either
    already present in the repo (local dev), or fetched and checksum-
    verified against artifacts/models/manifest.json (a real Vercel
    deployment, where these gitignored binaries are never in the Git
    checkout - see docs/vercel-deployment.md). A manifest entry without a
    usable source_url, or a checksum mismatch, resolves to None here same
    as a file that was simply never present - never a guess, never a
    silently-wrong model. The loaded file's sha256 is recorded as its
    model version (history, access log, /health).

    Serialized per name (FastAPI's sync `def` endpoints run in a thread
    pool, so two cold requests for the same uncached name genuinely race):
    without this lock, two threads can both receive the same path from
    artifacts.ensure_artifact, and one thread's post-load file deletion
    (below) can remove the file before the other thread's own path.open()
    runs, raising FileNotFoundError instead of loading cleanly. The
    double-checked _MODEL_CACHE read (outside, then again inside the lock)
    means only the first caller for a given name ever does the actual
    download/load/delete work; every other concurrent or later caller just
    returns the cached model."""
    if name in _MODEL_CACHE:
        return _MODEL_CACHE[name]
    with _lock_for_load(name):
        if name in _MODEL_CACHE:
            return _MODEL_CACHE[name]
        return _load_joblib_locked(name)


def _load_joblib_locked(name: str) -> Any | None:
    try:
        path = artifacts.ensure_artifact(name)
    except OSError:
        # Defense in depth: ensure_artifact already fails closed internally
        # (e.g. a download-time OSError), but a filesystem failure in
        # _cache_dir()'s own mkdir (a read-only /tmp, disk full before any
        # download starts) happens before that try block and would
        # otherwise surface as an unhandled 500 instead of the same 503
        # every other missing-artifact case produces.
        logger.warning("Artifact lookup failed with a filesystem error")
        return None
    if path is None:
        return None
    with path.open("rb") as stream:
        _MODEL_VERSIONS[name] = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
    model = joblib.load(path)
    _MODEL_CACHE[name] = model
    if path.parent != artifacts.MODELS_DIR:
        # path is a downloaded cache copy (artifacts._cache_dir()), not the
        # repo-checked-out local dev copy under MODELS_DIR - never delete that
        # one. Once loaded, the deserialized model lives in _MODEL_CACHE for
        # this process's whole life (the `if name in _MODEL_CACHE` fast path
        # above means this function never reads `path` again for this name),
        # so the on-disk copy is pure dead weight afterward. Freeing it here
        # is the direct fix for the Hobby-tier /tmp ENOSPC documented in
        # docs/PRODUCTION_RELEASE.md: rul_extra_trees.joblib (108MB) and
        # cross_domain_bundle.joblib (219MB) together exceed the tier's /tmp
        # budget only if BOTH their downloaded copies are kept on disk at
        # once after both are already safely in memory - deleting each one
        # right after its own load means at most one artifact's download is
        # ever resident on disk at a time (plus brief overlap with a
        # concurrent request's own in-flight download of a different name).
        # A deletion failure (e.g. already gone) is never fatal - the model
        # is already safely in memory regardless.
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove the cached download for %s after loading it", name)
    return model


def _load_bundle() -> Any | None:
    """The cross-domain bundle (~200MB): supplies only the cached applicability
    model and conformal calibrator; its models are never used for the served
    prediction. Loaded once per process through the same verified loader.

    Only bundle["raw_seconds"] is ever read anywhere this is called from
    (routing.candidates_from_bundle filters to "raw_seconds"; reliability.py's
    BUNDLE_ENTRY is "raw_seconds") - the bundle's other entry,
    "sn_fraction_multi", carries its own full fitted RUL model + calibrators
    and is dead weight here. Dropping it immediately after load (rather than
    holding the whole dict in _MODEL_CACHE for a warm instance's lifetime)
    roughly halves this artifact's resident memory - the suspected cause of
    the applicability/OOD gate failing to load on the Hobby tier's /tmp+memory
    budget alongside rul_extra_trees.joblib (docs/PRODUCTION_RELEASE.md)."""
    bundle = _load_joblib(CROSS_DOMAIN_BUNDLE_NAME)
    if isinstance(bundle, dict) and set(bundle) - {"raw_seconds"}:
        bundle = {"raw_seconds": bundle["raw_seconds"]}
        _MODEL_CACHE[CROSS_DOMAIN_BUNDLE_NAME] = bundle
    return bundle


# Direct-to-storage uploads (frontend -> Vercel Blob -> this API) only ever
# name an object this deployment's own client-upload token minted - never an
# arbitrary caller-supplied URL (security.md: validate caller-supplied
# paths/URLs, no open proxy/SSRF). ALLOW_LOCAL_BLOB_HOSTS is an opt-in escape
# hatch for tests/local dev only, never set in a deployed environment.
#
# BLOB_STORE_HOSTNAME (set once a real Blob store is connected - see
# docs/vercel-deployment.md) pins this to THIS PROJECT's own store exactly.
# Without it, every *.blob.vercel-storage.com host is accepted - that
# suffix is shared by every Vercel customer's store, not just this
# project's, so this fallback is deliberately looser (review flagged this:
# it lets the backend fetch/delete another customer's public blob, not
# true internal-network SSRF since Blob objects are public HTTPS URLs, but
# still not a real identity check). Deploy with BLOB_STORE_HOSTNAME set.
_BLOB_HOST_SUFFIXES = (".public.blob.vercel-storage.com", ".blob.vercel-storage.com")


def _get_http_client() -> httpx.Client:
    """Seam for tests to substitute a MockTransport instead of a real
    network call - see tests/test_api_blob.py. follow_redirects is left at
    its httpx default (False) deliberately - a redirect must never be able
    to carry a validated blob_url to a host that bypassed validation."""
    return httpx.Client(timeout=30.0)


def _validate_blob_url(url: str) -> None:
    # urlsplit silently drops ASCII control characters (tab/CR/LF) from a
    # hostname instead of erroring, which let a crafted
    # "https://evil.com\t.blob.vercel-storage.com/x" pass this check and
    # then crash httpx.Client.stream() with httpx.InvalidURL (a 500, not a
    # clean 422) - found in review. Reject any such character up front.
    if any(ord(ch) < 0x20 for ch in url):
        raise ApiError(422, "INVALID_BLOB_URL", "blob_url contains invalid characters.")

    parsed = urlsplit(url)
    # Read live, not cached at import time, so a test can toggle this via
    # monkeypatch.setenv without needing to reimport the module.
    allow_local = os.environ.get("ALLOW_LOCAL_BLOB_HOSTS") == "1"
    if allow_local and parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"):
        return
    if parsed.scheme != "https":
        raise ApiError(422, "INVALID_BLOB_URL", "blob_url must be an https URL.")

    pinned_host = os.environ.get("BLOB_STORE_HOSTNAME")
    if pinned_host:
        if parsed.hostname != pinned_host:
            raise ApiError(
                422, "INVALID_BLOB_URL",
                "blob_url is not an object in this deployment's own Blob store.",
            )
        _reject_model_artifact_path(parsed.path)
        return
    if not (parsed.hostname and any(parsed.hostname.endswith(suf) for suf in _BLOB_HOST_SUFFIXES)):
        raise ApiError(
            422, "INVALID_BLOB_URL",
            "blob_url must be an https *.blob.vercel-storage.com object, not an arbitrary URL.",
        )
    _reject_model_artifact_path(parsed.path)


def _reject_model_artifact_path(path: str) -> None:
    """The deployment's trained model artifacts live in the same public Blob
    store (under models/) as user uploads, at URLs published in
    artifacts/models/manifest.json. Without this check, anyone could pass
    one of those URLs as blob_url to a predict/inspect route and have it
    deleted by the existing finally: _delete_blob(...) - an unauthenticated
    way to destroy production model artifacts, with no credentials needed
    (independent review finding, HIGH). These routes only ever legitimately
    receive a user-uploaded dataset file, never anything under models/."""
    if path.lstrip("/").startswith("models/"):
        raise ApiError(
            422, "INVALID_BLOB_URL",
            "blob_url may not reference this deployment's model artifacts.",
        )


class BlobUploadRequest(BaseModel):
    blob_url: str = Field(..., description="A client-uploaded Vercel Blob object URL.")


def _stream_blob_to_tempfile(blob_url: str, tmp, max_bytes: int) -> int:
    """Bounded-memory download of a direct-to-storage upload (python.md:
    'all raw reads are chunked') - this server never buffers the whole
    object in memory, the same chunked pattern as the direct upload path
    (_spool_upload), including its text-head check on the first bytes. A
    missing object (expired/already cleaned up) and a connection dropping
    mid-transfer are reported as distinct, truthful error states rather
    than one generic failure."""
    written = 0
    try:
        with _get_http_client() as client, client.stream("GET", blob_url) as response:
            if response.status_code == 404:
                raise ApiError(
                    404, "UPLOAD_NOT_FOUND",
                    "Uploaded object not found - it may have expired or already been "
                    "cleaned up. Please re-upload.",
                )
            if response.status_code >= 400:
                raise ApiError(
                    502, "STORAGE_FETCH_FAILED",
                    f"Could not fetch the uploaded object (storage returned {response.status_code}).",
                    retryable=True,
                )
            for chunk in response.iter_bytes(UPLOAD_CHUNK_BYTES):
                if written == 0 and chunk:
                    _check_text_head(chunk)
                written += len(chunk)
                if written > max_bytes:
                    raise ApiError(
                        413, "UPLOAD_TOO_LARGE",
                        f"Uploaded object exceeds the {max_bytes // (1024 * 1024)}MB limit.",
                    )
                tmp.write(chunk)
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        # httpx.InvalidURL is not an httpx.HTTPError subclass (verified in
        # review) - a URL that passed _validate_blob_url's hostname check
        # but still isn't well-formed enough for httpx to request (e.g. a
        # stray non-ASCII byte) must still fail clean, not 500.
        _note(exc_type=type(exc).__name__)
        raise ApiError(
            502, "STORAGE_FETCH_FAILED",
            "Upload was interrupted while downloading from storage. Retry the request.",
            retryable=True,
        ) from None
    tmp.flush()
    if written == 0:
        raise ApiError(422, "EMPTY_UPLOAD", "Uploaded object is empty.")
    return written


def _delete_blob(blob_url: str) -> None:
    """Best-effort upload-lifecycle cleanup: once a direct-to-storage upload
    has been processed (successfully or not), it has no further purpose and
    left behind is a stale object taking up storage. Never raises - a failed
    cleanup must not turn a successful prediction/inspection into an error.
    Never logs the URL (it carries the uploaded filename) or the token."""
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not token:
        return
    try:
        with _get_http_client() as client:
            response = client.post(
                "https://blob.vercel-storage.com/delete",
                json={"urls": [blob_url]},
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400:
            # client.post doesn't raise on a 4xx/5xx body - a failed delete
            # (e.g. the token lacks access, or the API changed) was
            # otherwise silently swallowed.
            _note(blob_cleanup="failed")
            logger.warning("Blob delete request returned %s", response.status_code)
        else:
            _note(blob_cleanup="deleted")
    except httpx.HTTPError as exc:
        _note(blob_cleanup="failed")
        logger.warning("Failed to delete blob after processing (%s)", type(exc).__name__)


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
    compatibility: str = FULLY_SUPPORTED
    applicability_level: str | None = None
    applicability_shift_ratio: float | None = None
    applicability_reasons: list[str] = Field(default_factory=list)
    # Goal 21 (docs/prediction-reliability.md): held-out error, tree disagreement,
    # conformal interval and applicability, each traced to a file or computation
    # and null-with-reason when unavailable. Never a confidence or probability.
    reliability: dict[str, Any] | None = None


def _reliability(model: Any, x: Any, features: dict[str, float], prediction: float) -> dict:
    """Reliability block; an unexpected failure withholds it (with a reason)
    rather than failing a prediction that was itself computed correctly."""
    try:
        return reliability.build(METRICS_DIR / "rul_evaluation.json", _load_bundle(), model,
                                 "extra_trees", x, features, prediction, single_recording=True)
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
    return json.loads(path.read_text())


@app.get("/models/info")
def models_info() -> dict[str, Any]:
    # Routed through artifacts.ensure_artifact, not a direct MODELS_DIR
    # read - review found this was the one place still bypassing it, which
    # would have left selected_model permanently null on a deployment that
    # only has the manifest's fetch path (no local checkout of the file).
    selected_path = artifacts.ensure_artifact("rul_selected_model.json")
    selected = json.loads(selected_path.read_text()) if selected_path is not None else None
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
        raise ApiError(
            503, "MODEL_UNAVAILABLE",
            "rul_extra_trees.joblib is missing. Run scripts/train_models.py first.",
            retryable=True,
        )
    _note_model("predict_rul", "rul_extra_trees.joblib", "extra_trees")

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
        raise ApiError(
            422, "FEATURES_MISSING",
            f"{len(missing)}/{len(model.feature_columns)} required features are missing "
            f"(max allowed {max_missing_fraction:.0%}). A prediction built mostly from "
            "training medians would not reflect the submitted sample.",
        )

    # Real model-domain compatibility (applicability.py, routing.py's own
    # decision rule) - a sampling-rate/column match upstream is not enough.
    # Assessed on the caller's own submitted values (pre-median-fill): the
    # question is whether what was actually measured looks like the training
    # population, not whether a filled-in row would.
    applicability = _assess_applicability(features, "femto")
    if applicability is not None and applicability["level"] == "LOW":
        _note(compatibility=RETRAIN_REQUIRED)
        raise ApiError(
            422, "APPLICABILITY_LOW",
            f"RUL suppressed: model applicability is LOW (shift ratio "
            f"{applicability['shift_ratio']:.2f}x the in-domain reference) - this signal does "
            "not look like the model's training population; a prediction here would not be "
            "reliable. Reasons: " + "; ".join(applicability["reasons"]),
            extra={"compatibility": RETRAIN_REQUIRED},
        )

    row = {
        c: features[c] if c not in missing else model.median_fill.get(c)
        for c in model.feature_columns
    }
    if any(v is None for v in row.values()):
        unresolvable = [c for c, v in row.items() if v is None]
        raise ApiError(
            422, "FEATURES_MISSING",
            f"Missing required features with no fallback median: {unresolvable}",
        )

    x = pd.DataFrame([row])[list(model.feature_columns)]
    try:
        prediction = float(model.model.predict(x)[0])
    except ValueError as exc:
        # Extreme-but-finite input (e.g. 1e300 raw samples) can still overflow
        # a derived feature like RMS to inf despite passing the raw-value
        # isfinite check upstream. Fail closed with 422, not a raw 500.
        raise ApiError(
            422, "NON_FINITE_FEATURES",
            f"Feature values are unusable for prediction: {exc}",
        ) from None
    if not math.isfinite(prediction):
        raise ApiError(503, "INVALID_MODEL_OUTPUT",
                       "The cached model did not produce a finite RUL.")

    applicability_level = applicability["level"] if applicability else None
    applicability_shift_ratio = applicability["shift_ratio"] if applicability else None
    if applicability is None:
        # Same honest-degrade pattern as _classify_for_model: never claim a
        # domain-fit check happened when it didn't. An earlier version left
        # `compatibility` at its FULLY_SUPPORTED default here - indistinguishable
        # from a real HIGH-applicability result even though domain-fit was never
        # checked at all. Reuse the existing RETRAIN_REQUIRED/"experimental"
        # contract (the same one MEDIUM applicability already uses) rather than
        # inventing a new state: whether the input is in-domain is unknown, not
        # confirmed, so the prediction must not be represented as fully validated.
        compatibility = RETRAIN_REQUIRED
        applicability_reasons = [
            "model applicability could not be assessed (cross_domain_bundle.joblib missing or "
            "unreadable) - treat this prediction as experimental, the same as MEDIUM "
            "applicability: whether the input is in-domain for this model is unknown, not "
            "confirmed"
        ]
    else:
        compatibility = FULLY_SUPPORTED
        applicability_reasons = applicability["reasons"]
    if applicability_level == "MEDIUM":
        compatibility = RETRAIN_REQUIRED
        applicability_reasons = [
            "model applicability is MEDIUM: prediction returned, but treat it as experimental "
            "- this configuration differs from the training population more than the model's "
            "own in-domain bearings do"
        ] + applicability_reasons
    _note(compatibility=compatibility)

    return PredictRulResponse(
        model_name="extra_trees",
        rul_seconds=prediction,
        rul_hours=prediction / 3600.0,
        features_used=list(model.feature_columns),
        features_missing=missing,
        compatibility=compatibility,
        applicability_level=applicability_level,
        applicability_shift_ratio=applicability_shift_ratio,
        applicability_reasons=applicability_reasons,
        reliability=_reliability(model, x, features, prediction),
    )


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
    return _predict_rul_from_features(request.features)


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


def _process_femto_acquisition_file(tmp_path: str, source: str) -> PredictRulResponse:
    """The validation + feature-extraction + prediction core shared by both
    the direct-multipart-upload endpoint and the direct-to-storage blob
    endpoint below. Both paths funnel through this single function so they
    are scientifically identical by construction - not two implementations
    that could silently drift apart (ml-data.md: chunked results must match
    the trusted reference pipeline). One history record per request, on
    success or failure, carrying only a content hash and the row count -
    never the filename or any sample value."""
    summary: dict[str, Any] = {"dataset_id": "femto", "source": source}
    with _history_entry("predict_rul_femto_acquisition", "rul_extra_trees.joblib", summary,
                        _file_fingerprint(tmp_path), supported=True) as record:
        try:
            raw = pd.read_csv(tmp_path, header=None, dtype="float64")
        except (ValueError, pd.errors.ParserError, pd.errors.EmptyDataError):
            raise ApiError(
                422, "MALFORMED_FILE",
                "Not a numeric, headerless FEMTO acc_*.csv file: every cell must be a number "
                f"and every row must have {len(ACC_COLUMNS)} columns.",
            ) from None
        summary["n_rows"] = int(raw.shape[0])

        if raw.shape[1] != len(ACC_COLUMNS):
            raise ApiError(
                422, "ADAPTER_REQUIRED",
                f"Expected {len(ACC_COLUMNS)} columns (FEMTO's fixed acc_*.csv layout: "
                f"{ACC_COLUMNS}), got {raw.shape[1]}. This is not a FEMTO acquisition file.",
                extra={"compatibility": ADAPTER_REQUIRED},
            )
        if raw.shape[0] != FEMTO_ACQUISITION_SAMPLES:
            raise ApiError(
                422, "INCOMPLETE_ACQUISITION",
                f"Got {raw.shape[0]} rows - a FEMTO acquisition is exactly "
                f"{FEMTO_ACQUISITION_SAMPLES} rows (0.1 s at 25.6 kHz), the window the model's "
                "features were computed on. Partial or concatenated acquisitions are never "
                "trimmed or padded; upload one complete acc_*.csv file.",
                extra={"compatibility": INVALID_INPUT},
            )
        vibration = raw[[4, 5]].to_numpy()
        if np.isnan(vibration).any():
            raise ApiError(
                422, "INCOMPLETE_ACQUISITION",
                f"{int(np.isnan(vibration).sum())} vibration sample(s) are missing. Samples are "
                "never dropped or filled before prediction.",
                extra={"compatibility": INVALID_INPUT},
            )
        if not np.isfinite(vibration).all():
            raise ApiError(
                422, "NON_FINITE_SIGNAL",
                "Non-finite (inf) values in the vibration columns are not allowed.",
                extra={"compatibility": INVALID_INPUT},
            )
        # The spectral features assume samples in acquisition order, and the
        # offline reader (femto.read_acceleration) rejects any missing cell,
        # timestamps included. Reordered rows leave every time-domain feature
        # unchanged but scramble the FFT, so a shuffled file would otherwise
        # get a confident RUL from a meaningless spectrum. Non-decreasing (not
        # strict) because the archive's %.5g-formatted microsecond field can
        # round adjacent samples to the same value; one midnight rollover is
        # unwrapped rather than rejected.
        clock = raw[[0, 1, 2, 3]].to_numpy()
        if not np.isfinite(clock).all():
            raise ApiError(
                422, "INVALID_TIMESTAMPS",
                "Every row needs a finite hour, minute, second and microsecond; the sample "
                "order of this acquisition cannot be verified without them.",
                extra={"compatibility": INVALID_INPUT},
            )
        steps = np.diff(clock @ np.array([3600.0, 60.0, 1.0, 1e-6]))
        steps = np.where(steps < -43200.0, steps + 86400.0, steps)
        if (steps < 0).any():
            raise ApiError(
                422, "SAMPLES_OUT_OF_ORDER",
                f"The row timestamps go backwards in {int((steps < 0).sum())} place(s). Samples "
                "must be in acquisition order; they are never re-sorted before feature "
                "extraction.",
                extra={"compatibility": INVALID_INPUT},
            )

        try:
            features = _extract_femto_acquisition_features(tmp_path)
        except OverflowError as exc:
            # Finite but extreme raw samples (e.g. a huge-amplitude signal)
            # can overflow a derived statistic (std**4 etc.) before any
            # feature value is even produced to check for non-finiteness -
            # found in review. Fail closed with 422, not a raw 500.
            raise ApiError(
                422, "NON_FINITE_FEATURES",
                f"Raw sample values are too extreme to extract features from: {exc}",
            ) from None

        response = _predict_rul_from_features(features)
        _rul_history_result(record, response)
        return response


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

    For a file too large for a normal request body, see the direct-to-storage
    /predict/rul/femto-acquisition/blob variant below.
    """
    with _temporary_upload() as tmp:
        await _spool_upload(file, tmp)
        return _process_femto_acquisition_file(tmp.name, "upload")


@app.post("/predict/rul/femto-acquisition/blob", response_model=PredictRulResponse)
def predict_rul_from_femto_acquisition_blob(request: BlobUploadRequest) -> PredictRulResponse:
    """Direct-to-storage counterpart of /predict/rul/femto-acquisition: the
    browser uploads the raw file straight to Vercel Blob (bypassing the
    platform's ~4.5MB serverless request-body limit) and only hands this
    endpoint the resulting object URL. Downloads it in MAX_UPLOAD_BYTES/
    UPLOAD_CHUNK_BYTES-bounded chunks, then runs the exact same
    _process_femto_acquisition_file the direct-upload path uses, and always
    deletes the now-unneeded blob afterward (lifecycle cleanup) whether
    processing succeeded or failed."""
    _validate_blob_url(request.blob_url)
    with _temporary_upload() as tmp:
        try:
            # Cleanup must cover the download itself, not just processing -
            # review found that an oversized/missing/interrupted download
            # (a 413/404/502 raised inside _stream_blob_to_tempfile) left
            # the blob behind forever, since _delete_blob previously sat in
            # a `finally` that only wrapped the step after this one.
            _stream_blob_to_tempfile(request.blob_url, tmp, MAX_UPLOAD_BYTES)
            return _process_femto_acquisition_file(tmp.name, "blob")
        finally:
            _delete_blob(request.blob_url)


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

    required_cols = [*reference_model.features, "sequence_index"]
    missing = [c for c in required_cols if any(c not in row for row in request.rows)]
    if missing:
        raise ApiError(
            422, "FEATURES_MISSING",
            f"Every row must include all HI feature columns plus sequence_index. "
            f"Missing from at least one row: {missing}",
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

    feature_cols = list(reference_model.features)
    non_finite = [
        c for c in [*feature_cols, "sequence_index"]
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

    return HiResponse(
        rows=[
            HiRow(sequence_index=int(seq), health_indicator=float(h), stage=str(s))
            for seq, h, s in zip(df["sequence_index"], hi, stage)
        ],
        hi_warn_threshold=float(thresholds.hi_warn),
        hi_critical_threshold=float(thresholds.hi_critical),
    )


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
        selected_path = artifacts.ensure_artifact("rul_selected_model.json")
        name = json.loads(selected_path.read_text())["selected"] if selected_path else None
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
    """Bounded prediction summaries, newest first, from the configured store
    (process-local unless RULGUARD_HISTORY_DB is set - see docs/prediction-history.md)."""
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


def _process_dataset_inspect_file(
    tmp_path: str,
    filename: str | None,
    declared_sampling_rate_hz: float | None,
    declared_units: str | None,
) -> DatasetProfileResponse:
    """Shared by the direct-multipart /dataset/inspect and the direct-to-
    storage /dataset/inspect/blob below - same reasoning as
    _process_femto_acquisition_file: one implementation, never two that
    could drift apart."""
    try:
        profile = profile_file(tmp_path)
        compatibility, reasons, required_action, sampling = _classify_for_model(
            profile,
            Path(tmp_path),
            declared_sampling_rate_hz=declared_sampling_rate_hz,
            declared_units=declared_units,
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
    profile["file"] = filename or profile["file"]  # real name, not the temp path
    _note(compatibility=compatibility)
    return DatasetProfileResponse(
        compatibility=compatibility, reasons=reasons, profile=profile,
        required_action=RequiredAction(**required_action), sampling=sampling,
    )


@app.post("/dataset/inspect", response_model=DatasetProfileResponse)
async def inspect_dataset(
    file: UploadFile,
    declared_sampling_rate_hz: float | None = Form(
        None, gt=0, le=MAX_SAMPLING_RATE_HZ, allow_inf_nan=False,
    ),
    declared_units: str | None = Form(None, max_length=40),
) -> DatasetProfileResponse:
    """Upload -> inspect -> classify (goals.md's dataset-detection step), before
    anything is validated/preprocessed/fed to a model - see
    docs/dataset-compatibility.md for what this does and does not check.

    declared_sampling_rate_hz/declared_units are the caller's own assertion,
    used only when the file carries no regular timestamps in seconds to derive
    a rate from - never a guess this endpoint makes itself (ml-data.md).

    For a file too large for a normal request body, see the direct-to-storage
    /dataset/inspect/blob variant below."""
    with _temporary_upload() as tmp:
        await _spool_upload(file, tmp)
        return _process_dataset_inspect_file(
            tmp.name, file.filename, declared_sampling_rate_hz, declared_units
        )


class BlobInspectRequest(BaseModel):
    blob_url: str = Field(..., description="A client-uploaded Vercel Blob object URL.")
    # Deliberately unconstrained here (unlike the equivalent Form()/Query() fields on the
    # direct-upload routes): a pydantic Field constraint violation is raised by FastAPI
    # during request validation, before this handler's body - and therefore before its
    # try/finally - ever runs, which would leave the already-uploaded blob undeleted.
    # Validated manually below, inside the try, so a bad value still cleans up the blob.
    declared_sampling_rate_hz: float | None = Field(default=None)
    declared_units: str | None = Field(default=None)


def _validate_declared_dataset_fields(
    declared_sampling_rate_hz: float | None, declared_units: str | None
) -> None:
    """Same bounds as the direct-upload routes' Form()/Query() constraints, raised as an
    ApiError instead so callers can validate inside a try/finally that must still run its
    cleanup (see BlobInspectRequest)."""
    if declared_sampling_rate_hz is not None and (
        not math.isfinite(declared_sampling_rate_hz)
        or not (0 < declared_sampling_rate_hz <= MAX_SAMPLING_RATE_HZ)
    ):
        raise ApiError(422, "VALIDATION_ERROR",
                       f"declared_sampling_rate_hz must be a finite number in (0, "
                       f"{MAX_SAMPLING_RATE_HZ}].")
    if declared_units is not None and len(declared_units) > 40:
        raise ApiError(422, "VALIDATION_ERROR", "declared_units must be at most 40 characters.")


@app.post("/dataset/inspect/blob", response_model=DatasetProfileResponse)
def inspect_dataset_blob(request: BlobInspectRequest) -> DatasetProfileResponse:
    """Direct-to-storage counterpart of /dataset/inspect - see
    predict_rul_from_femto_acquisition_blob's docstring for the shared
    rationale (bypasses the serverless request-body limit, bounded-memory
    chunked download, shared processing core, best-effort blob cleanup)."""
    _validate_blob_url(request.blob_url)
    with _temporary_upload() as tmp:
        try:
            _validate_declared_dataset_fields(
                request.declared_sampling_rate_hz, request.declared_units
            )
            _stream_blob_to_tempfile(request.blob_url, tmp, MAX_UPLOAD_BYTES)
            return _process_dataset_inspect_file(
                tmp.name,
                request.blob_url.rsplit("/", 1)[-1],
                request.declared_sampling_rate_hz,
                request.declared_units,
            )
        finally:
            _delete_blob(request.blob_url)


# Upload -> dataset detection -> validation -> preprocessing -> feature extraction
# (docs/feature-analysis.md). Deliberately stops before any health indicator or
# model: no cached artifact is loaded, so D11's FEMTO-only gate is never in play.
ANALYZE_STAGES = ("upload", "dataset_detection", "validation", "preprocessing",
                  "feature_extraction")
# The FEMTO acquisition length (0.1 s at 25.6 kHz, the project's fixed feature window).
# Only a default window length in samples; it makes no claim about any other machine.
DEFAULT_WINDOW_SAMPLES = FEMTO_ACQUISITION_SAMPLES
MAX_WINDOW_SAMPLES = 1_048_576
# Response size bound; windows past it are not computed (the total is still exact).
MAX_RETURNED_WINDOWS = 200
# Per-channel compute bound: featurised windows x window_samples. Heavily overlapping
# large windows would otherwise turn a tiny upload into unbounded synchronous work.
MAX_COMPUTED_SAMPLES = 16_777_216
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
    from bearing_pdm.chunked import WindowReport, iter_csv_window_features, scan_csv_column

    memory_detail = ("The file needs more memory than this service allows. Upload a smaller "
                     "file or a shorter recording.")

    # --- dataset detection: the same profile/structural classify /dataset/inspect uses.
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
    computed_samples = min(windows_total, MAX_RETURNED_WINDOWS) * window_samples
    if computed_samples > MAX_COMPUTED_SAMPLES:
        raise stages.fail("preprocessing", 422, "COMPUTE_LIMIT_EXCEEDED",
                          f"{min(windows_total, MAX_RETURNED_WINDOWS)} window(s) of "
                          f"{window_samples} samples would featurise {computed_samples} samples "
                          f"per channel; at most {MAX_COMPUTED_SAMPLES} are allowed. Use a "
                          "smaller window_samples or overlap_samples.",
                          compatibility=compatibility)
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
    except (ValueError, OverflowError, pd.errors.ParserError) as exc:
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
    timestamp_check = sampling["message"]
    if rate_source == "user":
        timestamp_check = (
            f"User-supplied sampling_rate_hz {rate:g} used; it agrees with the file's timestamps "
            "(1% tolerance)." if derived is not None else
            f"User-supplied sampling_rate_hz {rate:g} used; the file has no regular timestamp "
            "column in seconds, so the rate is not cross-checked against timing data.")
    stages.ok(stage, f"{len(windows)} of {windows_total} window(s) featurised"
                     + (f" (response capped at {MAX_RETURNED_WINDOWS})" if truncated else "")
                     + f"; {non_finite} non-finite feature value(s) returned as null.")
    return AnalyzeFeaturesResponse(
        stages=stages.as_list(), file=filename or "upload",
        channel={"column": name, "canonical": column["canonical"]},
        compatibility=compatibility, reasons=reasons,
        sampling={"rate_hz": rate, "source": rate_source,
                  "timestamp_check": timestamp_check, "timestamps_regular": sampling["regular"]},
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
    applicability_level: str | None = None
    applicability_shift_ratio: float | None = None
    applicability_reasons: list[str] = Field(default_factory=list)
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
        fingerprint = _file_fingerprint(tmp.name)
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

    supported = dataset_id.strip().lower() == TRAINED_DATASET_ID
    summary = {"dataset_id": "femto" if supported else "other", "recordings": len(rows)}
    with _history_entry("analyze_rul", "rul_extra_trees.joblib", summary, fingerprint,
                        supported=supported) as record:
        response = _analyze_rows(rows, axes, stages, dataset_id=dataset_id, units=units,
                                 preprocessing_version=preprocessing_version,
                                 window_samples=window_samples, overlap_samples=overlap_samples)
        record["compatibility_state"] = response.compatibility
        record["result"] = {
            "rul_hours": response.rul_hours,
            "applicability_level": response.applicability_level,
            "latest_stage": response.health.rows[-1].stage if response.health else None,
        }
        if response.health is None:
            record["warnings"].append("HEALTH_INDICATOR_UNAVAILABLE")
        return response


def _analyze_rows(rows, axes, stages, *, dataset_id, units, preprocessing_version,
                  window_samples, overlap_samples) -> AnalyzeRulResponse:
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
    if (preprocessing_version != FEMTO_PREPROCESSING_VERSION
            or window_samples != FEMTO_ACQUISITION_SAMPLES or overlap_samples != 0):
        raise stages.fail(stage, 422, "PREPROCESSING_MISMATCH",
                          "The cached FEMTO pipeline requires femto-acquisition-v1: complete "
                          "2560-sample acquisitions, no overlap or prior signal transforms.",
                          compatibility=ADAPTER_REQUIRED)
    incomplete = {a.channel["column"]: a.signal["missing"] for a in axes if a.signal["missing"]}
    if incomplete:
        raise stages.fail(stage, 422, "INCOMPLETE_ACQUISITION",
                          "femto-acquisition-v1 requires every vibration sample to be present; "
                          f"missing samples per axis: {incomplete}. Samples are never dropped "
                          "or filled before prediction.", compatibility=INVALID_INPUT)
    if any(a.truncated or a.signal["rows"] % FEMTO_ACQUISITION_SAMPLES for a in axes):
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
    # The /predict/* route functions are reused as-is; their own history
    # records are suppressed so this request is recorded once, as analyze_rul.
    token = _HISTORY_SUPPRESSED.set(True)
    try:
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
                              exc.retryable, **(exc.extra or {})) from None
    finally:
        _HISTORY_SUPPRESSED.reset(token)
    if not math.isfinite(prediction.rul_seconds) or prediction.rul_seconds < 0:
        raise stages.fail("prediction", 503, "INVALID_MODEL_OUTPUT",
                          "The cached model did not produce a finite non-negative RUL.")
    stages.ok("prediction", "RUL for the last complete acquisition computed by /predict/rul "
                            f"(model applicability: {prediction.applicability_level or 'not assessed'}).")
    # The metadata gate above cannot see the feature VALUES; /predict/rul's
    # applicability check on the latest acquisition can, and a MEDIUM result
    # downgrades the outcome exactly as it does on /predict/rul itself.
    compatibility = prediction.compatibility
    if compatibility != FULLY_SUPPORTED:
        warnings.extend(prediction.applicability_reasons)
    warnings.append("Dataset identity, units and acquisition order are caller declarations; "
                    "schema matching does not establish machine provenance or held-out accuracy.")
    return AnalyzeRulResponse(
        stages=stages.as_list(), compatibility=compatibility, model=gate.model,
        preprocessing_version=FEMTO_PREPROCESSING_VERSION,
        rul_seconds=prediction.rul_seconds, rul_hours=prediction.rul_hours,
        health_indicator_produced=health is not None, health=health, warnings=warnings,
        applicability_level=prediction.applicability_level,
        applicability_shift_ratio=prediction.applicability_shift_ratio,
        applicability_reasons=prediction.applicability_reasons,
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
