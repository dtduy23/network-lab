# Nội dung 12 slide bảo vệ

1. **Tên đồ án / tác giả** — Linux Network Infrastructure & Systems Automation Lab; Đinh Tuấn Duy, HCMUS. Mục tiêu: tái lập, phân đoạn, vận hành và phục hồi.
2. **Bài toán** — cần IP/DNS đúng, cổng đúng, SSH an toàn, dữ liệu restore được và quy trình xử lý lỗi.
3. **Topology** — đưa `topology.svg`; giải thích WAN, DMZ, LAN, management và mỗi node.
4. **IP/DHCP plan** — hai /24, reservation theo MAC, DORA, option gateway/DNS, lease12h.
5. **DNS/web** — BIND A/PTR/ACL; Nginx HTTP/TLS; demo dig và healthz.
6. **Firewall/NAT** — INPUT/FORWARD, defaultDROP, allowed ports, masquerade/DNAT; counters và listener evidence.
7. **Linux administration** — systemd, users/groups/permissions, key SSH, root/password disabled, Fail2ban.
8. **Automation** — Vagrant/Ansible/Netplan, QEMU fallback, labctl; thứ tự provision và fixed MAC.
9. **Monitoring/logging** — MemAvailable/disk/inode/load/service/backup freshness; NDJSON/metrics; local OnFailure alert/logrotate.
10. **Backup/restore** — staging, checksum/manifest, lock/retention, restore DB mới, failure test và row comparison.
11. **Kiểm thử và incident demo** — số pass lấy từ JSON/XML thật; phân biệt container và VM; dừng DNS, health fail, khôi phục.
12. **Giới hạn / hướng phát triển** — single server/router, local backup, self-signed TLS, chưa productioncapacity; offsite/HA/monitoring collector.

Không dùng số liệu tải, availability hoặc throughput khi chưa có benchmark. Ảnh chụp demo cần đúng lần chạy đang trình bày và có timestamp. Bộ source, report PDF, topology và JSON evidence là phần bàn giao chính.
