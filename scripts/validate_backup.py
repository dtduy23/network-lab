#!/usr/bin/env python3
"""Validate exactly one complete backup package before creating a restore DB."""
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def validate(directory):
    path = Path(directory)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Backup package must be a real directory")
    dump = path / "database.dump"
    manifest_path = path / "manifest.json"
    for file in (dump, manifest_path):
        if file.is_symlink() or not file.is_file():
            raise ValueError(f"Missing or unsafe backup file: {file.name}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported backup schema")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", str(manifest.get("database", ""))):
        raise ValueError("Invalid manifest database")
    created = datetime.fromisoformat(manifest["created_at"])
    if created.tzinfo is None:
        raise ValueError("Backup timestamp must include timezone")
    if dump.stat().st_size == 0 or dump.stat().st_size != manifest["size_bytes"]:
        raise ValueError("Backup size mismatch")
    checksum = hashlib.sha256()
    with dump.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(block)
    if checksum.hexdigest() != manifest.get("sha256"):
        raise ValueError("Backup checksum mismatch")
    return manifest


if __name__ == "__main__":
    try:
        result = validate(sys.argv[1])
        print(json.dumps(result))
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        print(f"Backup rejected: {error}", file=sys.stderr)
        sys.exit(2)
