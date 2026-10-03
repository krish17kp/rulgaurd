"""Compare chunked windows against independently sliced full-file inputs."""

import numpy as np
import pandas as pd
import pytest

from bearing_pdm.chunked import WindowReport, iter_csv_window_features
from bearing_pdm.features import frequency_domain_features, time_domain_features


@pytest.mark.parametrize("chunk_rows", [1, 3, 8, 11, 32])
@pytest.mark.parametrize("overlap", [0, 3, 7])
@pytest.mark.parametrize("length", [0, 5, 8, 16, 1031])
def test_whole_file_equivalence(tmp_path, chunk_rows, overlap, length):
    path = tmp_path / "signal.csv"
    x = np.sin(np.arange(length) * 0.71)
    x[:8] = np.nan
    x[19::23] = np.nan
    pd.DataFrame({"vibration": x, "unused": np.arange(length)}).to_csv(path, index=False)
    whole = pd.read_csv(path)["vibration"].to_numpy()
    report = WindowReport()
    stream = iter_csv_window_features(
        path, vibration_column="vibration", window_samples=8,
        overlap_samples=overlap, chunk_rows=chunk_rows, sample_rate_hz=100,
        report=report,
    )
    count = 0
    for start in range(0, length - 8 + 1, 8 - overlap):
        actual = next(stream)
        segment = whole[start:start + 8]
        expected = time_domain_features(segment, "vibration")
        expected.update(frequency_domain_features(segment, 100, "vibration"))
        assert (actual.row_start, actual.row_stop) == (start, start + 8)
        assert actual.features.keys() == expected.keys()
        np.testing.assert_allclose(list(actual.features.values()), list(expected.values()),
                                   rtol=0, atol=0, equal_nan=True)
        count += 1
    assert list(stream) == []
    assert report.completed
    assert report.rows_read == length
    assert report.windows_emitted == count
    assert report.trailing_partial_rows == length - count * (8 - overlap)
    assert report.peak_rows_held <= chunk_rows + 8


def test_blank_rows_preserved(tmp_path):
    path = tmp_path / "missing.csv"
    path.write_text("vibration\n1\n\n3\n4\n")
    report = WindowReport()
    rows = list(iter_csv_window_features(
        path, vibration_column="vibration", window_samples=2, overlap_samples=0,
        chunk_rows=1, sample_rate_hz=100, report=report,
    ))
    assert report.rows_read == 4
    assert [r.features["vibration_mean"] for r in rows] == [1, 3.5]


@pytest.mark.parametrize("override", [
    {"window_samples": 0}, {"window_samples": 1.5}, {"chunk_rows": 0},
    {"chunk_rows": True}, {"overlap_samples": -1}, {"overlap_samples": 8},
    {"sample_rate_hz": 0}, {"sample_rate_hz": float("nan")},
    {"sample_rate_hz": float("inf")}, {"vibration_column": ""},
])
def test_invalid_parameters(tmp_path, override):
    kwargs = dict(vibration_column="vibration", window_samples=8, overlap_samples=0,
                  chunk_rows=3, sample_rate_hz=100, report=WindowReport())
    kwargs.update(override)
    with pytest.raises(ValueError):
        list(iter_csv_window_features(tmp_path / "unopened.csv", **kwargs))


@pytest.mark.parametrize("contents", ["other\n1\n", "vibration\ninvalid\n"])
def test_invalid_column_fails_closed(tmp_path, contents):
    path = tmp_path / "invalid.csv"
    path.write_text(contents)
    report = WindowReport()
    with pytest.raises(ValueError):
        list(iter_csv_window_features(
            path, vibration_column="vibration", window_samples=8, overlap_samples=0,
            chunk_rows=3, sample_rate_hz=100, report=report,
        ))
    assert not report.completed


def test_large_stream_reuses_one_window(tmp_path, monkeypatch):
    import bearing_pdm.chunked as chunked

    path = tmp_path / "large.csv"
    with path.open("w") as handle:
        handle.write("vibration\n")
        for _ in range(10000):
            handle.write("1\n2\n3\n4\n")
    original_read = pd.read_csv
    original_time = chunked.time_domain_features
    buffer = None
    chunks_seen = 0

    class CheckedReader:
        def __enter__(self):
            self.reader = original_read(path, usecols=["vibration"], dtype="float64",
                                        chunksize=127)
            return self

        def __exit__(self, *args):
            self.reader.close()

        def __next__(self):
            nonlocal chunks_seen
            frame = next(self.reader)
            assert len(frame) <= 127
            chunks_seen += 1
            return frame

    def checked_read(*args, **kwargs):
        assert kwargs["chunksize"] == 127
        assert kwargs["usecols"] == ["vibration"]
        return CheckedReader()

    def checked_features(values, prefix):
        nonlocal buffer
        if buffer is None:
            buffer = values
        assert values is buffer
        assert values.shape == (256,)
        return original_time(values, prefix)

    monkeypatch.setattr(chunked.pd, "read_csv", checked_read)
    monkeypatch.setattr(chunked, "time_domain_features", checked_features)
    report = WindowReport()
    for _ in iter_csv_window_features(
        path, vibration_column="vibration", window_samples=256, overlap_samples=128,
        chunk_rows=127, sample_rate_hz=100, report=report,
    ):
        pass
    assert report.rows_read == 40000
    assert chunks_seen == 315
    assert report.peak_rows_held == 383
    assert report.completed


def test_large_overlap_shift_is_vectorised(tmp_path, monkeypatch):
    import time

    import bearing_pdm.chunked as chunked

    # Features are stubbed so the timing isolates the per-window overlap shift,
    # which was an interpreted loop of overlap_samples steps per window.
    window, overlap, windows = 200_000, 199_999, 201
    x = np.arange(window + windows - 1, dtype=np.float64)
    path = tmp_path / "large_overlap.csv"
    pd.DataFrame({"vibration": x}).to_csv(path, index=False)
    monkeypatch.setattr(chunked, "time_domain_features",
                        lambda values, prefix: {"first": values[0], "last": values[-1]})
    monkeypatch.setattr(chunked, "frequency_domain_features", lambda *args: {})
    report = WindowReport()
    started = time.perf_counter()
    rows = list(iter_csv_window_features(
        path, vibration_column="vibration", window_samples=window,
        overlap_samples=overlap, chunk_rows=65_536, sample_rate_hz=100, report=report,
    ))
    elapsed = time.perf_counter() - started
    assert len(rows) == windows
    for index, row in enumerate(rows):
        assert row.features == {"first": index, "last": index + window - 1}
    assert elapsed < 3, f"{elapsed:.1f}s for {windows} heavily overlapping windows"
