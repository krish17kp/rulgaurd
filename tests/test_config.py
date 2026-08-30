"""Config loading and cross-OS path resolution (docs/decisions.md D13).

The resolution tests are regression cover for a real failure: feature batches
built on Windows recorded `data\\processed\\<id>.parquet` and absolute
`D:\\...` source paths, which made every reader (dashboard + all three model
scripts) raise FileNotFoundError after the Windows -> Linux migration.
"""

from pathlib import Path

import pytest

from bearing_pdm.config import (
    DataPaths,
    load_data_paths,
    normalize_stored_path,
    resolve_stored_path,
)

# ---------------------------------------------------------------------------
# normalize_stored_path
# ---------------------------------------------------------------------------


def test_normalize_converts_windows_separators():
    assert normalize_stored_path("data\\processed\\femto_abc.parquet") == Path(
        "data/processed/femto_abc.parquet"
    )


def test_normalize_leaves_posix_paths_untouched():
    assert normalize_stored_path("data/processed/femto_abc.parquet") == Path(
        "data/processed/femto_abc.parquet"
    )


def test_normalize_accepts_a_path_object():
    assert normalize_stored_path(Path("a/b.csv")) == Path("a/b.csv")


# ---------------------------------------------------------------------------
# resolve_stored_path
# ---------------------------------------------------------------------------


def test_resolves_windows_relative_path_to_a_real_file(tmp_path, monkeypatch):
    """The exact shape that broke the pipeline: a relative path recorded with
    backslashes, whose file really is present."""
    target = tmp_path / "data" / "processed" / "femto_abc.parquet"
    target.parent.mkdir(parents=True)
    target.write_text("x")
    monkeypatch.chdir(tmp_path)

    resolved = resolve_stored_path("data\\processed\\femto_abc.parquet")

    assert resolved.exists()
    assert resolved.name == "femto_abc.parquet"


def test_reroots_a_foreign_absolute_path_under_a_search_root(tmp_path):
    """A path recorded on another machine (`D:\\...`) resolves when the same
    file exists locally under a configured dataset directory."""
    local_root = tmp_path / "datasets" / "college"
    local_root.mkdir(parents=True)
    (local_root / "LogFile_2022-06-20-17-00-31.csv").write_text("x")

    resolved = resolve_stored_path(
        "D:\\capstone\\data\\Vibration_Bearing_RuntoFailure\\LogFile_2022-06-20-17-00-31.csv",
        [local_root],
    )

    assert resolved == local_root / "LogFile_2022-06-20-17-00-31.csv"
    assert resolved.exists()


def test_reroots_using_nested_bearing_directory(tmp_path):
    """FEMTO's layout needs more than the filename: acc_00001.csv exists under
    every bearing, so the bearing directory has to be part of the match."""
    training = tmp_path / "Training_set" / "Learning_set"
    (training / "Bearing1_1").mkdir(parents=True)
    (training / "Bearing1_1" / "acc_00001.csv").write_text("x")

    resolved = resolve_stored_path(
        "D:\\old\\femto dataset\\Training_set\\Learning_set\\Bearing1_1\\acc_00001.csv",
        [training],
    )

    assert resolved == training / "Bearing1_1" / "acc_00001.csv"


def test_prefers_an_existing_path_over_rerooting(tmp_path, monkeypatch):
    """If the stored path already resolves, it wins - re-rooting must not
    silently redirect a valid path to a same-named file elsewhere."""
    monkeypatch.chdir(tmp_path)
    real = tmp_path / "real.csv"
    real.write_text("correct")
    decoy_root = tmp_path / "decoy"
    decoy_root.mkdir()
    (decoy_root / "real.csv").write_text("wrong")

    assert resolve_stored_path("real.csv", [decoy_root]).read_text() == "correct"


def test_unresolvable_path_returns_unchanged_and_does_not_raise(tmp_path):
    """Callers (dashboard.py) handle a missing source by degrading to cached
    features, so this must never raise - and must report a sensible name."""
    resolved = resolve_stored_path("D:\\gone\\missing.csv", [tmp_path])

    assert resolved == Path("D:/gone/missing.csv")
    assert not resolved.exists()


def test_ignores_search_roots_that_do_not_exist(tmp_path):
    real_root = tmp_path / "real"
    real_root.mkdir()
    (real_root / "f.csv").write_text("x")

    resolved = resolve_stored_path("X:\\nope\\f.csv", [tmp_path / "absent", real_root])

    assert resolved == real_root / "f.csv"


# ---------------------------------------------------------------------------
# load_data_paths
# ---------------------------------------------------------------------------


