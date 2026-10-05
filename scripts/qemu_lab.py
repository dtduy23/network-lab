#!/usr/bin/env python3
"""Unprivileged full VM backend using QEMU TCG and localhost socket networks."""
import hashlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
import pycdlib
import yaml

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".lab/qemu"
BASE_URL = "https://cloud-images.ubuntu.com/noble/current/"
IMAGE_NAME = "noble-server-cloudimg-amd64.img"
PORTS = {"router": 2222, "server": 2200, "client": 2201}


def command(*argv, **options):
    return subprocess.run(list(map(str, argv)), check=True, **options)


def qmp(name, action):
    path = STATE / name / "monitor.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        connection.connect(str(path))
        with connection.makefile("rwb") as handle:
            json.loads(handle.readline())
            for request in ("qmp_capabilities", action):
                handle.write((json.dumps({"execute": request}) + "\n").encode())
                handle.flush()
                while True:
                    line = handle.readline()
                    if not line:
                        if request == "quit":
                            return
                        raise RuntimeError("QMP connection closed before response")
                    result = json.loads(line)
                    if "return" in result:
                        break
                    if "error" in result:
                        raise RuntimeError(result["error"])


def running(name):
    try:
        qmp(name, "query-status")
        return True
    except (OSError, ValueError, RuntimeError):
        return False


def prepare():
    STATE.mkdir(parents=True, exist_ok=True)
    base = STATE / IMAGE_NAME
    if not base.exists():
        command("curl", "--fail", "--location", "--retry", "3", BASE_URL + "SHA256SUMS", "-o", STATE / "SHA256SUMS")
        entries = [line.split() for line in (STATE / "SHA256SUMS").read_text().splitlines()]
        expected = next(checksum for checksum, name in entries if name.lstrip("*") == IMAGE_NAME)
        temporary = STATE / (IMAGE_NAME + ".download")
        command("curl", "--fail", "--location", "--retry", "3", BASE_URL + IMAGE_NAME, "-o", temporary)
        digest = hashlib.sha256()
        with temporary.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            temporary.unlink()
            raise RuntimeError("Ubuntu cloud image checksum mismatch; retry release download")
        temporary.rename(base)
        (STATE / "image-checksum.json").write_text(json.dumps({"url": BASE_URL + IMAGE_NAME, "sha256": expected}, indent=2) + "\n")
    key = ROOT / ".lab/keys/provision"
    if not key.exists():
        command("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "network-infra-qemu-provision", "-f", key)
    return base, key.with_suffix(".pub").read_text().strip()


def seed(name, node, public_key):
    user_data = "#cloud-config\n" + yaml.safe_dump({
        "hostname": name, "manage_etc_hosts": True,
        "ssh_pwauth": False, "disable_root": True,
        "users": [{"name": "vagrant", "groups": ["sudo"], "shell": "/bin/bash", "lock_passwd": True,
                   "sudo": ["ALL=(ALL) NOPASSWD:ALL"], "ssh_authorized_keys": [public_key]}],
    })
    meta_data = yaml.safe_dump({"instance-id": "network-infra-" + name, "local-hostname": name})
    network = yaml.safe_dump({"version": 2, "ethernets": {"management": {"match": {"macaddress": node["mgmt_mac"]}, "dhcp4": True, "dhcp6": False}}})
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3, rock_ridge="1.09", vol_ident="cidata")
    for filename, iso_filename, text in (("user-data", "USER_DAT.;1", user_data), ("meta-data", "META_DAT.;1", meta_data), ("network-config", "NET_CONF.;1", network)):
        data = text.encode()
        iso.add_fp(io.BytesIO(data), len(data), iso_path="/" + iso_filename, joliet_path="/" + filename, rr_name=filename)
    iso.write(str(STATE / name / "seed.iso"))
    iso.close()


def ssh_config():
    key = ROOT / ".lab/keys/provision"
    for name, port in PORTS.items():
        print(f'Host {name}\n  HostName 127.0.0.1\n  User vagrant\n  Port {port}\n  IdentityFile "{key}"\n  IdentitiesOnly yes\n  StrictHostKeyChecking accept-new\n  UserKnownHostsFile "{ROOT}/.lab/known_hosts"')


