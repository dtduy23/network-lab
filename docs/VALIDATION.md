# Kiểm chứng và ma trận yêu cầu

## Mức độ bằng chứng

1. **Regression/controller**: logic ngưỡng, dữ liệu không hợp lệ, backup thất bại/retention, lock chạy song song, checksum, inventory; Ansible syntax, Ruby syntax, ShellCheck.
2. **Integration container**: cấu hình được kiểm tra bằng binary Ubuntu thật; DNS/DHCP/HTTP/TLS/iptables/UFW/NAT/backup/restore chạy trên các network namespaces riêng. Cùng template với VM.
3. **VM runtime**: `./labctl verify` và checklist reboot; bắt buộc có hypervisor hoạt động. Chưa chạy bước này thì không đánh dấu VM deploy đã thành công.

Kết quả controller ghi tại `artifacts/unit-tests.xml`; integration tại `artifacts/integration-results.json`; preflight tại `artifacts/preflight.json`. Report PDF được sinh từ các artifact này, không nhập số pass thủ công.

## Ma trận yêu cầu từ phần dự án trong CV

| Yêu cầu | Mã nguồn/cấu hình | Bằng chứng |
|---|---|---|
| Ubuntu, systemd, users, POSIX permissions, SSH key | `common`, `operations`, `network` roles | Ansible syntax + unit verification native; runtime SSH/timer qua VM verify |
| DNS local thuận/ngược | `server/templates/named*`, `db.*` | dig UDP/TCP, A/PTR, NXDOMAIN, AXFR denied |
| DHCP và subnet ảo | `Vagrantfile`, `lab.yml`, `router/templates/dnsmasq*` | DORA thật; IP reservation, gateway và resolver nhận từ DHCP |
| NAT và port forwarding | router `iptables.rules` | WAN thấy source masquerade; WAN:8080 tới DMZ:80 |
| Ingress/egress filtering, iptables/UFW | router + endpoint roles | Cổng SSH/DB đang listen vẫn bị router chặn; local UFW nạp policy thật |
| Fail2ban | common jail + integration | Fixture auth failures, ban/unban thay đổi iptables; VM journal flow còn cần xác minh |
| Process/memory/disk monitoring | `healthcheck.py` | Threshold boundary, nonfinite, log concurrency, valid backup freshness, failure exit |
| Backup và failure alerts | `backup.sh`, `restore.sh`, systemd OnFailure | PostgreSQL dump/restore rows, checksum hỏng không tạo DB; failure cleanup/lock/retention tests; alert local systemd qua VM checklist |
| Logrotate | operations logrotate | Native `logrotate --debug`; rotate thật trong VM checklist |
| SOP/topology/troubleshooting | docs, topology SVG | Runbook, demo, checklist phân lớp, báo cáo và slide outline |

## Checklist nghiệm thu trên máy có VM

- [ ] `./labctl up` hoàn thành cả ba VM không failed task.
- [ ] `./labctl verify` thành công và lưu output/timestamp.
- [ ] Đăng nhập SSH operator bằng key lab, root/password login bị từ chối.
- [ ] `systemctl is-active` đúng cho named/nginx/pg cluster/dnsmasq/Fail2ban.
- [ ] Management NIC endpoints không có default route, UFW outgoing management chỉ DHCP/reply.
- [ ] Reboot cả ba VM; `./labctl verify` tiếp tục thành công.
- [ ] Chạy `./labctl provision` lần hai, không reset data/permissions/keys.
- [ ] Dừng named: health trả exit 1; alert local xuất hiện; start named và health trở lại khỏe.
- [ ] Dừng PostgreSQL: backup service failed, alert được ghi; backup cũ còn nguyên; restart PostgreSQL và backup lại thành công.
- [ ] Dùng `logrotate --force /etc/logrotate.d/network-lab`; JSON mới vẫn ghi được, archive quyền đúng.
- [ ] Xác minh Fail2ban với log SSH thực trong journal và đường SSH management.
- [ ] `halt` giữ dữ liệu; `destroy` chỉ xóa VM lab và dữ liệu trong guest.

Checklist chưa tự động đánh dấu. Container không chạy systemd làm PID 1, nên chỉ kiểm tra cú pháp/unit dependencies bằng `systemd-analyze verify`; health container tắt service probes vì systemctl runtime không tồn tại. VM verify chạy service probes thật.

Health trong verify được thử lại tối đa khoảng2 phút để tải khởi động của VM/QEMU giảm xuống ngưỡng đã cấu hình. Không tăng ngưỡng hoặc bỏ qua failure; nếu service/metrics vẫn không đạt, nghiệm thu thất bại.

`./labctl drills` tự kiểm tra dừng DNS → health failure → OnFailure alert, backup lỗi không mất package cũ, backup unit failure alert, recovery và logrotate. Có `always` để khởi động lại dịch vụ/khôi phục environment sau test; evidence lưu tại `artifacts/vm-drills.txt`, `vm-alerts.jsonl`, `vm-health.jsonl`. Chỉ chạy trong server lab đã provision.

## Kiểm thử đối kháng có ý nghĩa

Backup lỗi không được xoay vòng xóa bản cũ hoặc để package nửa chừng; hai backup đồng thời chỉ một tiến trình vào dump; sửa byte trong dump với cùng kích thước vẫn bị checksum phát hiện; symlinked dump bị từ chối; restore target nguồn/tên SQL injection/existing DB bị từ chối. Unit fixture chỉ mô phỏng failure paths; dump và restore thành công được xác nhận thêm với PostgreSQL thật.

Firewall denial cần listener đang hoạt động để phân biệt packet DROP với không có dịch vụ. Runner mở listener SSH và TCP5432, tạm tắt UFW server, kiểm tra LAN vẫn không tới được và khôi phục UFW sau kiểm tra. NAT kiểm tra IP nguồn mà service WAN thực sự nhìn thấy.

## Giới hạn

Không có số liệu production capacity, HA, tốc độ backup với dữ liệu lớn hay load test nhiều nghìn người dùng. Self-signed TLS chỉ phục vụ lab; backup local chưa chống mất server. DNS forwarding phụ thuộc Internet và hai upstream; kiểm thử zone local không chứng minh toàn bộ upstream. Cấu hình được viết cho Ubuntu 24.04/PostgreSQL16; host có thể là distro khác vì không provision host.
