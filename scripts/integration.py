#!/usr/bin/env python3
"""Exercise real services and packets in three isolated network namespaces.

NET_ADMIN applies only to the test containers. No host firewall is loaded.
Systemd/cloud-init/reboot remain VM-only checks, documented separately.
"""
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "network-infra-check:ubuntu24.04"


class Lab:
    def __init__(self):
        self.prefix = "network-infra-check-" + uuid.uuid4().hex[:10]
        self.containers = []
        self.networks = []
        self.checks = []
        self.lab = yaml.safe_load((ROOT / "lab.yml").read_text())

    def docker(self, *arguments, check=True, timeout=60, stdin=None):
        result = subprocess.run(["docker", *map(str, arguments)], capture_output=True, text=True, timeout=timeout, check=False, input=stdin)
        if check and result.returncode:
            raise RuntimeError(f"docker {' '.join(map(str, arguments[:5]))}: {(result.stdout + result.stderr)[-3500:]}")
        return result

    def execute(self, node, *command, check=True, timeout=60, stdin=None):
        options = ["-i"] if stdin is not None else []
        return self.docker("exec", *options, f"{self.prefix}-{node}", *command, check=check, timeout=timeout, stdin=stdin)

    def copy(self, node, source, destination):
        return self.docker("cp", source, f"{self.prefix}-{node}:{destination}")

    def check(self, name, action):
        start = time.monotonic()
        try:
            detail = action()
            self.checks.append({"name": name, "passed": True, "seconds": round(time.monotonic() - start, 3), "detail": detail})
            print(f"PASS {name}", flush=True)
        except Exception as error:
            self.checks.append({"name": name, "passed": False, "seconds": round(time.monotonic() - start, 3), "detail": str(error)})
            print(f"FAIL {name}: {error}", flush=True)
            raise

    def network(self, name, cidr=None):
        full_name = f"{self.prefix}-{name}"
        arguments = ["network", "create", "--label", f"network-infra.run={self.prefix}"]
        if cidr:
            gateway = cidr.split("/")[0].rsplit(".", 1)[0] + ".254"
            arguments += ["--internal", "--subnet", cidr, "--gateway", gateway]
        arguments += [full_name]
        self.docker(*arguments)
        self.networks.append(full_name)
        return full_name

    def run(self, name, network, ip=None, mac=None):
        full_name = f"{self.prefix}-{name}"
        arguments = ["run", "-d", "--name", full_name, "--label", f"network-infra.run={self.prefix}",
                     "--cap-add=NET_ADMIN", "--sysctl=net.ipv6.conf.all.disable_ipv6=1", "--network", network]
        if ip:
            arguments += ["--ip", ip]
        if mac:
            arguments += ["--mac-address", mac]
        if name == "router":
            arguments += ["--sysctl=net.ipv4.ip_forward=1"]
        self.docker(*arguments, IMAGE)
        self.containers.append(full_name)

    def rename(self, node, address, new_name):
        result = self.execute(node, "ip", "-4", "-o", "addr", "show").stdout
        names = [line.split()[1].split("@")[0] for line in result.splitlines() if f"{address}/" in line]
        if len(names) != 1:
            raise RuntimeError(f"Cannot identify {node} interface at {address}")
        old_name = names[0]
        self.execute(node, "ip", "link", "set", "dev", old_name, "down")
        self.execute(node, "ip", "link", "set", "dev", old_name, "name", new_name)
        self.execute(node, "ip", "link", "set", "dev", new_name, "up")

    def start(self):
        self.docker("info", "--format", "{{.ServerVersion}}")
        if self.docker("image", "inspect", IMAGE, check=False).returncode:
            self.docker("build", "-t", IMAGE, "-f", ROOT / "containers/Dockerfile", ROOT, timeout=1200)
        lan = self.network("lan", self.lab["lab_lan_cidr"])
        dmz = self.network("dmz", self.lab["lab_dmz_cidr"])
        wan = self.network("wan")
        self.run("router", wan)
        self.docker("network", "connect", "--ip", self.lab["lab_router_dmz"], dmz, f"{self.prefix}-router")
        self.docker("network", "connect", "--ip", self.lab["lab_router_lan"], lan, f"{self.prefix}-router")
        self.run("server", dmz, self.lab["lab_server_ip"])
        self.run("client", lan, self.lab["lab_client_ip"], self.lab["lab_nodes"]["client"]["lan_mac"])
        self.run("wan", wan)
        inspect = json.loads(self.docker("inspect", f"{self.prefix}-router").stdout)[0]
        self.router_wan_ip = inspect["NetworkSettings"]["Networks"][wan]["IPAddress"]
        inspect = json.loads(self.docker("inspect", f"{self.prefix}-wan").stdout)[0]
        self.wan_ip = inspect["NetworkSettings"]["Networks"][wan]["IPAddress"]
        for subnet in (self.lab["lab_dmz_cidr"], self.lab["lab_lan_cidr"]):
            self.execute("wan", "ip", "route", "add", subnet, "via", self.router_wan_ip)
        self.rename("router", self.router_wan_ip, "wan0")
        self.rename("router", self.lab["lab_router_dmz"], "dmz0")
        self.rename("router", self.lab["lab_router_lan"], "lan0")
        self.rename("server", self.lab["lab_server_ip"], "dmz0")
        self.rename("client", self.lab["lab_client_ip"], "lan0")
        self.execute("server", "ip", "route", "replace", "default", "via", self.lab["lab_router_dmz"], "dev", "dmz0")
        self.execute("client", "ip", "route", "replace", "default", "via", self.lab["lab_router_lan"], "dev", "lan0")
        for node in ("router", "server", "client"):
            self.copy(node, str(ROOT / f"artifacts/rendered/{node}") + "/.", "/")
            for file in ("backup.sh", "restore.sh", "validate_backup.py", "healthcheck.py"):
                self.copy(node, ROOT / "scripts" / file, "/usr/local/sbin/" + file)
            self.copy(node, ROOT / "scripts/alert.py", "/usr/local/sbin/alert.py")
            self.copy(node, ROOT / "scripts/backup.sh", "/usr/local/sbin/lab-backup")
            self.copy(node, ROOT / "scripts/restore.sh", "/usr/local/sbin/lab-restore")
            self.execute(node, "chmod", "+x", "/usr/local/sbin/lab-backup", "/usr/local/sbin/lab-restore")
            self.execute(node, "chown", "root:adm", "/etc/network-lab", "/var/log/network-lab", "/var/lib/network-lab")
            self.execute(node, "chmod", "750", "/etc/network-lab", "/var/log/network-lab", "/var/lib/network-lab")
            self.execute(node, "chmod", "700", "/var/backups/network-lab")
        self.copy("server", ROOT / "ansible/roles/server/files/index.html", "/var/www/network-lab/index.html")
        self.copy("server", ROOT / "ansible/roles/server/files/seed.sql", "/etc/network-lab/seed.sql")
        self.copy("wan", ROOT / "containers/wan_service.py", "/tmp/wan_service.py")
        self.docker("exec", "-d", f"{self.prefix}-wan", "python3", "/tmp/wan_service.py")

    def syntax(self):
        self.execute("server", "named-checkconf", "-z")
        self.execute("router", "dnsmasq", "--test", "--conf-file=/etc/dnsmasq.d/network-lab.conf")
        self.execute("router", "bash", "-c", "iptables-restore --test < /etc/network-lab/iptables.rules")
        for node in ("router", "server", "client"):
            self.execute(node, "chmod", "600", "/etc/netplan/90-network-lab.yaml")
            self.execute(node, "netplan", "generate")
            self.execute(node, "systemd-analyze", "verify", "/etc/systemd/system/lab-health.service", "/etc/systemd/system/lab-health.timer", "/etc/systemd/system/lab-alert@.service")
        self.execute("server", "systemd-analyze", "verify", "/etc/systemd/system/lab-backup.service", "/etc/systemd/system/lab-backup.timer")
        self.copy("server", ROOT / "ansible/roles/operations/files/logrotate.conf", "/etc/logrotate.d/network-lab")
        self.execute("server", "logrotate", "--debug", "/etc/logrotate.d/network-lab")
        return "BIND, dnsmasq, iptables, Netplan, systemd units and logrotate validated by Ubuntu binaries"

    def services(self):
        self.execute("server", "openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048", "-days", "1", "-keyout", "/etc/nginx/network-lab-tls/server.key", "-out", "/etc/nginx/network-lab-tls/server.crt", "-subj", f"/CN=www.{self.lab['lab_domain']}", "-addext", f"subjectAltName=DNS:www.{self.lab['lab_domain']},IP:{self.lab['lab_server_ip']}")
        self.execute("server", "ln", "-sf", "/etc/nginx/sites-available/network-lab", "/etc/nginx/sites-enabled/network-lab")
        self.execute("server", "rm", "-f", "/etc/nginx/sites-enabled/default")
        self.execute("server", "nginx", "-t")
        self.execute("server", "nginx")
        self.execute("server", "named", "-u", "bind")
        self.execute("router", "dnsmasq", "--conf-file=/etc/dnsmasq.d/network-lab.conf", "--log-facility=/var/log/network-lab/dhcp.log")
        self.execute("server", "pg_ctlcluster", "--skip-systemctl-redirect", "16", "main", "start")
        self.execute("server", "runuser", "-u", "postgres", "--", "createdb", "-T", "template0", self.lab["lab_database"])
        self.execute("server", "runuser", "-u", "postgres", "--", "psql", "-X", "-v", "ON_ERROR_STOP=1", "-d", self.lab["lab_database"], stdin=(ROOT / "ansible/roles/server/files/seed.sql").read_text())
        self.execute("router", "bash", "-c", "iptables-restore < /etc/network-lab/iptables.rules")
        for node in ("server", "client"):
            self.execute(node, "sed", "-i", "s/^IPV6=.*/IPV6=no/", "/etc/default/ufw")
            self.execute(node, "bash", "/etc/network-lab/apply-ufw.sh")
        return "Real BIND, DHCP, Nginx TLS, PostgreSQL and guest firewall policies started"

    def dhcp(self):
        self.execute("client", "ip", "addr", "flush", "dev", "lan0")
        self.execute("client", "bash", "-c", "printf 'timeout 15;\nretry 3;\n' > /tmp/dhclient.conf")
        result = self.execute("client", "dhclient", "-1", "-v", "-cf", "/tmp/dhclient.conf", "lan0", timeout=25)
        address = self.execute("client", "ip", "-4", "-o", "addr", "show", "lan0").stdout
        route = self.execute("client", "ip", "route", "show", "default").stdout
        leases = self.execute("router", "cat", "/var/lib/misc/dnsmasq.leases").stdout
        assert self.lab["lab_client_ip"] + "/24" in address, address
        assert self.lab["lab_router_lan"] in route, route
        assert self.lab["lab_nodes"]["client"]["lan_mac"] in leases, leases
        resolver = self.execute("client", "cat", "/etc/resolv.conf").stdout
        assert self.lab["lab_server_ip"] in resolver, resolver
        return (result.stdout + result.stderr)[-1200:]

    def dns(self, name, expected, *options):
        result = self.execute("client", "dig", "+short", "+time=2", "+tries=1", "@" + self.lab["lab_server_ip"], *options, name).stdout.strip()
        assert result == expected, result
        return result

    def negative_dns(self):
        missing = self.execute("client", "dig", "+time=2", "+tries=1", "@" + self.lab["lab_server_ip"], "absent." + self.lab["lab_domain"]).stdout
        assert "status: NXDOMAIN" in missing, missing
        axfr = self.execute("client", "dig", "+time=2", "+tries=1", "@" + self.lab["lab_server_ip"], self.lab["lab_domain"], "AXFR", check=False)
        assert "Transfer failed" in axfr.stdout or axfr.returncode != 0, axfr.stdout
        return "NXDOMAIN returned; AXFR denied"

    def web(self, tls=False):
        name = "www." + self.lab["lab_domain"]
        arguments = ["curl", "--fail", "--silent", "--show-error", "--max-time", "5"]
        if tls:
            self.execute("server", "cp", "/etc/nginx/network-lab-tls/server.crt", "/tmp/server.crt")
            temporary = ROOT / "artifacts/container-logs/server.crt"
            self.docker("cp", f"{self.prefix}-server:/tmp/server.crt", temporary)
            self.copy("client", temporary, "/tmp/server.crt")
            arguments += ["--cacert", "/tmp/server.crt"]
        result = self.execute("client", *arguments, f"{'https' if tls else 'http'}://{name}/healthz").stdout
        assert json.loads(result)["status"] == "ok", result
        return result.strip()

    def denied(self, source, destination, port):
        result = self.execute(source, "nc", "-z", "-w", "2", destination, str(port), check=False)
        assert result.returncode != 0, f"Unexpectedly reachable {destination}:{port}"
        return f"Connection denied: {destination}:{port}"

    def router_isolation(self):
        # Open real listeners and temporarily disable endpoint UFW to prove
        # the router itself enforces the separation, not a closed port.
        self.execute("server", "/usr/sbin/sshd")
        self.docker("exec", "-d", f"{self.prefix}-server", "python3", "-m", "http.server", "5432", "--bind", self.lab["lab_server_ip"])
        self.execute("server", "ufw", "disable")
        time.sleep(0.3)
        listening = self.execute("server", "ss", "-lnt").stdout
        assert ":22 " in listening and ":5432 " in listening, listening
        try:
            self.denied("client", self.lab["lab_server_ip"], 22)
            self.denied("client", self.lab["lab_server_ip"], 5432)
        finally:
            self.execute("server", "ufw", "--force", "enable")
        counters = self.execute("router", "iptables", "-nvL", "FORWARD").stdout
        return "SSH and database probe had active listeners and were blocked by router; " + counters[:500]

    def dnat(self):
        result = self.execute("wan", "curl", "--fail", "--silent", "--max-time", "5", f"http://{self.router_wan_ip}:8080/healthz").stdout
        assert json.loads(result)["status"] == "ok", result
        return result.strip()

    def nat(self):
        result = self.execute("client", "curl", "--fail", "--silent", "--max-time", "5", f"http://{self.wan_ip}/").stdout
        observed = json.loads(result)["client_ip"]
        assert observed == self.router_wan_ip, f"Expected NAT source {self.router_wan_ip}, observed {observed}"
        return f"WAN observed masqueraded source {observed}"

    def dmz_to_lan_denied(self):
        self.docker("exec", "-d", f"{self.prefix}-client", "python3", "-m", "http.server", "8081", "--bind", self.lab["lab_client_ip"])
        self.execute("client", "ufw", "disable")
        time.sleep(0.3)
        listening = self.execute("client", "ss", "-lnt").stdout
        assert ":8081 " in listening, listening
        try:
            return self.denied("server", self.lab["lab_client_ip"], 8081)
        finally:
            self.execute("client", "ufw", "--force", "enable")

    def external_dns_denied(self):
        self.execute("wan", "dnsmasq", "--conf-file=/dev/null", "--no-resolv", "--no-hosts", "--address=/egress.test/192.0.2.1")
        local = self.execute("wan", "dig", "+short", "@127.0.0.1", "egress.test").stdout.strip()
        assert local == "192.0.2.1", local
        result = self.execute("client", "dig", "+time=2", "+tries=1", "@" + self.wan_ip, "egress.test", check=False)
        assert result.returncode != 0, result.stdout
        return "WAN DNS has a valid answer; direct client DNS query blocked by router"

    def backup(self):
        result = self.execute("server", "bash", "/usr/local/sbin/backup.sh").stdout.strip()
        self.backup_path = result.splitlines()[-1]
        self.execute("server", "python3", "/usr/local/sbin/validate_backup.py", self.backup_path)
        self.execute("server", "bash", "/usr/local/sbin/restore.sh", self.backup_path, "lab_restore_integration")
        original = self.execute("server", "runuser", "-u", "postgres", "--", "psql", "-X", "-tAc", "SELECT id,event_name FROM lab_events ORDER BY id", "-d", self.lab["lab_database"]).stdout
        restored = self.execute("server", "runuser", "-u", "postgres", "--", "psql", "-X", "-tAc", "SELECT id,event_name FROM lab_events ORDER BY id", "-d", "lab_restore_integration").stdout
        assert original == restored and "Backup demo" in restored, restored
        return "Dump and restored rows are identical; checksum verified"

    def corrupt_backup(self):
        self.execute("server", "cp", "-a", self.backup_path, "/tmp/corrupt-backup")
        self.execute("server", "bash", "-c", "printf tamper >> /tmp/corrupt-backup/database.dump")
        result = self.execute("server", "bash", "/usr/local/sbin/restore.sh", "/tmp/corrupt-backup", "lab_restore_corrupt", check=False)
        assert result.returncode != 0, result.stdout
        count = self.execute("server", "runuser", "-u", "postgres", "--", "psql", "-X", "-tAc", "SELECT count(*) FROM pg_database WHERE datname='lab_restore_corrupt'").stdout.strip()
        assert count == "0", count
        return "Corrupt package rejected before database creation"

    def restore_overwrite(self):
        result = self.execute("server", "bash", "/usr/local/sbin/restore.sh", self.backup_path, "lab_restore_integration", check=False)
        assert result.returncode != 0 and "refusing overwrite" in result.stderr, result.stderr
        return "Existing restore database preserved"

    def fail2ban(self):
        self.execute("server", "touch", "/var/log/auth.log")
        self.execute("server", "bash", "-c", "printf '[sshd]\nenabled=true\nbackend=polling\nlogpath=/var/log/auth.log\nbanaction=iptables-multiport\n' > /etc/fail2ban/jail.local")
        self.execute("server", "fail2ban-client", "-x", "start")
        self.execute("server", "fail2ban-client", "set", "sshd", "banip", "10.20.20.200")
        rules = self.execute("server", "iptables-save").stdout
        assert "10.20.20.200" in rules and "f2b-sshd" in rules, rules[-1000:]
        self.execute("server", "fail2ban-client", "set", "sshd", "unbanip", "10.20.20.200")
        fixture = ROOT / "tests/fixtures/sshd.log"
        self.copy("server", fixture, "/tmp/sshd.log")
        result = self.execute("server", "fail2ban-regex", "/tmp/sshd.log", "/etc/fail2ban/filter.d/sshd.conf").stdout
        assert "2) [sshd]" in result or "2 matched" in result, result
        return "SSHD failures recognized; ban and unban changed real iptables rules"

    def health(self):
        self.execute("server", "bash", "-c", "printf '{\"services\":[],\"backup_directory\":\"/var/backups/network-lab\",\"thresholds\":{\"load_per_cpu\":1000}}' > /tmp/health.json")
        result = self.execute("server", "python3", "/usr/local/sbin/healthcheck.py", "--config", "/tmp/health.json").stdout
        report = json.loads(result)
        assert report["healthy"] and report["backup_age_hours"] is not None, report
        self.execute("server", "bash", "-c", "printf '{\"services\":[],\"thresholds\":{\"disk_percent\":0}}' > /tmp/health-failure.json")
        result = self.execute("server", "python3", "/usr/local/sbin/healthcheck.py", "--config", "/tmp/health-failure.json", check=False)
        assert result.returncode == 1 and "disk_percent" in result.stdout, result.stdout
        return "Valid backup counted; forced disk threshold returned exit 1 and JSON alert data"

    def collect(self):
        output = ROOT / "artifacts/container-logs"
        for node in ("router", "server", "client"):
            if f"{self.prefix}-{node}" not in self.containers:
                continue
            for label, command in (("routes", ["ip", "route"]), ("firewall", ["iptables-save"]), ("listeners", ["ss", "-lntup"])):
                result = self.execute(node, *command, check=False)
                (output / f"{node}-{label}.txt").write_text(result.stdout + result.stderr)

    def cleanup(self):
        for name in reversed(self.containers):
            self.docker("rm", "-f", name, check=False)
        for name in reversed(self.networks):
            self.docker("network", "rm", name, check=False)

    def verify(self):
        self.check("isolated_topology", self.start)
        self.check("native_configuration_validation", self.syntax)
        self.check("real_services_and_firewalls", self.services)
        self.check("dhcp_dora_address_gateway_dns", self.dhcp)
        self.check("dns_udp", lambda: self.dns("www." + self.lab["lab_domain"], self.lab["lab_server_ip"]))
        self.check("dns_tcp", lambda: self.dns("www." + self.lab["lab_domain"], self.lab["lab_server_ip"], "+tcp"))
        self.check("dns_reverse", lambda: self.dns(self.lab["lab_client_ip"], "client." + self.lab["lab_domain"] + ".", "-x"))
        self.check("dns_nxdomain_and_axfr_denial", self.negative_dns)
        self.check("http_routed_from_lan", self.web)
        self.check("https_certificate_verified", lambda: self.web(True))
        self.check("router_blocks_live_ssh_and_db_listeners", self.router_isolation)
        self.check("wan_cannot_access_postgresql", lambda: self.denied("wan", self.lab["lab_server_ip"], 5432))
        self.check("dnat_wan_8080_to_dmz_80", self.dnat)
        self.check("nat_lan_source_masquerade", self.nat)
        self.check("dmz_new_connection_to_live_lan_listener_denied", self.dmz_to_lan_denied)
        self.check("direct_external_dns_egress_denied", self.external_dns_denied)
        self.check("postgres_backup_restore_data_integrity", self.backup)
        self.check("corrupt_backup_rejected_without_db_creation", self.corrupt_backup)
        self.check("existing_restore_database_preserved", self.restore_overwrite)
        self.check("fail2ban_detection_ban_and_unban", self.fail2ban)
        self.check("health_json_metrics_and_failure_exit", self.health)


def main():
    output = ROOT / "artifacts/container-logs"
    output.mkdir(parents=True, exist_ok=True)
    lab = Lab()
    error = None
    try:
        lab.verify()
    except Exception as caught:
        error = str(caught)
    finally:
        try:
            lab.collect()
        finally:
            lab.cleanup()
        report = {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "environment": "Ubuntu 24.04 containers; isolated network namespaces; NET_ADMIN only",
            "vm_lifecycle_verified": False,
            "passed": error is None,
            "checks": lab.checks,
            "error": error,
        }
        (ROOT / "artifacts/integration-results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Integration result: {len([c for c in lab.checks if c['passed']])}/{len(lab.checks)} checks passed", flush=True)
    return 0 if error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
