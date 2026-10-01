#!/usr/bin/env python3
"""Record local systemd failure alerts. No external messages are sent."""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from healthcheck import append_json

parser = argparse.ArgumentParser()
parser.add_argument("--unit", required=True)
parser.add_argument("--log", default="/var/log/network-lab/alerts.jsonl")
args = parser.parse_args()
result = subprocess.run(["systemctl", "show", args.unit, "--property=Result", "--value"], capture_output=True, text=True, timeout=10, check=False)
report = {"timestamp": datetime.now(timezone.utc).isoformat(), "severity": "error", "unit": args.unit, "result": result.stdout.strip() or "unknown"}
append_json(Path(args.log), report)
print(json.dumps(report))
