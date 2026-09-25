"""Dataset profiler: what is in a folder, and can the pipeline use it?

Works on ANY folder, including one no adapter knows. Reads are bounded: at most
`sample_files` files and `sample_rows` rows each; exact row counts only for
files under `exact_count_mb` (larger ones are estimated from size and flagged).

Column mapping is conservative:
    high     the (normalised) header equals a known alias exactly
    low      the header merely contains an axis/sensor token - reported with a
             warning, never used silently
    unmapped no header, or nothing recognisable
A headerless numeric file cannot be mapped by name at all; the profiler says so
instead of guessing that column 0 is vibration. Mapping a headerless source is
exactly what a dataset adapter (adapters.py) is for.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import numpy as np
import pandas as pd

from bearing_pdm.adapters import ADAPTERS

ALIASES: dict[str, set[str]] = {
    "vibration_x": {"vibration_x", "vib_x", "acc_x", "accel_x", "acceleration_x", "ax", "x_acc",
                    "horizontal", "horizontal_acceleration", "horizontal_vibration",
                    "horizontal_vibration_signals", "accel_horizontal", "vibration_x_axis"},
    "vibration_y": {"vibration_y", "vib_y", "acc_y", "accel_y", "acceleration_y", "ay", "y_acc",
                    "vertical", "vertical_acceleration", "vertical_vibration",
                    "vertical_vibration_signals", "accel_vertical", "vibration_y_axis"},
    "vibration_z": {"vibration_z", "vib_z", "acc_z", "accel_z", "acceleration_z", "az", "z_acc",
                    "axial", "axial_acceleration", "axial_vibration", "vibration_z_axis"},
    "temperature_bearing": {"temperature_bearing", "bearing_temp", "bearing_temperature",
                            "temp_bearing", "temperature_c", "bearing_temp_c"},
    "temperature_ambient": {"temperature_ambient", "ambient_temp", "ambient_temperature",
                            "temperature_atmospheric", "atmospheric_temperature", "ambient_temp_c"},
    "timestamp": {"time", "timestamp", "datetime", "date_time", "time_s", "t", "seconds"},
    "rpm": {"rpm", "speed_rpm", "rotational_speed", "shaft_speed"},
    "current": {"current", "motor_current", "current_a"},
    "pressure": {"pressure", "pressure_bar", "pressure_pa"},
}
# Low-confidence guesses: (any of these sensor tokens, required axis token or None).
_LOW_TOKENS = {
    "vibration_x": (("acc", "vib"), "x"), "vibration_y": (("acc", "vib"), "y"),
    "vibration_z": (("acc", "vib"), "z"), "temperature_bearing": (("temp",), None),
}
TABULAR_SUFFIXES = {".csv", ".txt", ".tsv", ".dat", ""}


def _is_tabular(path: Path) -> bool:
    """Known text suffixes, no suffix, or a purely numeric one - IMS files are
    named by timestamp (2004.02.12.10.32.39), so their 'suffix' is '.39'."""
    suffix = path.suffix.lower()
    return suffix in TABULAR_SUFFIXES or suffix[1:].isdigit()


def normalise_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def map_column(name: str) -> tuple[str | None, str]:
    """(canonical name, confidence). Never maps on a vague match without saying so."""
    norm = normalise_name(name)
    for canonical, aliases in ALIASES.items():
        if norm in aliases:
            return canonical, "high"
    parts = set(norm.split("_"))
    for canonical, (sensors, axis) in _LOW_TOKENS.items():
        if any(t in p for t in sensors for p in parts) and (axis is None or axis in parts):
            return canonical, "low"
    return None, "unmapped"


def _sniff(text: str) -> tuple[str | None, bool]:
    """(delimiter, has_header) from a text sample. None = whitespace-separated."""
    first = text.splitlines()[0] if text else ""
    if "\t" not in first and "," not in first and ";" not in first:
        delimiter = None
    else:
        try:
            delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",;\t").delimiter
        except csv.Error:
            delimiter = max(",;\t", key=first.count)
    fields = first.split(delimiter) if delimiter else first.split()
    has_header = False
    for f in fields:
        try:
            float(f)
        except ValueError:
            has_header = f.strip().lower() not in {"nan", ""}
            if has_header:
                break
    return delimiter, has_header


def _count_rows(path: Path, exact_limit_bytes: int, sample_text: str) -> tuple[int, bool]:
    size = path.stat().st_size
    if size <= exact_limit_bytes:
        with open(path, "rb") as f:
            return sum(1 for _ in f), True
    lines = sample_text.splitlines()
    avg = max(1.0, len(sample_text.encode()) / max(1, len(lines)))
    return int(size / avg), False


def profile_file(path: str | Path, sample_rows: int = 5000, exact_count_mb: float = 20) -> dict:
    path = Path(path)
    out: dict = {"file": path.name, "size_bytes": path.stat().st_size, "warnings": []}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = "".join(line for _, line in zip(range(sample_rows + 1), f))
    except OSError as e:
        return out | {"readable": False, "warnings": [f"unreadable: {e}"]}
    if not text.strip():
        return out | {"readable": False, "warnings": ["empty file"]}
    delimiter, has_header = _sniff(text)
    try:
        df = pd.read_csv(io.StringIO(text), sep=delimiter if delimiter else r"\s+",
                         header=0 if has_header else None)
    except (pd.errors.ParserError, ValueError) as e:
        return out | {"readable": False, "delimiter": delimiter,
                      "warnings": [f"corrupt/unparseable: {e}".splitlines()[0]]}
    rows, exact = _count_rows(path, int(exact_count_mb * 1e6), text)
    rows -= int(has_header)
    columns = []
    for col in df.columns:
        values = pd.to_numeric(df[col], errors="coerce")
        numeric_fraction = float(values.notna().mean() + df[col].isna().mean())
        finite = values[np.isfinite(values)]
        canonical, confidence = map_column(col) if has_header else (None, "unmapped")
        columns.append({
            "name": str(col), "canonical": canonical, "confidence": confidence,
            "numeric": numeric_fraction >= 0.99,
            "nan_fraction": float(df[col].isna().mean()),
            "inf_count": int(np.isinf(values).sum()),
            "constant": bool(len(finite) > 0 and finite.nunique() == 1),
            "min": float(finite.min()) if len(finite) else None,
            "max": float(finite.max()) if len(finite) else None,
            "std": float(finite.std()) if len(finite) > 1 else None,
        })
    for c in columns:
        if not c["numeric"]:
            out["warnings"].append(f"column {c['name']}: non-numeric values (unusable as a signal)")
        if c["constant"]:
            out["warnings"].append(f"column {c['name']}: constant in the sampled rows")
        if c["inf_count"]:
            out["warnings"].append(f"column {c['name']}: {c['inf_count']} infinite values")
        if c["nan_fraction"] > 0.5:
            out["warnings"].append(f"column {c['name']}: {c['nan_fraction']:.0%} missing")
        if c["confidence"] == "low":
            out["warnings"].append(f"column {c['name']}: guessed as {c['canonical']} from its name "
                                   "(low confidence - confirm before use)")
    if not has_header:
        out["warnings"].append("no header row: column meanings cannot be inferred from names; "
                               "a dataset adapter is required")
    return out | {"readable": True, "delimiter": delimiter or "whitespace", "has_header": has_header,
                  "n_columns": int(df.shape[1]), "rows": rows, "rows_exact": exact,
                  "columns": columns}


def _sampling_rate(profile: dict, folder: Path) -> tuple[float | None, str]:
    """Only from evidence: a time column's median step, else a matching adapter's
    documented rate. Never assumed."""
    for f in profile["files"]:
        time_cols = [c for c in f.get("columns", []) if c["canonical"] == "timestamp"]
        if time_cols and f.get("rows", 0) > 1:
            sep = r"\s+" if f["delimiter"] == "whitespace" else f["delimiter"]
            df = pd.read_csv(folder / f["relative_path"], nrows=2000, sep=sep)
            step = np.median(np.diff(pd.to_numeric(df[time_cols[0]["name"]], errors="coerce")))
            if np.isfinite(step) and step > 0:
                return float(1.0 / step), f"time column '{time_cols[0]['name']}'"
    if profile["known_datasets"]:
        run = profile["known_datasets"][0]
        return run["sampling_rate_hz"], f"documented rate of the {run['dataset_id']} adapter"
    return None, "unknown (no time column and no matching adapter)"


def detect_datasets(folder: str | Path) -> list[dict]:
    """Every adapter whose discover() accepts this folder - or its parent or
    grandparent, so a single bearing's folder is recognised as part of a known
    dataset (`root_level` says which level matched)."""
    folder = Path(folder).resolve()
    for level, root in (("folder", folder), ("parent", folder.parent),
                        ("grandparent", folder.parent.parent)):
        found = []
        for dataset_id, adapter in ADAPTERS.items():
            try:
                runs = adapter.discover(root)
            except (FileNotFoundError, ValueError, KeyError, OSError):
                continue
            if level != "folder":
                runs = [r for r in runs if folder in (Path(r.source).resolve(),
                                                      *Path(r.source).resolve().parents)]
            if runs:
                found.append({"dataset_id": dataset_id, "display_name": adapter.display_name,
                              "root_level": level, "n_bearings": len(runs),
                              "bearings": [r.bearing_id for r in runs][:20],
                              "sampling_rate_hz": runs[0].sampling_rate_hz})
        if found:
            return found
    return []


def profile_folder(folder: str | Path, sample_files: int = 5, sample_rows: int = 5000) -> dict:
    """Profile a folder (recursively). Returns a JSON-serialisable dict."""
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"Not a directory: {folder}")
    files = sorted(p for p in folder.rglob("*")
                   if p.is_file() and _is_tabular(p) and not p.name.startswith("."))
    step = max(1, len(files) // sample_files)
    sampled = files[::step][:sample_files]
    profile: dict = {
        "folder": folder.name, "n_files": len(files),
        "total_bytes": int(sum(p.stat().st_size for p in files)),
        "known_datasets": detect_datasets(folder),
        "files": [profile_file(p, sample_rows) | {"relative_path": str(p.relative_to(folder))}
                  for p in sampled],
        "warnings": [],
    }
    readable = [f for f in profile["files"] if f.get("readable")]
    if not files:
        profile["warnings"].append("no tabular files found")
    if len(readable) < len(profile["files"]):
        profile["warnings"].append(
            f"{len(profile['files']) - len(readable)} of {len(profile['files'])} sampled files "
            "unreadable, empty or corrupt")
    if len({f["n_columns"] for f in readable}) > 1:
        profile["warnings"].append("inconsistent column count across sampled files: "
                                   f"{sorted({f['n_columns'] for f in readable})}")
    if readable:
        rows = [f["rows"] for f in readable]
        if max(rows) > 1.05 * min(rows) + 1:
            profile["warnings"].append(f"row count varies across sampled files ({min(rows)}-{max(rows)})")
    rate, source = _sampling_rate(profile, folder)
    profile["sampling_rate_hz"], profile["sampling_rate_source"] = rate, source
    mapped = {c["canonical"] for f in readable for c in f.get("columns", []) if c["canonical"]}
    profile["channels_found"] = sorted(mapped)
    if not profile["known_datasets"]:
        profile["warnings"].append("no adapter recognises this folder: profiling only - RUL/HI "
                                   "cannot be run until an adapter maps it to the canonical format")
        if not any(m.startswith("vibration") for m in mapped):
            profile["warnings"].append("no vibration channel could be identified by name")
    if rate is None:
        profile["warnings"].append("sampling rate unknown: frequency features cannot be computed")
    return profile


# ---------------------------------------------------------------------------
# Full per-recording audit (reads every sample; used for docs/college-audit.md)
# ---------------------------------------------------------------------------

# A 1 s window whose RMS is below this fraction of its recording's median 1 s
# RMS is "low activity" - e.g. the shaft stopped. The college rig's description
# states an on/off duty cycle, so this is checked rather than assumed away.
LOW_ACTIVITY_FRACTION = 0.2


def _window_rms(x: np.ndarray, n: int) -> np.ndarray:
    x = x[: len(x) // n * n].reshape(-1, n)
    return np.sqrt(np.nanmean(x ** 2, axis=1))


def audit_recordings(adapter, run, hash_files: bool = True) -> pd.DataFrame:
    """One row per recording: exact sample count, per-channel NaN/Inf counts,
    min/max/std, constant/clipping flags, low-activity 1 s windows, time gap to
    the previous recording, and the source file's SHA-256 (duplicate detection)."""
    import hashlib

    from bearing_pdm.features import CLIP_FRACTION_LIMIT, signal_quality

    rows, prev_elapsed = [], None
    fs = run.sampling_rate_hz
    for rec in adapter.recordings(run):
        row = {"recording_id": rec.recording_id, "sequence_index": rec.sequence_index,
               "elapsed_s": rec.elapsed_s,
               "gap_s": None if prev_elapsed is None else rec.elapsed_s - prev_elapsed}
        prev_elapsed = rec.elapsed_s
        for ch, x in rec.signals.items():
            x = np.asarray(x, dtype=float)
            finite = x[np.isfinite(x)]
            q = signal_quality(x, ch)
            row |= {
                f"{ch}_n": int(x.size), f"{ch}_nan": int(np.isnan(x).sum()),
                f"{ch}_inf": int(np.isinf(x).sum()),
                f"{ch}_min": float(finite.min()) if finite.size else np.nan,
                f"{ch}_max": float(finite.max()) if finite.size else np.nan,
                f"{ch}_std": float(finite.std()) if finite.size else np.nan,
                f"{ch}_constant": bool(q[f"qc_{ch}_constant"]),
                # Saturation is a vibration-sensor failure; a slow, quantised
                # temperature legitimately repeats its maximum many times.
                f"{ch}_clipped": ch.startswith("vibration")
                and bool(q[f"qc_{ch}_clip_fraction"] > CLIP_FRACTION_LIMIT),
            }
            if ch.startswith("vibration") and x.size >= fs:
                rms = _window_rms(np.where(np.isfinite(x), x, np.nan), int(fs))
                row[f"{ch}_low_activity_windows"] = int(
                    (rms < LOW_ACTIVITY_FRACTION * np.nanmedian(rms)).sum())
                row[f"{ch}_n_windows_1s"] = int(rms.size)
        if hash_files:
            h = hashlib.sha256()
            with open(rec.source_path, "rb") as f:
                for block in iter(lambda: f.read(1 << 22), b""):
                    h.update(block)
            row["sha256"] = h.hexdigest()
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_audit(audit: pd.DataFrame, expected_interval_s: float | None) -> dict:
    """Dataset-level quality summary from `audit_recordings` output."""
    channels = sorted({c[:-2] for c in audit.columns if c.endswith("_n") and not c.startswith("n")})
    out: dict = {
        "n_recordings": int(len(audit)),
        "duplicate_files": int(audit["sha256"].duplicated().sum()) if "sha256" in audit else None,
        "samples_per_recording": sorted({int(v) for c in channels for v in audit[f"{c}_n"].dropna()}),
    }
    if expected_interval_s and audit["gap_s"].notna().any():
        gaps = audit["gap_s"].dropna()
        out["interval_s"] = {"median": float(gaps.median()), "min": float(gaps.min()),
                             "max": float(gaps.max())}
        out["missing_recordings_estimate"] = int(
            ((gaps / expected_interval_s).round() - 1).clip(lower=0).sum())
        out["irregular_gaps"] = audit.loc[(gaps - expected_interval_s).abs().reindex(audit.index)
                                          > 0.5 * expected_interval_s,
                                          ["recording_id", "gap_s"]].to_dict(orient="records")
    for c in channels:
        out[c] = {
            "recordings_with_nan": int((audit[f"{c}_nan"] > 0).sum()),
            "total_nan_samples": int(audit[f"{c}_nan"].sum()),
            "recordings_with_inf": int((audit[f"{c}_inf"] > 0).sum()),
            "constant_recordings": int(audit[f"{c}_constant"].sum()),
            "clipped_recordings": int(audit[f"{c}_clipped"].sum()),
            "min": float(audit[f"{c}_min"].min()), "max": float(audit[f"{c}_max"].max()),
        }
        if f"{c}_low_activity_windows" in audit:
            out[c]["recordings_with_low_activity"] = int((audit[f"{c}_low_activity_windows"] > 0).sum())
            out[c]["low_activity_windows_total"] = int(audit[f"{c}_low_activity_windows"].sum())
    return out
