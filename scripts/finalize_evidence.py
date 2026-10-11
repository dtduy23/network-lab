#!/usr/bin/env python3
"""Create acceptance summary only after every required evidence gate passes."""
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

root = Path(__file__).resolve().parents[1]
artifacts = root / "artifacts"
integration = json.loads((artifacts / "integration-results.json").read_text())
vm = json.loads((artifacts / "vm-results.json").read_text())
suites = ET.parse(artifacts / "unit-tests.xml").getroot()
tests = sum(int(suite.get("tests", 0)) for suite in suites.iter("testsuite"))
errors = sum(int(suite.get("failures", 0)) + int(suite.get("errors", 0)) for suite in suites.iter("testsuite"))
if errors or not integration["passed"] or not all(vm.get(key) for key in ("passed", "reboot_verified", "drills_verified")):
    raise SystemExit("Acceptance pending: regression/integration/VM/reboot/failure drills must all pass.")
records = [json.loads(line) for line in (artifacts / "vm-alerts.jsonl").read_text().splitlines()]
required_units = {"lab-health.service", "lab-backup.service"}
if not required_units.issubset({record["unit"] for record in records}):
    raise SystemExit("Missing required OnFailure alert evidence")
health = [json.loads(line) for line in (artifacts / "vm-health.jsonl").read_text().splitlines()]
if not health or not health[-1]["healthy"]:
    raise SystemExit("Recovery health evidence is not healthy")
checks = len(integration["checks"])
date = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%d/%m/%Y %H:%M %Z")
text = f"""# Biên bản nghiệm thu

Thời điểm tổng hợp: {date}. Môi trường VM: Ubuntu24.04, QEMU TCG; controller Linux.

| Hạng mục | Kết quả | Bằng chứng |
|---|---|---|
| Regression | {tests}/{tests} PASS | unit-tests.xml |
| Integration binary/gói tin thật | {checks}/{checks} PASS | integration-results.json |
| VM runtime router/server/client | PASS | vm-verification.txt |
| Reboot cả ba guest và verify lại | PASS | vm-reboot.txt, vm-results.json |
| DNS failure → health fail → local alert → recovery | PASS | vm-drills.txt, vm-alerts.jsonl |
| Backup failure không mất package cũ | PASS | vm-drills.txt |
| Backup unit OnFailure, recovery | PASS | vm-alerts.jsonl, vm-drills.txt |
| Logrotate và log permissions | PASS | vm-drills.txt, vm-health.jsonl |

Nghiệm thu VM bao gồm DHCP reservation/gateway, route qua router, DNS A/PTR UDP/TCP, NXDOMAIN/AXFR, HTTP/TLS có xác minh certificate, SSH operator và cấu hình SSH hiệu lực, router default DROP, blocked ports, backup/restore và DNAT+SNAT web demo trên host.

VirtualBox/libvirt có cấu hình bàn giao; chưa chạy nghiệm thu hai provider này trên controller hiện tại. Kết quả không bao gồm HA, productioncapacity, backup offsite hay public CA. Alert artifacts có thể chứa lịch sử thử lỗi trước sửa; các event của hai unit chuẩn đã được kiểm tra riêng.
"""
(artifacts / "ACCEPTANCE.md").write_text(text)
print(artifacts / "ACCEPTANCE.md")
