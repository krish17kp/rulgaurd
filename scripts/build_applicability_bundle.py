#!/usr/bin/env python
"""Derive artifacts/models/applicability_bundle.joblib from the full research
bundle artifacts/models/cross_domain_bundle.joblib.

This performs NO fit, NO retraining, and NO recomputation of any learned
parameter. It extracts cross_domain_bundle["raw_seconds"] - the only entry
api.py's _load_bundle ever reads (routing.candidates_from_bundle and
reliability.py both filter to "raw_seconds") - unchanged, and discards
"sn_fraction_multi" (its own fully fitted RUL model + calibrators, ~251MB of
the full bundle's ~361MB, never read by the served API).

Root cause this exists to fix: a live Vercel Hobby-tier deployment failed
with "[Errno 28] No space left on device" downloading the full 361MB
artifact just to discard 70% of it after load - disk pressure happens
during download, before any in-process trimming runs. See _load_bundle's
docstring in src/bearing_pdm/api.py.

Run after any change to cross_domain_bundle.joblib (e.g. after
scripts/build_cross_domain_bundle.py or equivalent), then re-run
scripts/build_artifact_manifest.py and upload the new file to Blob storage -
this script never uploads or knows a source_url (see build_artifact_manifest.py).

Usage (run from the repo root):
    PYTHONPATH=src python scripts/build_applicability_bundle.py
"""

from __future__ import annotations

import joblib

from bearing_pdm.artifacts import MODELS_DIR

SOURCE_NAME = "cross_domain_bundle.joblib"
DEST_NAME = "applicability_bundle.joblib"


def main() -> None:
    source_path = MODELS_DIR / SOURCE_NAME
    if not source_path.exists():
        raise SystemExit(f"{source_path} not found - nothing to derive from.")

    full_bundle = joblib.load(source_path)
    if not isinstance(full_bundle, dict) or "raw_seconds" not in full_bundle:
        raise SystemExit(f"{source_path} does not have the expected 'raw_seconds' entry.")

    # The exact same fitted object reference the full bundle holds - no copy,
    # no transformation, no refit.
    minimal_bundle = {"raw_seconds": full_bundle["raw_seconds"]}

    dest_path = MODELS_DIR / DEST_NAME
    joblib.dump(minimal_bundle, dest_path, compress=0)

    original_size = source_path.stat().st_size
    new_size = dest_path.stat().st_size
    print(f"Wrote {dest_path} ({new_size:,} bytes, was {original_size:,} bytes - "
          f"{100 * (1 - new_size / original_size):.1f}% smaller).")
    print("Next: PYTHONPATH=src python scripts/build_artifact_manifest.py, "
          "then upload the new file to Blob storage and set its source_url.")


if __name__ == "__main__":
    main()
