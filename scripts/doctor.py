#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def probe(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
        return {"ok": result.returncode == 0, "detail": (result.stdout + result.stderr).strip()[-1500:]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"ok": False, "detail": str(error)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-vm", action="store_true")
    args = parser.parse_args()
    provider = os.environ.get("LAB_PROVIDER", "virtualbox")
    checks = {
        "python": probe(["python3", "--version"]),
        "vagrant": probe(["vagrant", "--version"]),
        "qemu": probe(["qemu-system-x86_64", "--version"]),
        "qemu_img": probe(["qemu-img", "--version"]),
        "docker": probe(["docker", "info", "--format", "{{.ServerVersion}}"]),
        "controller": {"ok": (ROOT / ".venv/bin/ansible-playbook").exists(), "detail": "./labctl bootstrap"},
        "virtualbox": probe(["VBoxManage", "--version"]),
        "libvirt": probe(["virsh", "-c", "qemu:///system", "list", "--all"]),
        "kvm": {"ok": os.access("/dev/kvm", os.R_OK | os.W_OK), "detail": "/dev/kvm must be accessible for the libvirt path"},
        "vagrant_libvirt": probe(["vagrant", "plugin", "list"]),
        "free_disk": {"ok": shutil.disk_usage(ROOT).free >= 12 * 1024**3, "detail": f"{shutil.disk_usage(ROOT).free / 1024**3:.1f} GiB available (recommend >=12)"},
    }
    plugins = checks["vagrant_libvirt"]
    plugins["ok"] = plugins["ok"] and "vagrant-libvirt" in plugins["detail"]
    vm_ready = checks["vagrant"]["ok"] and checks["controller"]["ok"] and checks["free_disk"]["ok"]
    if provider == "virtualbox":
        vm_ready = vm_ready and checks["virtualbox"]["ok"]
    elif provider == "libvirt":
        vm_ready = vm_ready and all(checks[key]["ok"] for key in ("libvirt", "kvm", "vagrant_libvirt"))
    elif provider == "qemu":
        vm_ready = checks["controller"]["ok"] and checks["free_disk"]["ok"] and checks["qemu"]["ok"] and checks["qemu_img"]["ok"]
    else:
        vm_ready = False
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "provider": provider, "vm_ready": vm_ready, "checks": checks}
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts/preflight.json").write_text(json.dumps(report, indent=2) + "\n")
    for name, check in checks.items():
        print(f"{'OK' if check['ok'] else 'MISSING':7} {name}: {check['detail']}")
    if args.require_vm and not vm_ready:
        print("VM prerequisites missing. See docs/SETUP.md; Docker integration remains available.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
