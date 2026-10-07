import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from healthcheck import append_json, atomic_write, backup_age_hours, evaluate, memory_percent

THRESHOLDS = {"memory_percent": 90, "disk_percent": 85, "inode_percent": 90, "load_per_cpu": 2, "backup_max_age_hours": 26}
METRICS = {"memory_percent": 35, "disk_percent": 20, "inode_percent": 10, "load_per_cpu": 0.1}


def test_memory_uses_available_including_reclaimable_cache():
    assert memory_percent("MemTotal: 1000 kB\nMemAvailable: 700 kB\nMemFree: 20 kB\n") == 30


@pytest.mark.parametrize("text", ["MemTotal: 0 kB\nMemAvailable: 0 kB", "MemTotal: 10 kB", "MemTotal: 10 kB\nMemAvailable: 20 kB"])
def test_invalid_memory_is_an_error(text):
    with pytest.raises(ValueError):
        memory_percent(text)


def test_healthy_and_inactive_service():
    assert evaluate(METRICS, THRESHOLDS, {"named": True}) == []
    assert evaluate(METRICS, THRESHOLDS, {"named": False}) == ["Service inactive: named"]


@pytest.mark.parametrize("name,value", [("disk_percent", 85), ("inode_percent", 99), ("memory_percent", float("nan")), ("load_per_cpu", float("inf"))])
def test_threshold_boundary_and_nonfinite_metrics(name, value):
    assert evaluate({**METRICS, name: value}, THRESHOLDS, {})


def test_stale_backup_causes_failure():
    assert evaluate(METRICS, THRESHOLDS, {}, 27)
    assert not evaluate(METRICS, THRESHOLDS, {}, 1)


def test_concurrent_json_logs_are_valid_and_complete(tmp_path):
    log = tmp_path / "health.jsonl"
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda index: append_json(log, {"id": index}), range(100)))
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert sorted(item["id"] for item in records) == list(range(100))


def test_atomic_metrics_replace_no_partial_file(tmp_path):
    path = tmp_path / "metrics.prom"
    atomic_write(path, "lab_health_ok 1\n")
    atomic_write(path, "lab_health_ok 0\n")
    assert path.read_text() == "lab_health_ok 0\n"
    assert list(tmp_path.glob(".metrics-*")) == []


def test_missing_and_incomplete_backups_do_not_count(tmp_path):
    (tmp_path / "labapp_20261014_broken").mkdir()
    assert backup_age_hours(tmp_path, time.time()) is None
