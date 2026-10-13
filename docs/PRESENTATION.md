---
title: "Linux Network Infrastructure"
subtitle: "Systems Automation Lab"
author: "Đinh Tuấn Duy — HCMUS"
theme: Madrid
aspectratio: 169
lang: vi
---

## Bài toán và mục tiêu

- Cấp IP và phân giải tên nội bộ nhất quán.
- Tách LAN/DMZ, kiểm soát cổng dịch vụ và truy cập quản trị.
- Theo dõi sức khỏe, phát hiện lỗi và phục hồi dữ liệu.
- Tái lập bằng mã; mọi kết luận dựa trên bằng chứng kiểm thử.

## Kiến trúc ba máy

![WAN, router, DMZ, LAN và management](topology.png){height=65%}

## IP plan và DHCP

| Segment | Gateway | Địa chỉ |
|---|---|---|
| DMZ /24 | 10.20.10.1 | Server 10.20.10.10 |
| LAN /24 | 10.20.20.1 | Client DHCP 10.20.20.100 |

- Pool .100–.150; reservation theo MAC; lease 12 giờ.
- DORA thật; DHCP cấp gateway, DNS 10.20.10.10 và domain.
- DHCP chỉ trên LAN, không can thiệp DHCP management.

## DNS và web

- BIND9: zone `infra.test`, A/PTR, UDP/TCP 53.
- Query/recursion chỉ local/LAN/DMZ; AXFR và dynamic update bị cấm.
- dnsmasq chỉ DHCP, `port=0`; Nginx bind DMZ 80/443.
- TLS self-signed có SAN; kiểm thử dùng `--cacert`.
- `/healthz` trả JSON để demo đường đi end to end.

## Firewall và NAT

- Router INPUT/FORWARD mặc định DROP; stateful reply được phép.
- LAN → DMZ: DNS, HTTP, HTTPS, ICMP; SSH/database bị chặn.
- DMZ→LAN: chặn kết nối mới; DNS ngoài chỉ qua resolver.
- MASQUERADE khi ra WAN; DNAT + SNAT cho web demo WAN8080→server80.
- Server/client dùng UFW; IPv4 lab; router OUTPUT vẫn ACCEPT.

## Linux administration và SSH

- Guest Ubuntu24.04; systemd quản lý service/timer và boot order.
- Account operator, groups, owner/mode cho keys/logs/backup.
- SSH key, tắt root/password/keyboard-interactive; MaxAuthTries3.
- Vagrant giữ quyền bootstrap; operator chỉ đọc trạng thái theo sudoers.
- Fail2ban đọc journal, ban10 phút khi đạt5 lần lỗi/10 phút.

## Hạ tầng bằng mã

- `lab.yml`: IP/MAC/tài nguyên; cùng nguồn biến cho các kiểm thử.
- Vagrant VirtualBox/libvirt; Ansible roles theo thứ tự router→server→client.
- Netplan match MAC, endpoints dùng gateway router, management chỉ SSH/DHCP.
- QEMU TCG fallback: VM thật, socketlocalhost, không sửa mạng host.
- CLI: bootstrap, up, provision, verify, reboot, halt, destroy.

## Monitoring và log

- MemAvailable, disk, inode, load/CPU và trạng thái service.
- Backup freshness dựa trên package có checksum hợp lệ.
- Health mỗi 5 phút; JSONL có lock; textfile metrics ghi atomic.
- Failure exit kích hoạt local alert qua OnFailure.
- Logrotate 7 bản; chưa có external notifications hoặc Grafana collector.

## Backup và phục hồi

- PostgreSQL16 local; custom dump, manifest UTC, SHA-256.
- Staging→atomic rename; flock; retention chỉ sau thành công.
- Restore chỉ sang database mới `lab_restore_*`; transaction + exit-on-error.
- Từ chối package hỏng, symlink, target nguồn/tên không hợp lệ/existing DB.
- So sánh dữ liệu restore; backup local chưa chống mất toàn bộ server.

## Kết quả kiểm thử

<!-- SLIDE_EVIDENCE -->

## Demo sự cố DNS

1. Dừng `named` trên server; client query timeout.
2. Kiểm tra IP/route; HTTP theo IP có thể vẫn khỏe.
3. Health phát hiện service inactive; OnFailure ghi alert local.
4. Dùng dig/tcpdump/journal xác minh nguyên nhân.
5. Start named; health/dig hồi phục, không mở rộng firewall.

## Giới hạn và hướng phát triển

- Một router/server; chưa HA, productioncapacity hoặc offsite backup.
- TLS lab; DNS upstream phụ thuộc Internet.
- Container evidence và VM lifecycle được báo cáo riêng.
- Mở rộng: backup offsite/encryption, DNS redundancy, monitoring collector, CA/VPN nội bộ.
- Mỗi phần mở rộng cần yêu cầu nghiệm thu và kiểm thử riêng.
