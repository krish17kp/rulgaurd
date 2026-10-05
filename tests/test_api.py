"""Tests for the read-only prediction API (src/bearing_pdm/api.py).

Uses the real cached artifacts under artifacts/models/ when present (they are
gitignored, same as dashboard.py's artifacts - not committed). Tests that need
the model skip cleanly on a checkout without them; health/gating tests do not
depend on the artifact's presence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bearing_pdm import api, artifacts

MODEL_PRESENT = (api.MODELS_DIR / "rul_extra_trees.joblib").exists()
BUNDLE_PRESENT = (api.MODELS_DIR / api.CROSS_DOMAIN_BUNDLE_NAME).exists()

client = TestClient(api.app)


def test_requests_get_a_request_id_header_and_are_logged(caplog):
    with caplog.at_level("INFO", logger="bearing_pdm.api"):
        response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    assert any("path=/health" in r.message and "status=200" in r.message for r in caplog.records)


def test_health_reports_model_status():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["models_loaded"]["rul_extra_trees"] == MODEL_PRESENT


def test_metrics_dir_prefers_a_vendored_copy_next_to_the_api_module(tmp_path, monkeypatch):
    """Packaging regression test: a real Vercel deployment only bundles files
    physically inside its rootDirectory-scoped tree (frontend/api/**), not a
    sibling frontend/reports/ copy, even though both resolve fine locally.
    frontend/package.json's "prebuild" vendors reports/metrics/ to
    api/reports/metrics/ for exactly this reason - this test locks in that
    the module picks the vendored-copy candidate first, so the fix cannot
    silently regress back to depending on RUL_EVALUATION_JSON alone."""
    vendored = tmp_path / "vendored" / "reports" / "metrics"
    vendored.mkdir(parents=True)
    (vendored / "rul_evaluation.json").write_text("{}")
    fallback = tmp_path / "fallback" / "reports" / "metrics"
    monkeypatch.setattr(api, "_METRICS_DIR_CANDIDATES", (vendored, fallback))
    assert api._resolve_metrics_dir() == vendored


def test_metrics_dir_falls_back_when_no_candidate_is_vendored(tmp_path, monkeypatch):
    missing_vendored = tmp_path / "vendored" / "reports" / "metrics"
    fallback = tmp_path / "fallback" / "reports" / "metrics"
    monkeypatch.setattr(api, "_METRICS_DIR_CANDIDATES", (missing_vendored, fallback))
    assert api._resolve_metrics_dir() == fallback


EVALUATION_PRESENT = (api.METRICS_DIR / "rul_evaluation.json").exists()


@pytest.mark.skipif(not EVALUATION_PRESENT, reason="reports/metrics/rul_evaluation.json not present")
def test_models_evaluation_returns_real_metrics_with_college_caveat():
    response = client.get("/models/evaluation")
    assert response.status_code == 200
    body = response.json()
    assert "femto_lobo_mean_mae_by_model" in body
    assert "extra_trees" in body["femto_lobo_mean_mae_by_model"]
    # D10: college naive's MAE=0.0 must never travel without its caveat.
    assert "college_naive_caveat" in body
    assert "oracle" in body["college_naive_caveat"].lower()


def test_models_info_lists_femto_only():
    response = client.get("/models/info")
    assert response.status_code == 200
    assert response.json()["supported_datasets"] == ["femto"]


def test_models_evaluation_prefers_the_inline_env_var_over_the_file(monkeypatch, tmp_path):
    """RUL_EVALUATION_JSON (deployment escape hatch for when the file isn't
    bundled - see models_evaluation's docstring) must win over a stale or
    absent file, the same precedence as ARTIFACT_MANIFEST_JSON."""
    monkeypatch.setattr(api, "METRICS_DIR", tmp_path / "does-not-exist")
    monkeypatch.setenv(
        "RUL_EVALUATION_JSON",
        json.dumps({"femto_lobo_mean_mae_by_model": {"extra_trees": 1.0},
                   "college_naive_caveat": "oracle, not a fair comparison"}),
    )
    response = client.get("/models/evaluation")
    assert response.status_code == 200
    assert response.json()["femto_lobo_mean_mae_by_model"]["extra_trees"] == 1.0


def test_models_evaluation_falls_back_to_the_file_on_malformed_env_var(monkeypatch):
    monkeypatch.setenv("RUL_EVALUATION_JSON", "{not valid json")
    response = client.get("/models/evaluation")
    # Whatever the file-based path would have returned (200 if present locally,
    # 503 METRICS_UNAVAILABLE otherwise) - never a 500 from the bad env var.
    assert response.status_code in (200, 503)


def test_predict_rul_rejects_non_femto_dataset():
    response = client.post(
        "/predict/rul", json={"dataset_id": "college", "features": {}}
    )
    assert response.status_code == 422
    assert "femto" in response.json()["detail"].lower()


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_predict_rul_downgrades_compatibility_when_applicability_cannot_be_assessed(
    monkeypatch,
):
    """Production-policy regression (M2 from the independent release review):
    if cross_domain_bundle.joblib is missing/unreadable, domain-fit was never
    checked, so the response must not claim FULLY_SUPPORTED - that would be
    indistinguishable from a real HIGH-applicability result. It must downgrade
    to the same RETRAIN_REQUIRED/"experimental" contract MEDIUM applicability
    already uses, not invent a new state and not silently assume in-domain."""
    monkeypatch.setattr(api, "_assess_applicability", lambda *a, **k: None)
    model = api._load_joblib("rul_extra_trees.joblib")
    features = dict(model.median_fill)
    response = client.post(
        "/predict/rul", json={"dataset_id": "femto", "features": features}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["compatibility"] == "RETRAIN_REQUIRED"
    assert body["applicability_level"] is None
    assert "could not be assessed" in " ".join(body["applicability_reasons"]).lower()
    assert "experimental" in " ".join(body["applicability_reasons"]).lower()


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_predict_rul_accepts_full_feature_row():
    model = api._load_joblib("rul_extra_trees.joblib")
    features = dict(model.median_fill)
    response = client.post(
        "/predict/rul", json={"dataset_id": "femto", "features": features}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model_name"] == "extra_trees"
    assert body["rul_hours"] == pytest.approx(body["rul_seconds"] / 3600.0)
    assert body["features_missing"] == []


FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"


def _real_femto_vibration_csv(
    with_timestamp: bool = False, blank_x: bool = False, acquisitions: tuple[str, ...] = ("acc_00001",),
    max_rows: int | None = None,
) -> bytes:
    """A header-based CSV built from the real FEMTO fixture's own
    accel_horizontal/accel_vertical values - realistic signal statistics, not
    a flat synthetic placeholder, so applicability.assess() scores it the way
    it would score genuine in-domain data (HIGH), not an artifact of using
    toy numbers nothing like a real bearing signal.

    `acquisitions`: one or more real acc_*.csv files concatenated, to test
    that a longer upload is windowed back to the training acquisition size
    (api.FEMTO_ACQUISITION_SAMPLES) rather than scored as one long window."""
    import pandas as pd

    frames = [
        pd.read_csv(
            FIXTURES / "femto" / "Bearing1_1" / f"{name}.csv",
            header=None,
            names=["hour", "minute", "second", "microsecond", "x", "y"],
            dtype="float64",
        )
        for name in acquisitions
    ]
    df = pd.concat(frames, ignore_index=True)
    if max_rows is not None:
        df = df.iloc[:max_rows]
    lines = []
    header = (["time_s"] if with_timestamp else []) + ["vibration_x", "vibration_y"]
    lines.append(",".join(header))
    rate = api.FEMTO_SAMPLE_RATE_HZ
    for i, (x, y) in enumerate(zip(df["x"], df["y"])):
        x_field = "" if blank_x else str(x)
        row = ([f"{i / rate}"] if with_timestamp else []) + [x_field, str(y)]
        lines.append(",".join(row))
    return ("\n".join(lines) + "\n").encode()


def test_dataset_inspect_rejects_empty_file():
    response = client.post(
        "/dataset/inspect", files={"file": ("empty.csv", b"", "text/csv")}
    )
    assert response.status_code == 422


def test_dataset_inspect_requires_adapter_for_headerless_femto_fixture():
    path = FIXTURES / "femto" / "Bearing1_1" / "acc_00001.csv"
    with open(path, "rb") as f:
        response = client.post("/dataset/inspect", files={"file": (path.name, f, "text/csv")})
    assert response.status_code == 200
    body = response.json()
    assert body["compatibility"] == "ADAPTER_REQUIRED"
    assert body["profile"]["has_header"] is False


@pytest.mark.skipif(not BUNDLE_PRESENT, reason="artifacts/models/cross_domain_bundle.joblib not present")
def test_dataset_inspect_fully_supported_for_a_real_in_domain_signal():
    """A matching declared rate alone is not enough - this also needs real,
    in-domain-looking vibration values (applicability HIGH), not just any
    numbers at the right rate. Uses the real FEMTO fixture's own signal."""
    response = client.post(
        "/dataset/inspect",
        files={"file": ("clean.csv", _real_femto_vibration_csv(), "text/csv")},
        data={"declared_sampling_rate_hz": "25600", "declared_units": "g"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["compatibility"] == "FULLY_SUPPORTED"


@pytest.mark.skipif(not BUNDLE_PRESENT, reason="artifacts/models/cross_domain_bundle.joblib not present")
def test_dataset_inspect_fully_supported_for_a_longer_real_signal_spanning_two_acquisitions():
    """Regression: a longer upload (here, two real in-domain acquisitions
    concatenated) must be windowed back to the training acquisition size
    before scoring, not treated as one long window - several features
    (total energy, peak-to-peak, spectral resolution) scale with window
    length, so scoring an arbitrarily long window against a reference fitted
    on 2560-sample acquisitions previously pushed even genuinely in-domain
    data toward RETRAIN_REQUIRED purely from length."""
    csv_bytes = _real_femto_vibration_csv(acquisitions=("acc_00001", "acc_00002"))
    response = client.post(
        "/dataset/inspect",
        files={"file": ("clean.csv", csv_bytes, "text/csv")},
        data={"declared_sampling_rate_hz": "25600", "declared_units": "g"},
    )
    assert response.status_code == 200
    assert response.json()["compatibility"] == "FULLY_SUPPORTED"


@pytest.mark.skipif(not BUNDLE_PRESENT, reason="artifacts/models/cross_domain_bundle.joblib not present")
def test_dataset_inspect_degrades_honestly_for_a_file_shorter_than_one_window():
    """Regression: a file shorter than FEMTO_ACQUISITION_SAMPLES was scored
    as one short window against a reference fitted on full-length windows -
    several length-dependent features made real, in-domain data look
    out-of-domain purely from being short. Must degrade honestly (like the
    bundle-unavailable case) instead of reporting a fabricated domain shift."""
    csv_bytes = _real_femto_vibration_csv(max_rows=api.FEMTO_ACQUISITION_SAMPLES - 1)
    response = client.post(
        "/dataset/inspect",
        files={"file": ("short.csv", csv_bytes, "text/csv")},
        data={"declared_sampling_rate_hz": "25600", "declared_units": "g"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["compatibility"] == "FULLY_SUPPORTED"
    assert "could not be assessed" in " ".join(body["reasons"]).lower()


@pytest.mark.skipif(not BUNDLE_PRESENT, reason="artifacts/models/cross_domain_bundle.joblib not present")
def test_dataset_inspect_reports_dropped_trailing_rows():
    """A file that isn't an exact multiple of the window size must say so,
    not silently drop the unscored remainder."""
    csv_bytes = _real_femto_vibration_csv(
        acquisitions=("acc_00001", "acc_00002"), max_rows=api.FEMTO_ACQUISITION_SAMPLES + 100
    )
    response = client.post(
        "/dataset/inspect",
        files={"file": ("partial.csv", csv_bytes, "text/csv")},
        data={"declared_sampling_rate_hz": "25600", "declared_units": "g"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "100 trailing row" in " ".join(body["reasons"])


def test_dataset_inspect_adapter_required_without_sampling_rate_or_units_toy_data():
    """A toy, flat-ish signal with a matching declared rate is downgraded by
    applicability (not HIGH) rather than silently accepted as fully
    supported just because the rate matches - see the real-signal test
    above for what genuinely in-domain data looks like."""
    csv_bytes = b"vibration_x,vibration_y\n0.1,0.2\n0.3,0.4\n0.2,0.1\n"
    response = client.post(
        "/dataset/inspect",
        files={"file": ("clean.csv", csv_bytes, "text/csv")},
        data={"declared_sampling_rate_hz": "25600", "declared_units": "g"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["compatibility"] in ("FULLY_SUPPORTED", "RETRAIN_REQUIRED")
    if not BUNDLE_PRESENT:
        assert body["compatibility"] == "FULLY_SUPPORTED"  # degraded: rate-match only, stated in reasons


def test_dataset_inspect_adapter_required_without_sampling_rate_or_units():
    """Structurally clean, high-confidence vibration columns - but no
    timestamp column and no declaration means frequency features can't be
    computed and units aren't known, so this can't be called FULLY_SUPPORTED
    without guessing (ml-data.md)."""
    csv_bytes = b"vibration_x,vibration_y\n0.1,0.2\n0.3,0.4\n0.2,0.1\n"
    response = client.post(
        "/dataset/inspect", files={"file": ("clean.csv", csv_bytes, "text/csv")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["compatibility"] == "ADAPTER_REQUIRED"
    reasons = " ".join(body["reasons"]).lower()
    assert "sampling rate unknown" in reasons
    assert "units not declared" in reasons


def test_dataset_inspect_retrain_required_for_structurally_usable_but_unmatched_rate():
    """Metadata is fully known (declared), the file is structurally clean -
    but no trained model was fit at this sampling rate. That's a scientific
    gap (retraining), not a parsing gap (ADAPTER_REQUIRED)."""
    csv_bytes = b"vibration_x,vibration_y\n0.1,0.2\n0.3,0.4\n0.2,0.1\n"
    response = client.post(
        "/dataset/inspect",
        files={"file": ("clean.csv", csv_bytes, "text/csv")},
        data={"declared_sampling_rate_hz": "1000", "declared_units": "m/s^2"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["compatibility"] == "RETRAIN_REQUIRED"
    assert "1000" in " ".join(body["reasons"])


@pytest.mark.skipif(not BUNDLE_PRESENT, reason="artifacts/models/cross_domain_bundle.joblib not present")
def test_dataset_inspect_derives_sampling_rate_from_a_timestamp_column():
    """No declaration needed when the file itself carries a timestamp
    column - the rate is derived from real evidence (median step), not
    guessed, and happens to match FEMTO's rate here. Real signal values
    (not toy numbers) so it also clears the applicability check."""
    csv_bytes = _real_femto_vibration_csv(with_timestamp=True)
    response = client.post(
        "/dataset/inspect",
        files={"file": ("timed.csv", csv_bytes, "text/csv")},
        data={"declared_units": "g"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["compatibility"] == "FULLY_SUPPORTED"
    assert "timestamp column" in " ".join(body["reasons"])


def test_dataset_inspect_timestamp_evidence_overrides_a_contradicting_declared_rate():
    """Regression for a review defect: a declared_sampling_rate_hz used to
    win even when a real timestamp column in the file said otherwise,
    letting the caller declare their way to FULLY_SUPPORTED - exactly the
    guess ml-data.md forbids. The file's own evidence must win, and a
    contradicting declaration must be flagged, not silently overridden."""
    step = 1.0 / 1000.0  # 1kHz by the file's own timestamps
    rows = "\n".join(f"{i * step},{0.1 + 0.001 * (i % 7)},{0.2 + 0.001 * (i % 5)}" for i in range(300))
    csv_bytes = f"time_s,vibration_x,vibration_y\n{rows}\n".encode()

    response = client.post(
        "/dataset/inspect",
        files={"file": ("timed.csv", csv_bytes, "text/csv")},
        data={"declared_sampling_rate_hz": "25600", "declared_units": "g"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["compatibility"] == "ADAPTER_REQUIRED"
    assert "conflicts" in " ".join(body["reasons"]).lower()

    # No conflicting declaration at all: the file's own 1kHz evidence is used
    # directly, correctly landing on RETRAIN_REQUIRED (not FEMTO's rate).
    response = client.post(
        "/dataset/inspect",
        files={"file": ("timed.csv", csv_bytes, "text/csv")},
        data={"declared_units": "g"},
    )
    assert response.json()["compatibility"] == "RETRAIN_REQUIRED"

    # A declaration that *agrees* with the file's own timestamps (within
    # tolerance) must not be flagged as a conflict - only disagreement is.
    response = client.post(
        "/dataset/inspect",
        files={"file": ("timed.csv", csv_bytes, "text/csv")},
        data={"declared_sampling_rate_hz": "1005", "declared_units": "g"},
    )
    body = response.json()
    assert body["compatibility"] == "RETRAIN_REQUIRED"
    assert "conflicts" not in " ".join(body["reasons"]).lower()


def test_dataset_inspect_never_assumes_a_generic_time_column_is_in_seconds():
    """Regression: any timestamp-mapped column's median step used to be read
    as seconds, so a millisecond `time` column at 25.6 kHz (step 0.0390625)
    'derived' 25.6 Hz - or a ms column whose numbers happened to look like
    seconds derived a fabricated rate. Only time_s/seconds (or ISO datetimes)
    are read as seconds; anything else needs a declaration and says so."""
    step_ms = 1000.0 / api.FEMTO_SAMPLE_RATE_HZ
    rows = "\n".join(f"{i * step_ms},{0.1 + 0.001 * (i % 7)},{0.2 + 0.001 * (i % 5)}"
                     for i in range(300))
    csv_bytes = f"time,vibration_x,vibration_y\n{rows}\n".encode()

    response = client.post(
        "/dataset/inspect",
        files={"file": ("timed.csv", csv_bytes, "text/csv")},
        data={"declared_units": "g"},
    )
    body = response.json()
    assert body["compatibility"] == "ADAPTER_REQUIRED"
    assert body["required_action"]["kind"] == "METADATA_REQUIRED"
    assert body["sampling"]["rate_hz"] is None
    assert "not used to derive or cross-check" in " ".join(body["reasons"])

    response = client.post(
        "/dataset/inspect",
        files={"file": ("timed.csv", csv_bytes, "text/csv")},
        data={"declared_sampling_rate_hz": "25600", "declared_units": "g"},
    )
    body = response.json()
    assert body["sampling"] | {"message": None} == {
        "rate_hz": 25600.0, "source": "user", "regular": None, "required": False, "message": None}
    assert "not used to derive or cross-check" in " ".join(body["reasons"])


def test_dataset_inspect_irregular_timestamps_fail_closed_even_with_a_declaration():
    rows = "\n".join(f"{t},{0.1 + 0.001 * (i % 7)}" for i, t in enumerate([0, 0.01, 0.03, 0.04]))
    response = client.post(
        "/dataset/inspect",
        files={"file": ("timed.csv", f"time_s,vibration_x\n{rows}\n".encode(), "text/csv")},
        data={"declared_sampling_rate_hz": "25600", "declared_units": "g"},
    )
    body = response.json()
    assert body["compatibility"] == "ADAPTER_REQUIRED"
    assert body["required_action"]["kind"] == "TIMESTAMPS_IRREGULAR"
    assert body["sampling"]["regular"] is False


@pytest.mark.parametrize("data, state, kind", [
    ({}, "ADAPTER_REQUIRED", "METADATA_REQUIRED"),
    ({"declared_sampling_rate_hz": "1000", "declared_units": "g"}, "RETRAIN_REQUIRED",
     "RETRAIN_REQUIRED"),
])
def test_dataset_inspect_states_carry_a_required_action(data, state, kind):
    csv_bytes = b"vibration_x,vibration_y\n0.1,0.2\n0.3,0.4\n0.2,0.1\n"
    response = client.post(
        "/dataset/inspect", files={"file": ("clean.csv", csv_bytes, "text/csv")}, data=data)
    body = response.json()
    assert (body["compatibility"], body["required_action"]["kind"]) == (state, kind)
    assert body["required_action"]["missing"]


@pytest.mark.parametrize("body", [
    b'{"dataset_id": NaN, "features": {}}',
    b'{"dataset_id": "femto", "features": Infinity}',
])
@pytest.mark.parametrize("path", ["/predict/rul", "/predict/hi"])
def test_non_finite_literal_in_an_invalid_body_is_422_not_500(path, body):
    """Regression: FastAPI's default handler echoed the NaN/Infinity `input`
    back into a JSON response it then could not serialise - a 500."""
    response = TestClient(api.app, raise_server_exceptions=False).post(
        path, content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_dataset_inspect_rejects_whitespace_only_declared_units():
    csv_bytes = b"vibration_x,vibration_y\n0.1,0.2\n0.3,0.4\n0.2,0.1\n"
    response = client.post(
        "/dataset/inspect",
        files={"file": ("clean.csv", csv_bytes, "text/csv")},
        data={"declared_sampling_rate_hz": "25600", "declared_units": "   "},
    )
    assert response.status_code == 200
    assert response.json()["compatibility"] == "ADAPTER_REQUIRED"


def test_dataset_inspect_rejects_non_positive_declared_sampling_rate():
    csv_bytes = b"vibration_x\n0.1\n0.2\n0.3\n"
    response = client.post(
        "/dataset/inspect",
        files={"file": ("clean.csv", csv_bytes, "text/csv")},
        data={"declared_sampling_rate_hz": "0", "declared_units": "g"},
    )
    assert response.status_code == 422


def test_dataset_inspect_invalid_for_non_numeric_vibration_column():
    csv_bytes = b"vibration_x\nabc\ndef\n"
    response = client.post("/dataset/inspect", files={"file": ("bad.csv", csv_bytes, "text/csv")})
    assert response.status_code == 200
    assert response.json()["compatibility"] == "INVALID_INPUT"


@pytest.mark.skipif(not BUNDLE_PRESENT, reason="artifacts/models/cross_domain_bundle.joblib not present")
def test_dataset_inspect_retrain_required_when_half_the_model_features_are_unavailable():
    """vibration_x is 100% missing but vibration_y is fully usable and
    structurally this is fine - but half the trained model's features
    (every vibration_x_* one) are then unavailable, which applicability.py's
    own missing-feature cap correctly treats as a real degradation, not
    something to silently call fully supported.

    Also pins the single-window scoring-consistency fix: this file is
    exactly one FEMTO_ACQUISITION_SAMPLES window, which must be scored the
    same way (single_recording=True) whether it arrives as a one-element
    list (this generic path) or a dict (the raw FEMTO upload endpoint) -
    routing by list-length rather than by isinstance(..., dict) alone."""
    csv_bytes = _real_femto_vibration_csv(blank_x=True)
    response = client.post(
        "/dataset/inspect",
        files={"file": ("bad.csv", csv_bytes, "text/csv")},
        data={"declared_sampling_rate_hz": "25600", "declared_units": "g"},
    )
    assert response.status_code == 200
    body = response.json()
    # Half the model's features missing caps at MEDIUM
    # (applicability.py's PARTIAL_MISSING_FRACTION/MISSING_FEATURE_FRACTION
    # thresholds applied to the *fraction present*), not LOW - LOW is what
    # the pre-fix max()-based aggregation produced for this exact input.
    assert body["compatibility"] == "RETRAIN_REQUIRED"
    # The downgrade message must attribute the real cause (missing features),
    # not blame "the signal itself" when the shift ratio is actually fine.
    assert "missing model feature" in " ".join(body["reasons"])


def test_dataset_inspect_invalid_when_every_vibration_column_is_missing():
    csv_bytes = b"vibration_x\n\n\n\n"
    response = client.post("/dataset/inspect", files={"file": ("bad.csv", csv_bytes, "text/csv")})
    assert response.status_code == 200
    assert response.json()["compatibility"] == "INVALID_INPUT"


def test_dataset_inspect_invalid_for_constant_vibration_column():
    csv_bytes = b"vibration_x\n1.0\n1.0\n1.0\n"
    response = client.post("/dataset/inspect", files={"file": ("bad.csv", csv_bytes, "text/csv")})
    assert response.status_code == 200
    assert response.json()["compatibility"] == "INVALID_INPUT"


def test_dataset_inspect_invalid_for_all_infinite_vibration_column():
    csv_bytes = b"vibration_x\ninf\ninf\n-inf\ninf\n"
    response = client.post("/dataset/inspect", files={"file": ("bad.csv", csv_bytes, "text/csv")})
    assert response.status_code == 200
    body = response.json()
    assert body["compatibility"] == "INVALID_INPUT"
    assert "infinite" in " ".join(body["reasons"]).lower()


def test_dataset_inspect_invalid_for_header_only_file():
    csv_bytes = b"vibration_x,vibration_y\n"
    response = client.post("/dataset/inspect", files={"file": ("empty_rows.csv", csv_bytes, "text/csv")})
    assert response.status_code == 200
    assert response.json()["compatibility"] == "INVALID_INPUT"


def test_dataset_inspect_unsupported_for_no_recognisable_sensor_columns():
    csv_bytes = b"foo,bar\n1,2\n3,4\n"
    response = client.post(
        "/dataset/inspect", files={"file": ("unrelated.csv", csv_bytes, "text/csv")}
    )
    assert response.status_code == 200
    assert response.json()["compatibility"] == "UNSUPPORTED"


def test_dataset_inspect_rejects_oversized_upload(monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 10)
    response = client.post(
        "/dataset/inspect",
        files={"file": ("big.csv", b"vibration_x\n" + b"1.0\n" * 100, "text/csv")},
    )
    assert response.status_code == 413


def test_oversized_content_length_is_rejected_before_body_is_read():
    huge = api._MAX_REQUEST_BYTES + 1
    response = client.post(
        "/predict/hi",
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": str(huge)},
    )
    assert response.status_code == 413


def test_vercel_app_mounts_routes_under_api_prefix():
    vercel_client = TestClient(api.vercel_app)
    response = vercel_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


HI_MODEL_PRESENT = (api.MODELS_DIR / "reference_hi_model.joblib").exists()


def test_predict_hi_rejects_non_femto_dataset():
    response = client.post("/predict/hi", json={"dataset_id": "college", "rows": [{"sequence_index": 0}]})
    assert response.status_code == 422


@pytest.mark.skipif(not HI_MODEL_PRESENT, reason="artifacts/models/reference_hi_model.joblib not present")
def test_predict_hi_rejects_rows_missing_feature_columns():
    response = client.post(
        "/predict/hi", json={"dataset_id": "femto", "rows": [{"sequence_index": 0}]}
    )
    assert response.status_code == 422


@pytest.mark.skipif(not HI_MODEL_PRESENT, reason="artifacts/models/reference_hi_model.joblib not present")
def test_predict_hi_rejects_a_run_shorter_than_the_reference_window():
    hi_model = api._load_joblib("reference_hi_model.joblib")
    min_rows = hi_model.reference_skip + hi_model.reference_n
    too_few = min_rows - 1
    rows = [
        {"sequence_index": i, **{f: 1000.0 for f in hi_model.features}}
        for i in range(too_few)
    ]
    response = client.post("/predict/hi", json={"dataset_id": "femto", "rows": rows})
    assert response.status_code == 422
    assert "reference window" in response.json()["detail"].lower()


@pytest.mark.skipif(not HI_MODEL_PRESENT, reason="artifacts/models/reference_hi_model.joblib not present")
def test_predict_hi_rejects_constant_reference_window_even_when_long_enough():
    """The exact case review found fail-open: enough rows to pass the
    min-length gate, but every row identical, so the model can't tell
    'healthy' from 'stuck sensor' - was silently scored 100% HEALTHY."""
    hi_model = api._load_joblib("reference_hi_model.joblib")
    min_rows = hi_model.reference_skip + hi_model.reference_n
    rows = [
        {"sequence_index": i, **{f: 1000.0 for f in hi_model.features}}
        for i in range(min_rows)
    ]
    response = client.post("/predict/hi", json={"dataset_id": "femto", "rows": rows})
    assert response.status_code == 422
    assert "variation" in response.json()["detail"].lower()


@pytest.mark.skipif(not HI_MODEL_PRESENT, reason="artifacts/models/reference_hi_model.joblib not present")
def test_predict_hi_rejects_reference_window_with_only_float_jitter():
    """Regression for the exact gap review found in the previous fix: exact
    nunique()<=1 was defeated by a ~1e-7 perturbation, which is far below
    the model's fitted per-feature scale and should still count as
    'no real variation.'"""
    hi_model = api._load_joblib("reference_hi_model.joblib")
    min_rows = hi_model.reference_skip + hi_model.reference_n
    rows = [
        {"sequence_index": i, **{f: 1000.0 + (i % 2) * 1e-7 for f in hi_model.features}}
        for i in range(min_rows)
    ]
    response = client.post("/predict/hi", json={"dataset_id": "femto", "rows": rows})
    assert response.status_code == 422
    assert "variation" in response.json()["detail"].lower()


@pytest.mark.skipif(not HI_MODEL_PRESENT, reason="artifacts/models/reference_hi_model.joblib not present")
def test_predict_hi_rejects_reference_window_with_only_one_varying_feature():
    hi_model = api._load_joblib("reference_hi_model.joblib")
    min_rows = hi_model.reference_skip + hi_model.reference_n
    rows = []
    for i in range(min_rows):
        row = {"sequence_index": i}
        for j, f in enumerate(hi_model.features):
            row[f] = 1000.0 + (i * 10.0 if j == 0 else 0.0)  # only the first feature moves
        rows.append(row)
    response = client.post("/predict/hi", json={"dataset_id": "femto", "rows": rows})
    assert response.status_code == 422


@pytest.mark.skipif(not HI_MODEL_PRESENT, reason="artifacts/models/reference_hi_model.joblib not present")
def test_predict_hi_rejects_non_finite_feature_values():
    hi_model = api._load_joblib("reference_hi_model.joblib")
    min_rows = hi_model.reference_skip + hi_model.reference_n
    rows = [
        {"sequence_index": i, **{f: 1.0 + i * 0.01 for f in hi_model.features}}
        for i in range(min_rows)
    ]
    rows[-1][hi_model.features[0]] = float("inf")
    # Python's json.dumps allows Infinity by default (non-standard but valid
    # for this test's purpose: exercising what api.py does once a value is a
    # float('inf')) - build the body manually since httpx's own client-side
    # encoder is stricter than that.
    import json as json_module

    body = json_module.dumps({"dataset_id": "femto", "rows": rows})
    response = client.post(
        "/predict/hi", content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert "non-finite" in response.json()["detail"].lower()


def test_predict_hi_rejects_a_row_missing_sequence_index():
    """Regression for a review finding: the missing-columns check only covered the HI
    feature columns, so a row missing sequence_index reached df.sort_values("sequence_index")
    and raised a KeyError that surfaced as an unhelpful 500 instead of a 422."""
    hi_model = api._load_joblib("reference_hi_model.joblib")
    min_rows = hi_model.reference_skip + hi_model.reference_n
    rows = [{"sequence_index": i, **{f: 1.0 for f in hi_model.features}} for i in range(min_rows)]
    del rows[-1]["sequence_index"]
    response = client.post("/predict/hi", json={"dataset_id": "femto", "rows": rows})
    assert response.status_code == 422
    assert "sequence_index" in response.json()["detail"]


def test_predict_hi_rejects_non_finite_sequence_index():
    """A sequence_index present but NaN would otherwise reach int(seq) deep in the response
    assembly and raise ValueError instead of failing the request cleanly."""
    hi_model = api._load_joblib("reference_hi_model.joblib")
    min_rows = hi_model.reference_skip + hi_model.reference_n
    rows = [{"sequence_index": i, **{f: 1.0 for f in hi_model.features}} for i in range(min_rows)]
    rows[-1]["sequence_index"] = float("nan")
    import json as json_module

    body = json_module.dumps({"dataset_id": "femto", "rows": rows})
    response = client.post(
        "/predict/hi", content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert "non-finite" in response.json()["detail"].lower()


@pytest.mark.skipif(not HI_MODEL_PRESENT, reason="artifacts/models/reference_hi_model.joblib not present")
def test_predict_hi_returns_declining_health_indicator():
    hi_model = api._load_joblib("reference_hi_model.joblib")
    n = 60
    rows = []
    for i in range(n):
        row = {"sequence_index": i}
        for feature in hi_model.features:
            # reference_skip=10, reference_n=50 -> reference window is rows
            # [10, 60). Rows 50-59 fall inside that window AND get the jump,
            # so the window itself has real variation (passes the
            # degenerate-window check) while still producing a clear
            # late-run degradation signature, not noise.
            row[feature] = 1.0 if i < 50 else 5.0
        rows.append(row)
    response = client.post("/predict/hi", json={"dataset_id": "femto", "rows": rows})
    assert response.status_code == 200
    body = response.json()
    assert len(body["rows"]) == n
    assert all(0.0 < r["health_indicator"] < 1.0 for r in body["rows"])
    # Later (degraded) rows must score lower than the healthy reference rows.
    early_hi = body["rows"][10]["health_indicator"]
    late_hi = body["rows"][-1]["health_indicator"]
    assert late_hi < early_hi
    assert {r["stage"] for r in body["rows"]} <= {"HEALTHY", "DEGRADING", "CRITICAL"}


def test_predict_rul_returns_503_when_model_artifact_missing(monkeypatch):
    # _load_joblib resolves artifacts via artifacts.ensure_artifact, which
    # reads artifacts.MODELS_DIR (and api.MODELS_DIR itself is otherwise
    # unused by the loading path now) - see src/bearing_pdm/artifacts.py.
    monkeypatch.setattr(artifacts, "MODELS_DIR", api.MODELS_DIR.parent / "does-not-exist")
    monkeypatch.setattr(artifacts, "MANIFEST_PATH", api.MODELS_DIR.parent / "does-not-exist" / "manifest.json")  # no real source_url to fall back to - genuinely unavailable, not just locally missing
    api._MODEL_CACHE.clear()
    response = client.post("/predict/rul", json={"dataset_id": "femto", "features": {}})
    assert response.status_code == 503
    api._MODEL_CACHE.clear()


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_predict_rul_rejects_mostly_missing_features():
    response = client.post("/predict/rul", json={"dataset_id": "femto", "features": {}})
    assert response.status_code == 422
    assert "missing" in response.json()["detail"].lower()


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_predict_rul_falls_back_to_median_for_missing_features():
    model = api._load_joblib("rul_extra_trees.joblib")
    n_provided = len(model.feature_columns) - 2  # under the max_missing_fraction gate
    partial = dict(list(model.median_fill.items())[:n_provided])
    response = client.post(
        "/predict/rul", json={"dataset_id": "femto", "features": partial}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["features_missing"]) == len(model.feature_columns) - n_provided


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_predict_rul_treats_nan_feature_as_missing_not_as_a_real_value():
    """Regression for a review defect: a present-but-NaN feature (e.g.
    features.py's own NaN-by-design output for a degenerate signal) used to
    bypass both the median-fill and the missing-fraction gate, reaching the
    model with NaN instead of its training median."""
    model = api._load_joblib("rul_extra_trees.joblib")
    features = dict(model.median_fill)
    nan_col = model.feature_columns[0]
    features[nan_col] = float("nan")

    response = client.post(
        "/predict/rul",
        content=json.dumps({"dataset_id": "femto", "features": features}),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    body = response.json()
    assert nan_col in body["features_missing"]

    median_only = {c: v for c, v in model.median_fill.items() if c != nan_col}
    expected = client.post(
        "/predict/rul", json={"dataset_id": "femto", "features": median_only}
    ).json()
    assert body["rul_seconds"] == pytest.approx(expected["rul_seconds"])


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_predict_rul_rejects_too_many_nan_features_instead_of_predicting_on_them():
    model = api._load_joblib("rul_extra_trees.joblib")
    n_ok = max(len(model.feature_columns) // 3, 1)  # well under the 50% gate for the rest
    features = {c: float("nan") for c in model.feature_columns}
    for c in model.feature_columns[:n_ok]:
        features[c] = model.median_fill[c]

    response = client.post(
        "/predict/rul",
        content=json.dumps({"dataset_id": "femto", "features": features}),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert "missing" in response.json()["detail"].lower()


@pytest.mark.skipif(not BUNDLE_PRESENT, reason="artifacts/models/cross_domain_bundle.joblib not present")
def test_load_bundle_drops_the_unused_sn_fraction_multi_entry_to_save_memory():
    """_load_bundle only ever serves bundle["raw_seconds"] to callers
    (routing.candidates_from_bundle / reliability.BUNDLE_ENTRY); the other
    entry's full fitted model+calibrators must not stay resident in
    _MODEL_CACHE for the rest of the process's life (Hobby-tier /tmp+memory
    budget - see docs/PRODUCTION_RELEASE.md)."""
    api._MODEL_CACHE.clear()
    bundle = api._load_bundle()
    assert bundle is not None
    assert set(bundle) == {"raw_seconds"}
    # Cached value is the same trimmed dict, not the original.
    assert set(api._MODEL_CACHE[api.CROSS_DOMAIN_BUNDLE_NAME]) == {"raw_seconds"}
    # Idempotent on a second call (cache already trimmed).
    assert api._load_bundle() is bundle
    api._MODEL_CACHE.clear()


def _sha256_hex(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _mock_client(content: bytes):
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_load_joblib_deletes_the_downloaded_cache_copy_after_loading(tmp_path, monkeypatch):
    """Root-cause fix for the Hobby-tier /tmp ENOSPC (docs/PRODUCTION_RELEASE.md):
    once a downloaded artifact is safely in _MODEL_CACHE, its on-disk cache
    copy is dead weight for the rest of this process's life (_load_joblib's
    own `if name in _MODEL_CACHE` fast path never reads the file again) -
    it must be removed so a second large artifact's download has room."""
    import joblib

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(artifacts, "MODELS_DIR", models_dir)
    monkeypatch.setattr(artifacts, "MANIFEST_PATH", models_dir / "manifest.json")
    monkeypatch.setenv("ARTIFACT_CACHE_DIR", str(cache_dir))

    content_path = tmp_path / "payload.joblib"
    joblib.dump({"hello": "world"}, content_path)
    content = content_path.read_bytes()
    artifacts.MANIFEST_PATH.write_text(json.dumps({
        "artifacts": {"fake_model.joblib": {
            "sha256": _sha256_hex(content), "source_url": "https://example.com/fake_model.joblib",
        }}
    }))
    monkeypatch.setattr(artifacts, "_get_http_client", lambda: _mock_client(content))

    api._MODEL_CACHE.clear()
    model = api._load_joblib("fake_model.joblib")
    assert model == {"hello": "world"}
    assert api._MODEL_CACHE["fake_model.joblib"] == {"hello": "world"}
    cached_path = cache_dir / "fake_model.joblib"
    assert not cached_path.exists(), "downloaded cache copy must be removed after loading"

    # Still works from the in-process cache with the file gone.
    assert api._load_joblib("fake_model.joblib") == {"hello": "world"}
    api._MODEL_CACHE.clear()


def test_load_joblib_never_deletes_a_local_dev_checkout_copy(tmp_path, monkeypatch):
    """The same deletion must never touch artifacts/models/ itself (local dev,
    or a deployment that mounted the real files there) - only a downloaded
    cache copy under ARTIFACT_CACHE_DIR is disposable."""
    import joblib

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    monkeypatch.setattr(artifacts, "MODELS_DIR", models_dir)
    monkeypatch.setattr(artifacts, "MANIFEST_PATH", models_dir / "manifest.json")

    local_path = models_dir / "fake_local.joblib"
    joblib.dump({"local": True}, local_path)

    api._MODEL_CACHE.clear()
    model = api._load_joblib("fake_local.joblib")
    assert model == {"local": True}
    assert local_path.exists(), "a repo-local artifact must never be deleted"
    api._MODEL_CACHE.clear()


def test_load_joblib_is_safe_under_concurrent_cold_requests_for_the_same_name(tmp_path, monkeypatch):
    """FastAPI's sync `def` endpoints run in a thread pool - two requests for
    an uncached artifact genuinely race. Without the per-name lock in
    _load_joblib, one thread's post-load deletion of the downloaded cache
    file can run before another thread's own path.open(), raising
    FileNotFoundError instead of loading cleanly (the bug this test would
    have caught right after the /tmp-cleanup fix was first added)."""
    import threading
    import time

    import joblib

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(artifacts, "MODELS_DIR", models_dir)
    monkeypatch.setattr(artifacts, "MANIFEST_PATH", models_dir / "manifest.json")
    monkeypatch.setenv("ARTIFACT_CACHE_DIR", str(cache_dir))

    content_path = tmp_path / "payload.joblib"
    joblib.dump({"concurrent": True}, content_path)
    content = content_path.read_bytes()
    artifacts.MANIFEST_PATH.write_text(json.dumps({
        "artifacts": {"racy_model.joblib": {
            "sha256": _sha256_hex(content), "source_url": "https://example.com/racy_model.joblib",
        }}
    }))

    def slow_mock_client():
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            time.sleep(0.05)  # widen the race window
            return httpx.Response(200, content=content)

        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(artifacts, "_get_http_client", slow_mock_client)

    api._MODEL_CACHE.clear()
    results: list[object] = [None] * 8
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            results[i] = api._load_joblib("racy_model.joblib")
        except BaseException as exc:  # noqa: BLE001 - must observe every failure, not just common ones
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"concurrent _load_joblib calls raised: {errors!r}"
    assert all(r == {"concurrent": True} for r in results)
    api._MODEL_CACHE.clear()


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_predict_rul_never_serves_a_non_finite_prediction(monkeypatch):
    """RUL sanity (never NaN/Inf): api.py:1441 guards the model's raw output,
    but nothing previously exercised that guard - a regression there would
    silently serve a NaN/Inf rul_seconds instead of failing closed."""
    model = api._load_joblib("rul_extra_trees.joblib")
    monkeypatch.setattr(model.model, "predict", lambda X: __import__("numpy").array([float("nan")]))
    response = client.post(
        "/predict/rul", json={"dataset_id": "femto", "features": dict(model.median_fill)}
    )
    assert response.status_code == 503
    assert response.json()["code"] == "INVALID_MODEL_OUTPUT"


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_predict_rul_is_deterministic_for_identical_input():
    """python.md: 'Same input + same seed must produce the same metric to
    full float precision.' Three independent requests for the exact same
    feature row must return bit-identical rul_seconds, not just close."""
    model = api._load_joblib("rul_extra_trees.joblib")
    payload = {"dataset_id": "femto", "features": dict(model.median_fill)}
    results = [client.post("/predict/rul", json=payload).json()["rul_seconds"] for _ in range(3)]
    assert results[0] == results[1] == results[2]
