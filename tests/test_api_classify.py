"""Direct boundary tests for the fail-closed dataset compatibility classifier."""

import math

import pytest

from bearing_pdm.api import _classify
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
        assert _classify(profile) == ("INVALID_INPUT", ["vibration_x: 60% missing"])


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
        else ("INVALID_INPUT", ["vibration_x: 50% missing"])
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
