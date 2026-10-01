#!/usr/bin/env python3
"""Linux health snapshot with JSON logs, metrics and meaningful exit codes."""
import argparse
import fcntl
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def memory_percent(meminfo):
    values = {}
    for line in meminfo.splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.split()[0])
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable")
    if total <= 0 or available is None or not 0 <= available <= total:
        raise ValueError("MemTotal/MemAvailable unavailable or invalid")
    return (total - available) * 100.0 / total


def evaluate(metrics, thresholds, services, backup_age=None):
    failures = []
    for name in ("memory_percent", "disk_percent", "inode_percent", "load_per_cpu"):
        value = metrics[name]
        if not math.isfinite(value) or value >= thresholds[name]:
            failures.append(f"{name}={value:.2f} exceeds {thresholds[name]}")
    failures.extend(f"Service inactive: {name}" for name, active in services.items() if not active)
    if backup_age is not None and (not math.isfinite(backup_age) or backup_age > thresholds["backup_max_age_hours"]):
        failures.append(f"Backup is missing/stale: {backup_age:.2f} hours")
    return failures


def append_json(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        handle.flush()


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".metrics-")
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(text)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def backup_age_hours(directory, now, database="labapp"):
    # Only complete packages with a matching checksum count as recent.
    from validate_backup import validate
    timestamps = []
    for package in Path(directory).glob(f"{database}_20*"):
        try:
            manifest = validate(package)
            timestamp = datetime.fromisoformat(manifest["created_at"]).timestamp()
            if timestamp <= now + 300:
                timestamps.append(timestamp)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return (now - max(timestamps)) / 3600 if timestamps else None


def snapshot(config):
    usage = shutil.disk_usage(config.get("disk_path", "/"))
    fs = os.statvfs(config.get("disk_path", "/"))
    metrics = {
        "memory_percent": memory_percent(Path("/proc/meminfo").read_text()),
        "disk_percent": usage.used * 100.0 / usage.total,
        "inode_percent": (fs.f_files - fs.f_favail) * 100.0 / fs.f_files if fs.f_files else 0,
        "load_per_cpu": os.getloadavg()[0] / max(os.cpu_count() or 1, 1),
    }
    services = {}
    for name in config.get("services", []):
        try:
            result = subprocess.run(["systemctl", "is-active", "--quiet", name], timeout=5, check=False, capture_output=True)
            services[name] = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            services[name] = False
    age = None
    if config.get("backup_directory"):
        age = backup_age_hours(config["backup_directory"], time.time(), config.get("backup_database", "labapp"))
    thresholds = {"memory_percent": 90, "disk_percent": 85, "inode_percent": 90, "load_per_cpu": 2, "backup_max_age_hours": 26}
    thresholds.update(config.get("thresholds", {}))
    failures = evaluate(metrics, thresholds, services, age)
    if config.get("backup_directory") and age is None:
        failures.append("No valid backup package found")
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": os.uname().nodename,
        "healthy": not failures,
        "metrics": metrics,
        "services": services,
        "backup_age_hours": age,
        "failures": failures,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/etc/network-lab/health.json")
    parser.add_argument("--log", default="/var/log/network-lab/health.jsonl")
    parser.add_argument("--metrics", default="/var/lib/network-lab/health.prom")
    args = parser.parse_args()
    try:
        report = snapshot(json.loads(Path(args.config).read_text()))
        append_json(Path(args.log), report)
        lines = [f"lab_health_ok {int(report['healthy'])}"]
        lines.extend(f"lab_{key} {value:.6f}" for key, value in report["metrics"].items())
        atomic_write(Path(args.metrics), "\n".join(lines) + "\n")
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["healthy"] else 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"healthy": False, "error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
