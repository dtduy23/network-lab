#!/usr/bin/env python3
"""Convert only Vagrant-generated SSH configuration into Ansible inventory."""
import json
import shlex
import sys
from pathlib import Path


def parse(text):
    hosts = {}
    current = None
    for line in text.splitlines():
        parts = shlex.split(line, comments=True)
        if not parts:
            continue
        key, *values = parts
        if key.lower() == "host":
            current = values[0] if len(values) == 1 else None
            if current in {"router", "server", "client"}:
                hosts[current] = {}
        elif current in hosts and len(values) == 1:
            hosts[current][key.lower()] = values[0]
    if set(hosts) != {"router", "server", "client"}:
        raise ValueError("Cần đủ router, server, client trong vagrant ssh-config")
    output = {}
    for name, attrs in hosts.items():
        output[name] = {
            "ansible_host": attrs["hostname"],
            "ansible_port": int(attrs["port"]),
            "ansible_user": attrs["user"],
            "ansible_ssh_private_key_file": attrs["identityfile"],
            # Vagrant supplies per-machine keys. Record first host key locally,
            # reject subsequent unexpected changes; never use /dev/null.
            "ansible_ssh_common_args": (
                "-o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes "
                "-o UserKnownHostsFile=.lab/known_hosts"
            ),
        }
    return {"all": {"hosts": output}}


if __name__ == "__main__":
    result = parse(Path(sys.argv[1]).read_text())
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + "\n")
