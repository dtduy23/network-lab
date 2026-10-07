from copy import deepcopy
from pathlib import Path
import pytest
import yaml
from inventory import parse
from render import validate_topology

ROOT = Path(__file__).resolve().parents[1]


def test_unique_topology_and_reject_overlapping_networks():
    lab = yaml.safe_load((ROOT / "lab.yml").read_text())
    validate_topology(lab)
    lab["lab_lan_cidr"] = lab["lab_dmz_cidr"]
    with pytest.raises(ValueError, match="disjoint"):
        validate_topology(lab)


def test_duplicate_mac_is_rejected():
    lab = yaml.safe_load((ROOT / "lab.yml").read_text())
    lab["lab_nodes"]["client"]["lan_mac"] = lab["lab_nodes"]["router"]["lan_mac"]
    with pytest.raises(ValueError, match="unique"):
        validate_topology(lab)


def test_ssh_inventory_handles_paths_with_spaces():
    text = "\n".join(f'Host {name}\n HostName 127.0.0.1\n User vagrant\n Port {port}\n IdentityFile "/tmp/lab space/{name}/key"' for name, port in [("router", 2222), ("server", 2200), ("client", 2201)])
    inventory = parse(text)["all"]["hosts"]
    assert inventory["server"]["ansible_port"] == 2200
    assert inventory["server"]["ansible_ssh_private_key_file"] == "/tmp/lab space/server/key"
    assert "accept-new" in inventory["server"]["ansible_ssh_common_args"]


def test_incomplete_inventory_is_rejected():
    with pytest.raises(ValueError, match="đủ"):
        parse("Host router\n HostName 127.0.0.1\n")
