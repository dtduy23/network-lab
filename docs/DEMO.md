# Kịch bản demo và bảo vệ

## Chuẩn bị trước buổi trình bày

Chạy `./labctl up`, `./labctl verify`; chuẩn bị ba terminal SSH router/server/client và trình duyệt `http://127.0.0.1:8080`. Tải box/package trước, tránh phụ thuộc download trong buổi bảo vệ. Mang PDF, source zip và JSON test evidence. Chỉ mô tả kết quả đã có; nếu demo bằng container, nói rõ systemd/reboot thuộc phần VM chưa kiểm chứng.

## Demo 12–15 phút

| Phút | Nội dung | Lệnh/bằng chứng |
|---|---|---|
| 0–2 | Mục tiêu, topology, LAN/DMZ/WAN và management | `docs/topology.svg`, IP plan |
| 2–4 | DHCP và DNS | client `ip addr`, `ip route`, `resolvectl status`; router leases; dig A/PTR/TCP |
| 4–6 | Web và NAT/DNAT | client HTTP/TLS; controller localhost:8080; router NAT counters |
| 6–8 | Phân đoạn bằng firewall | `nc -z -w 2 10.20.10.10 22/5432`; explain FORWARD policy; integration listener evidence |
| 8–10 | Quản trị và monitoring | `sshd -T`, Fail2ban status, health JSON và timers |
| 10–12 | Backup/restore | chạy backup, validate checksum, restore DB mới, so sánh rows |
| 12–15 | Sự cố và giới hạn | dừng DNS, health alert local, bắt gói, khôi phục; nêu backup local/VM evidence |

Lệnh client:

```bash
ip -4 addr show lan0
ip route show default
resolvectl status lan0
dig @10.20.10.10 www.infra.test +short
dig +tcp @10.20.10.10 www.infra.test +short
dig @10.20.10.10 -x 10.20.20.100 +short
curl http://www.infra.test/healthz
nc -z -w 2 10.20.10.10 22
nc -z -w 2 10.20.10.10 5432
```

Để chứng minh TLS dùng `./labctl verify` hoặc certificate đã lấy qua SSH trong `/etc/network-lab/server.crt`:

```bash
curl --cacert /etc/network-lab/server.crt https://www.infra.test/healthz
```

## Bài tập sự cố có thể khôi phục

**Dừng DNS trên server**:

```bash
sudo systemctl stop named
sudo systemctl start lab-health.service
sudo tail -n 1 /var/log/network-lab/health.jsonl | jq
sudo tail -n 1 /var/log/network-lab/alerts.jsonl | jq
sudo systemctl start named
sudo systemctl reset-failed lab-health.service
sudo systemctl start lab-health.service
```

Client direct dig bị timeout; HTTP bằng IP có thể vẫn hoạt động, giúp tách lỗi application khỏi name resolution. Health phát hiện service inactive; OnFailure ghi alert. Sau start named, direct dig và health phải hồi phục.

**Backup hỏng**: sao chép một package sang directory tạm trong guest, append một byte vào dump và gọi restore `lab_restore_bad`. Kết quả phải nonzero và database đó chưa được tạo. Không sửa backup gốc.

## Câu hỏi bảo vệ

1. **Vì sao có hai subnet?** Tách broadcast domain DHCP và áp dụng policy giữa client với server bằng router; không có VLAN trunk vật lý trong mô hình này.
2. **INPUT khác FORWARD?** INPUT dành cho packet đến chính router; FORWARD dành cho packet đi xuyên router. Port web trên server được kiểm soát tại FORWARD.
3. **NAT và DNAT khác nhau?** MASQUERADE thay source khi ra WAN; DNAT thay destination WAN8080 thành server80. Web demo dùng thêm SNAT về IP DMZ router để tránh reply qua management. Không NAT LAN→DMZ để giữ nguồn client thật.
4. **Vì sao có management NIC?** Vagrant/Ansible cần SSH độc lập để xử lý lỗi lab. Endpoints không dùng management làm default gateway; UFW hạn chế outbound mới qua đó.
5. **DHCP cung cấp gì?** IP/subnet mask, option3 gateway, option6 DNS, option15 domain, lease time; reservation theo MAC không phải DNS động.
6. **DNS dùng TCP khi nào?** Zone transfer và fallback/câu trả lời lớn; policy cho cả UDP/TCP53. Zone transfer lab bị cấm.
7. **Firewall test nonzero đã đủ chưa?** Chưa; phải có listener và kiểm tra route để loại trừ dịch vụ tắt. Integration đã dùng listener thật.
8. **Backup chạy thành công có đủ chưa?** Chưa; phải xác minh checksum, thực sự restore, so sánh dữ liệu và thử failure/concurrency. Backup local vẫn không chống mất toàn bộ server.
9. **Tắt password rồi Fail2ban để làm gì?** Hạn chế lặp lỗi auth/key trên SSH management; filter phải kiểm tra log thực. Ban demo không chứng minh mọi brute-force pattern.
10. **Có HA hay production readiness không?** Đây là lab một router/server, chưa có HA, offsite backup, tải production hay TLS CA công khai.
11. **Health metrics có Grafana không?** Chưa có Prometheus/Grafana stack trong phạm vi dự án này; có textfile format để tích hợp sau.
12. **Container pass có chứng minh VM chạy tốt không?** Chứng minh dịch vụ và policy template trong namespace; cloud-init, Netplan apply, timer runtime và reboot cần kiểm thử VM riêng.