def test_load_data_paths_reads_every_section(tmp_path):
    cfg = tmp_path / "data_paths.toml"
    cfg.write_text(
        '[college]\nraw_dir = "datasets/college"\n'
        '[femto]\ntraining_dir = "a"\ntest_dir = "b"\nvalidation_dir = "c"\n'
        '[output]\nprocessed_dir = "data/processed"\ninterim_dir = "data/interim"\n'
        'duckdb_path = "artifacts/metadata.duckdb"\n'
    )

    paths = load_data_paths(cfg)

    assert isinstance(paths, DataPaths)
    assert paths.college_raw_dir == Path("datasets/college")
    assert paths.duckdb_path == Path("artifacts/metadata.duckdb")


def test_missing_config_raises_with_actionable_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="data_paths.example.toml"):
        load_data_paths(tmp_path / "absent.toml")


def test_missing_section_raises_keyerror(tmp_path):
    cfg = tmp_path / "data_paths.toml"
    cfg.write_text('[college]\nraw_dir = "x"\n')

    with pytest.raises(KeyError):
        load_data_paths(cfg)


def test_source_search_roots_covers_all_raw_dataset_dirs():
    paths = DataPaths(
        college_raw_dir=Path("c"),
        femto_training_dir=Path("t"),
        femto_test_dir=Path("te"),
        femto_validation_dir=Path("v"),
        processed_dir=Path("p"),
        interim_dir=Path("i"),
        duckdb_path=Path("d"),
    )

    assert paths.source_search_roots() == (Path("c"), Path("t"), Path("te"), Path("v"))


def test_longest_suffix_wins_across_roots_not_root_order(tmp_path):
    """Root-major search would return a 1-segment match under an EARLIER root
    before trying a 3-segment match under a later one. Suffix length must win
    globally, or a Full_Test_Set path resolves into Test_set - silently crossing
    the frozen hold-out boundary (docs/decisions.md D13/D15)."""
    shallow = tmp_path / "shallow"
    (shallow).mkdir()
    (shallow / "acc_00001.csv").write_text("wrong")

    deep = tmp_path / "deep"
    (deep / "Learning_set" / "Bearing1_1").mkdir(parents=True)
    (deep / "Learning_set" / "Bearing1_1" / "acc_00001.csv").write_text("right")

    resolved = resolve_stored_path(
        "D:\\old\\Learning_set\\Bearing1_1\\acc_00001.csv",
        [shallow, deep],  # shallow deliberately first
    )
    assert resolved.read_text() == "right"


def test_ambiguous_equal_length_match_is_broken_by_root_name_overlap(tmp_path):
    """Test_set/ and Full_Test_Set/ hold identically-named bearing folders, so
    'Bearing1_3/acc_00001.csv' matches both at the same length. The stored path
    names 'Full_Test_Set', so the validation root must win."""
    test_root = tmp_path / "Test_set"
    full_root = tmp_path / "Full_Test_Set"
    for root, marker in ((test_root, "censored"), (full_root, "continuation")):
        (root / "Bearing1_3").mkdir(parents=True)
        (root / "Bearing1_3" / "acc_00001.csv").write_text(marker)

    resolved = resolve_stored_path(
        "D:\\x\\Validation_Set\\Full_Test_Set\\Bearing1_3\\acc_00001.csv",
        [test_root, full_root],  # test root deliberately first
    )
    assert resolved.read_text() == "continuation"


def test_undecidable_ambiguity_declines_to_guess(tmp_path):
    """When nothing in the stored path favours either root, returning one at
    random could cross the learning/hold-out boundary. Decline instead."""
    a, b = tmp_path / "a", tmp_path / "b"
    for root in (a, b):
        (root / "Bearing1_3").mkdir(parents=True)
        (root / "Bearing1_3" / "acc_00001.csv").write_text("x")

    stored = "D:\\somewhere\\else\\Bearing1_3\\acc_00001.csv"
    resolved = resolve_stored_path(stored, [a, b])
    assert resolved == Path("D:/somewhere/else/Bearing1_3/acc_00001.csv")


def test_anchored_stored_path_cannot_escape_the_search_roots(tmp_path):
    """joinpath() with an anchored segment discards the root entirely, so the
    anchor must be stripped before re-rooting."""
    root = tmp_path / "root"
    root.mkdir()
    resolved = resolve_stored_path("/etc/passwd", [root])
    assert resolved == Path("/etc/passwd")  # unchanged, never re-rooted under root


def test_directory_matching_the_name_is_not_accepted_as_the_file(tmp_path):
    root = tmp_path / "root"
    (root / "acc_00001.csv").mkdir(parents=True)  # a DIRECTORY with the file's name
    resolved = resolve_stored_path("D:\\x\\acc_00001.csv", [root])
    assert resolved == Path("D:/x/acc_00001.csv")  # declined, not the directory
