#!/usr/bin/env python3
"""Package reviewable source/docs/evidence. Exclude every key/image/runtime."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".agents", ".aws", ".codex", ".venv", ".lab", ".vagrant", ".pytest_cache", "__pycache__", "rendered", "container-logs"}
target = ROOT / "artifacts/network-infra-project.zip"
files = []
for path in sorted(ROOT.rglob("*")):
    if not path.is_file() or path.is_symlink():
        continue
    relative = path.relative_to(ROOT)
    if any(part in SKIP for part in relative.parts) or path.suffix in {".key", ".dump", ".pyc", ".zip"}:
        continue
    if path.name in {".env", "package-manifest.json"}:
        continue
    files.append(path)
manifest = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
(ROOT / "artifacts/package-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, "network-infra/" + str(path.relative_to(ROOT)))
    archive.write(ROOT / "artifacts/package-manifest.json", "network-infra/artifacts/package-manifest.json")
print(f"{target} ({target.stat().st_size / 1024:.1f} KiB, {len(files)} files)")
