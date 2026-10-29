"""Fetch every model in artifacts/models/manifest.json into a directory, verifying sha256.
Usage: python3 fetch_models.py <manifest.json> <out_dir>   (stdlib only; re-runs skip verified files)"""
import hashlib, json, shutil, sys, urllib.request
from pathlib import Path

manifest, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
shutil.copy(manifest, out / "manifest.json")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


for name, entry in json.loads(manifest.read_text())["artifacts"].items():
    dest = out / name
    if dest.exists() and sha256(dest) == entry["sha256"]:
        print("ok      ", name)
        continue
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(entry["source_url"], timeout=60) as r, tmp.open("wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    if sha256(tmp) != entry["sha256"]:
        tmp.unlink()
        sys.exit(f"checksum mismatch: {name}")
    tmp.replace(dest)
    print("fetched ", name)
