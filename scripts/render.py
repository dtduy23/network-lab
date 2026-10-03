#!/usr/bin/env python3
"""Render the SAME role templates into fixtures for real service verification."""
import ipaddress
import json
import shutil
from pathlib import Path
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]


def validate_topology(lab):
    dmz = ipaddress.ip_network(lab["lab_dmz_cidr"])
    lan = ipaddress.ip_network(lab["lab_lan_cidr"])
    if dmz.version != 4 or lan.version != 4 or dmz.prefixlen != 24 or lan.prefixlen != 24 or dmz.overlaps(lan):
        raise ValueError("Lab requires two disjoint IPv4 /24 networks")
    addresses = {
        "lab_router_dmz": dmz, "lab_server_ip": dmz,
        "lab_router_lan": lan, "lab_client_ip": lan,
        "lab_dhcp_start": lan, "lab_dhcp_end": lan,
    }
    for field, subnet in addresses.items():
        address = ipaddress.ip_address(lab[field])
        if address not in subnet or address in {subnet.network_address, subnet.broadcast_address}:
            raise ValueError(f"Invalid {field}")
    if not int(ipaddress.ip_address(lab["lab_dhcp_start"])) <= int(ipaddress.ip_address(lab["lab_client_ip"])) <= int(ipaddress.ip_address(lab["lab_dhcp_end"])):
        raise ValueError("DHCP reservation must be inside the pool")
    macs = [value for node in lab["lab_nodes"].values() for key, value in node.items() if key.endswith("_mac")]
    if len(macs) != len(set(macs)):
        raise ValueError("NIC MAC addresses must be unique")
    if lab["lab_router_dmz"] == lab["lab_server_ip"] or lab["lab_router_lan"] == lab["lab_client_ip"]:
        raise ValueError("Guest addresses collide")


def render(output=None):
    output = Path(output) if output else ROOT / "artifacts/rendered"
    lab = yaml.safe_load((ROOT / "lab.yml").read_text())
    validate_topology(lab)
    env = Environment(loader=FileSystemLoader(str(ROOT / "ansible/roles")), undefined=StrictUndefined, keep_trailing_newline=True, trim_blocks=True, lstrip_blocks=True)
    for name in lab["lab_nodes"]:
        context = {**lab, "inventory_hostname": name, "mgmt_iface": "wan0" if name == "router" else "mgmt0", "mgmt_cidr": "172.29.240.0/24"}
        files = {
            "network/templates/netplan.yaml.j2": "etc/netplan/90-network-lab.yaml",
            "operations/templates/health.json.j2": "etc/network-lab/health.json",
        }
        if name == "router":
            files.update({"router/templates/dnsmasq.conf.j2": "etc/dnsmasq.d/network-lab.conf", "router/templates/iptables.rules.j2": "etc/network-lab/iptables.rules"})
        else:
            files["endpoint/templates/ufw.sh.j2"] = "etc/network-lab/apply-ufw.sh"
        if name == "server":
            files.update({
                "server/templates/named.conf.options.j2": "etc/bind/named.conf.options",
                "server/templates/named.conf.local.j2": "etc/bind/named.conf.local",
                "server/templates/db.forward.j2": "etc/bind/zones/db.infra.test",
                "server/templates/db.dmz.reverse.j2": "etc/bind/zones/db.10.20.10",
                "server/templates/db.lan.reverse.j2": "etc/bind/zones/db.10.20.20",
                "server/templates/nginx.conf.j2": "etc/nginx/sites-available/network-lab",
                "operations/templates/backup.env.j2": "etc/network-lab/backup.env",
            })
        for template, target in files.items():
            path = output / name / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(env.get_template(template).render(**context))
        operations = ROOT / "ansible/roles/operations/files"
        for file in operations.glob("*.service"):
            path = output / name / "etc/systemd/system" / file.name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, path)
        for file in operations.glob("*.timer"):
            shutil.copyfile(file, output / name / "etc/systemd/system" / file.name)
        for file in (output / name / "etc").rglob("*"):
            if file.suffix == ".json":
                json.loads(file.read_text())
            if file.suffix == ".yaml":
                yaml.safe_load(file.read_text())
    print(f"Rendered lab configuration: {output}")
    return output


if __name__ == "__main__":
    render()
