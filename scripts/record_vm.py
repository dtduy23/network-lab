#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / "artifacts/vm-results.json"
data = json.loads(target.read_text()) if target.exists() else {}
data.update({"verified_at": datetime.now(timezone.utc).isoformat(), "passed": "--failed" not in sys.argv, "backend": (root / ".lab/backend").read_text().strip(), "log": "artifacts/vm-verification.txt"})
if "--failed" in sys.argv:
    data["reboot_verified"] = False
if "--reboot" in sys.argv:
    data.update({"reboot_verified": True, "reboot_log": "artifacts/vm-reboot.txt"})
if "--drills" in sys.argv:
    data.update({"drills_verified": True, "drills_log": "artifacts/vm-drills.txt"})
target.write_text(json.dumps(data, indent=2) + "\n")
