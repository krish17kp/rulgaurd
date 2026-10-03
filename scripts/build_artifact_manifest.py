#!/usr/bin/env python
"""Regenerate artifacts/models/manifest.json - the committed, checksummed
index of the trained artifacts that are themselves gitignored (sha256/size
only, never the binary content). src/bearing_pdm/artifacts.py's production
loader reads this to fetch-and-verify a missing artifact at cold start.

Run after any change to artifacts/models/*.joblib (e.g. after
train_models.py / build_health.py). `source_url` is preserved across runs
for any artifact whose manifest entry already has one - this script never
knows where to upload the binary; that stays a manual step (see
docs/vercel-deployment.md) because it needs real storage credentials this
environment does not have.

Usage (run from the repo root; PYTHONPATH=src is required unless bearing_pdm
is installed editable into the active venv - see docs/vercel-deployment.md):
    PYTHONPATH=src python scripts/build_artifact_manifest.py
"""

from __future__ import annotations

import json

from bearing_pdm.artifacts import MANIFEST_PATH, MODELS_DIR, _sha256_of


def main() -> None:
    existing = {}
    if MANIFEST_PATH.exists():
        existing = json.loads(MANIFEST_PATH.read_text()).get("artifacts", {})

    artifacts_entry: dict[str, dict] = {}
    for path in sorted(MODELS_DIR.glob("*.joblib")) + sorted(MODELS_DIR.glob("*.json")):
        if path.name == MANIFEST_PATH.name:
            continue
        artifacts_entry[path.name] = {
            "sha256": _sha256_of(path),
            "size_bytes": path.stat().st_size,
            "source_url": existing.get(path.name, {}).get("source_url"),
        }

    MANIFEST_PATH.write_text(json.dumps({"artifacts": artifacts_entry}, indent=2, sort_keys=True) + "\n")
    missing_urls = [name for name, entry in artifacts_entry.items() if not entry["source_url"]]
    print(f"Wrote {MANIFEST_PATH} with {len(artifacts_entry)} artifact(s).")
    if missing_urls:
        print(
            "No source_url set for: "
            + ", ".join(missing_urls)
            + " - these cannot be fetched in a deployment that lacks the local file."
        )


if __name__ == "__main__":
    main()
