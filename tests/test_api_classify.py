"""Direct boundary tests for the fail-closed dataset compatibility classifier."""

import math

import pytest

from bearing_pdm.api import _classify, _classify_detailed
from bearing_pdm.profiler import profile_file


@pytest.mark.parametrize(
    "profile, reasons",
    [
        ({"readable": False, "warnings": ["unreadable: denied"]}, ["unreadable: denied"]),
        ({"readable": False}, ["file could not be read"]),
        ({}, ["file could not be read"]),
    ],
)
def test_unreadable_profile_returns_warning_or_fallback(profile, reasons):
    assert _classify(profile) == ("INVALID_INPUT", reasons)


@pytest.mark.parametrize(
    "csv_text, state, reason",
    [
        pytest.param("", "INVALID_INPUT", "empty file", id="empty"),
        pytest.param("1,2\n3,4\n", "ADAPTER_REQUIRED", "no header row", id="headerless"),
        pytest.param(
            "timestamp,temperature_bearing\n1,20\n2,21\n",
            "UNSUPPORTED", "no vibration channel recognised", id="non-vibration",
        ),
        pytest.param(
            "machine_vib_x,vibration_y\n1,2\n3,4\n",
            "ADAPTER_REQUIRED", "low-confidence name guess", id="low-confidence-with-good-channel",
        ),
        pytest.param(
            "vibration_x,vibration_y\n", "INVALID_INPUT", "no data rows", id="header-only",
        ),
        pytest.param(
            "vibration_x,timestamp\nabc,1\ndef,2\n",
            "INVALID_INPUT", "vibration_x: non-numeric values", id="non-numeric",
        ),
        pytest.param(
            "vibration_x,timestamp\n1,1\n1,2\n",
            "INVALID_INPUT", "vibration_x: constant in the sampled rows", id="constant",
        ),
        pytest.param(
            "vibration_x,timestamp\n1,1\n2,2\ninf,3\n",
            "INVALID_INPUT", "vibration_x: 1 infinite values", id="one-infinite",
        ),
        pytest.param(
            "vibration_x,timestamp\ninf,1\n-inf,2\n",
            "INVALID_INPUT", "vibration_x: 2 infinite values", id="all-infinite",
        ),
    ],
)
def test_classify_real_csv_rejections(tmp_path, csv_text, state, reason):
    path = tmp_path / "input.csv"
    path.write_text(csv_text, encoding="utf-8")
    profile = profile_file(path)

    actual_state, reasons = _classify(profile)

    assert actual_state == state
    assert len(reasons) == 1
    assert reason in reasons[0]


@pytest.mark.parametrize("missing_rows", [2, 3])
def test_real_csv_missing_fraction_boundary(tmp_path, missing_rows):
    # A populated timestamp keeps missing vibration cells from becoming blank
    # lines that the CSV reader would discard. Two finite values avoid constancy.
    path = tmp_path / "missing.csv"
    path.write_text(
        "vibration_x,timestamp\n1,0\n2,1\n"
        + "".join(f",{i + 2}\n" for i in range(missing_rows)),
        encoding="utf-8",
    )
    profile = profile_file(path)
    channel = profile["columns"][0]
    assert channel["numeric"]
    assert not channel["constant"]
    assert channel["inf_count"] == 0
    assert channel["nan_fraction"] == missing_rows / (2 + missing_rows)

    if missing_rows == 2:
        assert _classify(profile) == ("FULLY_SUPPORTED", [])
    else:
        assert _classify(profile) == (
            "INVALID_INPUT",
            ["vibration_x: more than 50% missing (60% rounded); at most 50% is accepted"],
        )


@pytest.mark.parametrize("fraction", [0.5, math.nextafter(0.5, math.inf)])
def test_missing_fraction_immediately_above_half_is_rejected(fraction):
    profile = {
        "readable": True,
        "has_header": True,
        "rows": 4,
        "columns": [{
            "name": "vibration_x", "canonical": "vibration_x", "confidence": "high",
            "numeric": True, "constant": False, "nan_fraction": fraction, "inf_count": 0,
        }],
    }
    expected = (
        ("FULLY_SUPPORTED", []) if fraction == 0.5
        else (
            "INVALID_INPUT",
            ["vibration_x: more than 50% missing (50% rounded); at most 50% is accepted"],
        )
    )
    assert _classify(profile) == expected


