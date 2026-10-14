# Biên bản nghiệm thu

Thời điểm tổng hợp: 14/10/2026 21:36 +07. Môi trường VM: Ubuntu24.04, QEMU TCG; controller Linux.

| Hạng mục | Kết quả | Bằng chứng |
|---|---|---|
| Regression | 34/34 PASS | unit-tests.xml |
| Integration binary/gói tin thật | 21/21 PASS | integration-results.json |
| VM runtime router/server/client | PASS | vm-verification.txt |
| Reboot cả ba guest và verify lại | PASS | vm-reboot.txt, vm-results.json |
| DNS failure → health fail → local alert → recovery | PASS | vm-drills.txt, vm-alerts.jsonl |
| Backup failure không mất package cũ | PASS | vm-drills.txt |
| Backup unit OnFailure, recovery | PASS | vm-alerts.jsonl, vm-drills.txt |
| Logrotate và log permissions | PASS | vm-drills.txt, vm-health.jsonl |

Nghiệm thu VM bao gồm DHCP reservation/gateway, route qua router, DNS A/PTR UDP/TCP, NXDOMAIN/AXFR, HTTP/TLS có xác minh certificate, SSH operator và cấu hình SSH hiệu lực, router default DROP, blocked ports, backup/restore và DNAT+SNAT web demo trên host.

VirtualBox/libvirt có cấu hình bàn giao; chưa chạy nghiệm thu hai provider này trên controller hiện tại. Kết quả không bao gồm HA, productioncapacity, backup offsite hay public CA. Alert artifacts có thể chứa lịch sử thử lỗi trước sửa; các event của hai unit chuẩn đã được kiểm tra riêng.