def up():
    backend_file = ROOT / ".lab/backend"
    if backend_file.exists() and backend_file.read_text().strip() != "qemu":
        raise RuntimeError("Another backend is recorded; halt/destroy it before selecting QEMU")
    base, public_key = prepare()
    lab = yaml.safe_load((ROOT / "lab.yml").read_text())
    # All listeners bind localhost. No bridge, tuntap, sudo or host firewall.
    for name, node in lab["lab_nodes"].items():
        if running(name):
            continue
        directory = STATE / name
        directory.mkdir(exist_ok=True)
        disk = directory / "disk.qcow2"
        if not disk.exists():
            command("qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", base, disk, "16G")
            seed(name, node, public_key)
        arguments = ["qemu-system-x86_64", "-name", "network-infra-" + name,
                     "-machine", "q35", "-accel", "tcg,thread=multi", "-cpu", "max",
                     "-smp", str(node["cpus"]), "-m", str(int(node["memory"] * float(os.environ.get("LAB_QEMU_MEMORY_SCALE", "0.666667")))),
                     "-drive", f"file={disk},format=qcow2,if=virtio", "-drive", f"file={directory / 'seed.iso'},format=raw,media=cdrom,readonly=on",
                     "-display", "none", "-monitor", "none", "-serial", f"file:{directory / 'console.log'}",
                     "-qmp", f"unix:{directory / 'monitor.sock'},server=on,wait=off", "-pidfile", str(directory / "pid"), "-daemonize"]
        management = f"user,id=mgmt,hostfwd=tcp:127.0.0.1:{PORTS[name]}-:22"
        if name == "router":
            management += ",hostfwd=tcp:127.0.0.1:8080-:8080"
        arguments += ["-netdev", management, "-device", f"virtio-net-pci,netdev=mgmt,mac={node['mgmt_mac']}"]
        for segment, port in (("dmz", 22110), ("lan", 22120)):
            if segment + "_mac" in node:
                mode = "listen" if name == "router" else "connect"
                arguments += ["-netdev", f"socket,id={segment},{mode}=127.0.0.1:{port}", "-device", f"virtio-net-pci,netdev={segment},mac={node[segment + '_mac']}"]
        command(*arguments)
        backend_file.write_text("qemu\n")
        print(f"Started {name} with QEMU software emulation", flush=True)
    for name, port in PORTS.items():
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            try:
                result = subprocess.run(["ssh", "-i", str(ROOT / ".lab/keys/provision"), "-p", str(port), "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={ROOT}/.lab/known_hosts", "vagrant@127.0.0.1", "true"], capture_output=True, timeout=10, check=False)
            except subprocess.TimeoutExpired:
                time.sleep(3)
                continue
            if result.returncode == 0:
                print(f"SSH ready: {name}", flush=True)
                break
            time.sleep(3)
        else:
            raise RuntimeError(f"{name} SSH not ready; inspect {STATE / name / 'console.log'}")


def stop(destroy=False):
    for name in reversed(list(PORTS)):
        if not running(name):
            continue
        qmp(name, "quit" if destroy else "system_powerdown")
        deadline = time.monotonic() + 90
        while running(name) and time.monotonic() < deadline:
            time.sleep(1)
        if running(name):
            raise RuntimeError(f"{name} still running; data retained. Inspect console.log.")
        print(f"Stopped {name}", flush=True)
    if destroy:
        for name in PORTS:
            shutil.rmtree(STATE / name, ignore_errors=True)
        (ROOT / ".lab/backend").unlink(missing_ok=True)


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "up":
        up()
    elif action == "ssh-config":
        ssh_config()
    elif action in {"halt", "destroy"}:
        stop(action == "destroy")
    elif action == "ssh" and sys.argv[2] in PORTS:
        command("ssh", "-i", ROOT / ".lab/keys/provision", "-p", str(PORTS[sys.argv[2]]), "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={ROOT}/.lab/known_hosts", "vagrant@127.0.0.1")
    else:
        raise SystemExit(2)