@pytest.mark.parametrize("constant_first", [False, True])
def test_one_usable_channel_suffices_regardless_of_order(tmp_path, constant_first):
    path = tmp_path / "mixed.csv"
    rows = "7,1\n7,2\n" if constant_first else "1,7\n2,7\n"
    path.write_text("vibration_x,vibration_y\n" + rows, encoding="utf-8")
    profile = profile_file(path)
    assert [c["constant"] for c in profile["columns"]] == [constant_first, not constant_first]
    assert profile["warnings"]  # A rejected channel does not invalidate a usable one.
    assert _classify(profile) == ("FULLY_SUPPORTED", [])


def test_clean_csv_has_no_rejection_reasons(tmp_path):
    path = tmp_path / "clean.csv"
    path.write_text("vibration_x,vibration_y\n1,2\n3,4\n", encoding="utf-8")
    profile = profile_file(path)
    assert profile["warnings"] == []
    assert _classify(profile) == ("FULLY_SUPPORTED", [])


def _detail(tmp_path, csv_text):
    path = tmp_path / "input.csv"
    path.write_text(csv_text, encoding="utf-8")
    return _classify_detailed(profile_file(path))


@pytest.mark.parametrize(
    "csv_text, state, kind, missing_fragment",
    [
        ("", "INVALID_INPUT", "FIX_INPUT_FILE", "readable"),
        ("1,2\n3,4\n", "ADAPTER_REQUIRED", "ADAPTER_REQUIRED", "adapters.py"),
        (
            "timestamp,temperature_bearing\n1,20\n2,21\n",
            "UNSUPPORTED", "NO_VIBRATION_CHANNEL", "vibration channel",
        ),
        (
            "machine_vib_x,vibration_y\n1,2\n3,4\n",
            "ADAPTER_REQUIRED", "ADAPTER_REQUIRED", "machine_vib_x",
        ),
        ("vibration_x,vibration_y\n", "INVALID_INPUT", "FIX_INPUT_FILE", "data rows"),
        (
            "vibration_x,timestamp\nabc,1\ndef,2\n",
            "INVALID_INPUT", "FIX_INPUT_FILE", "non-constant",
        ),
        ("vibration_x,vibration_y\n1,2\n3,4\n", "FULLY_SUPPORTED", "STRUCTURAL_CHECK_ONLY", None),
    ],
)
def test_every_state_has_a_required_action(tmp_path, csv_text, state, kind, missing_fragment):
    actual_state, _, action = _detail(tmp_path, csv_text)
    assert actual_state == state
    assert set(action) == {"kind", "message", "missing"}
    assert action["kind"] == kind
    assert action["message"]
    if missing_fragment is None:
        assert action["missing"] == []
    else:
        assert any(missing_fragment in m for m in action["missing"])


def test_headerless_action_names_adapter_and_user_metadata(tmp_path):
    _, _, action = _detail(tmp_path, "1,2\n3,4\n")
    assert any("adapters.py" in m for m in action["missing"])
    assert any("sampling_rate_hz" in m and "user-provided" in m for m in action["missing"])


def test_fully_supported_action_disclaims_model_validation(tmp_path):
    state, _, action = _detail(tmp_path, "vibration_x,vibration_y\n1,2\n3,4\n")
    assert state == "FULLY_SUPPORTED"
    assert "structurally parseable" in action["message"]
    assert "NOT mean a trained model is validated" in action["message"]
    assert "decided downstream" in action["message"]


@pytest.mark.parametrize(
    "csv_text",
    ["", "1,2\n3,4\n", "a,b\n1,2\n3,4\n", "vibration_x\n1\n2\n", "vibration_x\n1\n1\n"],
)
def test_retrain_required_is_never_emitted(tmp_path, csv_text):
    state, _, action = _detail(tmp_path, csv_text)
    assert state != "RETRAIN_REQUIRED"
    assert "RETRAIN" not in action["kind"]


def test_missing_message_states_the_threshold():
    profile = {
        "readable": True, "has_header": True, "rows": 4,
        "columns": [{
            "name": "vibration_x", "canonical": "vibration_x", "confidence": "high",
            "numeric": True, "constant": False, "nan_fraction": 0.75, "inf_count": 0,
        }],
    }
    _, reasons, _ = _classify_detailed(profile)
    assert "more than 50% missing" in reasons[0]
    assert "at most 50% is accepted" in reasons[0]
