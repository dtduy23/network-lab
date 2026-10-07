import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
import pytest
from validate_backup import validate

ROOT = Path(__file__).resolve().parents[1]


def package(tmp_path):
    path = tmp_path / "labapp_20261014_test"
    path.mkdir()
    payload = b"PGDMP test fixture"
    (path / "database.dump").write_bytes(payload)
    (path / "manifest.json").write_text(json.dumps({"schema_version": 1, "database": "labapp", "created_at": datetime.now(timezone.utc).isoformat(), "sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload)}))
    return path


def test_valid_package(tmp_path):
    assert validate(package(tmp_path))["database"] == "labapp"


def test_same_size_corruption_is_detected(tmp_path):
    path = package(tmp_path)
    (path / "database.dump").write_bytes(b"X" * (path / "database.dump").stat().st_size)
    with pytest.raises(ValueError, match="checksum"):
        validate(path)


@pytest.mark.parametrize("change", [{"schema_version": 2}, {"database": "x'; DROP DATABASE postgres;--"}, {"size_bytes": -1}, {"created_at": "2026-10-14T00:00:00"}])
def test_invalid_manifest_is_rejected(tmp_path, change):
    path = package(tmp_path)
    manifest = json.loads((path / "manifest.json").read_text())
    (path / "manifest.json").write_text(json.dumps({**manifest, **change}))
    with pytest.raises(ValueError):
        validate(path)


def test_symlinked_dump_is_rejected(tmp_path):
    path = package(tmp_path)
    dump = path / "database.dump"
    dump.rename(tmp_path / "external.dump")
    dump.symlink_to(tmp_path / "external.dump")
    with pytest.raises(ValueError, match="unsafe"):
        validate(path)


def fake_tools(tmp_path, pg_dump):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    commands = {
        "runuser": '#!/bin/bash\nshift 3\nexec "$@"\n',
        "pg_dump": "#!/bin/bash\n" + pg_dump,
        "pg_restore": '#!/bin/bash\nexit 0\n',
        "logger": '#!/bin/bash\nexit 0\n',
    }
    for name, text in commands.items():
        file = bin_dir / name
        file.write_text(text)
        file.chmod(0o755)
    return {**os.environ, "PATH": str(bin_dir) + ":" + os.environ["PATH"], "LAB_BACKUP_DIR": str(tmp_path / "backups")}


def test_failed_dump_has_no_partial_backup_and_preserves_old_backup(tmp_path):
    env = fake_tools(tmp_path, "printf partial\nexit 1\n")
    old = Path(env["LAB_BACKUP_DIR"]) / "labapp_20200101_old"
    old.mkdir(parents=True)
    os.utime(old, (1, 1))
    result = subprocess.run(["bash", ROOT / "scripts/backup.sh"], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert old.exists()
    assert list(old.parent.glob(".staging.*")) == []
    assert list(old.parent.glob("labapp_*")) == [old]


def test_successful_backup_commits_manifest_then_rotates(tmp_path):
    env = fake_tools(tmp_path, "printf 'PGDMP fake'\n")
    old = Path(env["LAB_BACKUP_DIR"]) / "labapp_20200101_old"
    old.mkdir(parents=True)
    os.utime(old, (1, 1))
    result = subprocess.run(["bash", ROOT / "scripts/backup.sh"], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not old.exists()
    assert validate(result.stdout.strip())["database"] == "labapp"


def test_concurrent_backups_are_serialized(tmp_path):
    env = fake_tools(tmp_path, "touch \"$LAB_BACKUP_DIR/dump-started\"\nsleep 2\nprintf 'PGDMP fake'\n")
    process = subprocess.Popen(["bash", ROOT / "scripts/backup.sh"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    marker = Path(env["LAB_BACKUP_DIR"]) / "dump-started"
    try:
        for _ in range(100):
            if marker.exists():
                break
            time.sleep(0.02)
        assert marker.exists()
        second = subprocess.run(["bash", ROOT / "scripts/backup.sh"], env=env, capture_output=True, text=True)
        assert second.returncode == 75
        process.communicate(timeout=5)
        assert process.returncode == 0
        assert len(list(marker.parent.glob("labapp_20*"))) == 1
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


@pytest.mark.parametrize("target", ["labapp", "postgres", "lab_restore_x'; DROP DATABASE labapp;--"])
def test_restore_rejects_source_and_injected_target(tmp_path, target):
    result = subprocess.run(["bash", ROOT / "scripts/restore.sh", str(tmp_path), target], capture_output=True, text=True)
    assert result.returncode == 2
    assert "Target must start" in result.stderr


def test_failed_restore_removes_only_new_database(tmp_path):
    path = package(tmp_path)
    env = fake_tools(tmp_path, "exit 0\n")
    env["LAB_BACKUP_VALIDATOR"] = str(ROOT / "scripts/validate_backup.py")
    bin_dir = tmp_path / "bin"
    (bin_dir / "psql").write_text('#!/bin/bash\nexit 0\n')
    (bin_dir / "createdb").write_text('#!/bin/bash\necho "$*" >> "$LAB_BACKUP_DIR-created"\n')
    (bin_dir / "dropdb").write_text('#!/bin/bash\necho "$*" >> "$LAB_BACKUP_DIR-dropped"\n')
    (bin_dir / "pg_restore").write_text('#!/bin/bash\nif [[ $1 == --list ]]; then exit 0; fi\nexit 1\n')
    for name in ("psql", "createdb", "dropdb", "pg_restore"):
        (bin_dir / name).chmod(0o755)
    result = subprocess.run(["bash", ROOT / "scripts/restore.sh", path, "lab_restore_failure"], env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert Path(env["LAB_BACKUP_DIR"] + "-created").read_text().strip() == "-T template0 lab_restore_failure"
    assert Path(env["LAB_BACKUP_DIR"] + "-dropped").read_text().strip() == "--if-exists lab_restore_failure"


def test_concurrent_createdb_failure_cannot_drop_other_database(tmp_path):
    path = package(tmp_path)
    env = fake_tools(tmp_path, "exit 0\n")
    env["LAB_BACKUP_VALIDATOR"] = str(ROOT / "scripts/validate_backup.py")
    bin_dir = tmp_path / "bin"
    (bin_dir / "psql").write_text('#!/bin/bash\nexit 0\n')
    (bin_dir / "createdb").write_text('#!/bin/bash\nexit 1\n')
    (bin_dir / "dropdb").write_text('#!/bin/bash\ntouch "$LAB_BACKUP_DIR-dropped"\n')
    for name in ("psql", "createdb", "dropdb"):
        (bin_dir / name).chmod(0o755)
    result = subprocess.run(["bash", ROOT / "scripts/restore.sh", path, "lab_restore_race"], env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert not Path(env["LAB_BACKUP_DIR"] + "-dropped").exists()


def test_backup_rejects_root_directory_after_path_normalization(tmp_path):
    env = {**os.environ, "LAB_BACKUP_DIR": "/tmp/.."}
    result = subprocess.run(["bash", ROOT / "scripts/backup.sh"], env=env, capture_output=True, text=True)
    assert result.returncode == 2
    assert "Unsafe backup directory" in result.stderr
