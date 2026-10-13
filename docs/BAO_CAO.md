---
title: "Linux Network Infrastructure & Systems Automation Lab"
subtitle: "Đồ án quản trị hệ thống Linux và hạ tầng mạng"
author: "Đinh Tuấn Duy — HCMUS"
lang: vi
---

# Tóm tắt

Đồ án xây dựng một môi trường mạng nhỏ có khả năng tái lập, gồm router/firewall, máy chủ dịch vụ và máy khách. Hệ thống cung cấp DNS nội bộ, DHCP, web HTTP/HTTPS, quản lý truy cập SSH, kiểm tra sức khỏe và sao lưu PostgreSQL. Cấu hình được biểu diễn bằng mã để giảm sai lệch thao tác thủ công; kiểm thử bao gồm trường hợp hoạt động bình thường và các tình huống lỗi có thể gây mất dữ liệu hoặc vượt chính sách mạng.

Sản phẩm gồm mã nguồn cấu hình, CLI `labctl`, lab VM, integration bằng container, regression tests, sơ đồ topology, SOP, kịch bản demo và báo cáo có bằng chứng kiểm thử tự động. Mô hình phục vụ học tập và đánh giá năng lực vận hành, chưa đặt mục tiêu HA hoặc tải production.

# Đặt vấn đề và mục tiêu

## Bối cảnh

Trong một tổ chức nhỏ, hạ tầng mạng cần đồng thời đảm bảo địa chỉ IP được cấp đúng, tên dịch vụ phân giải được, người dùng truy cập đúng các cổng được cho phép và dữ liệu có thể phục hồi. Một cấu hình hoạt động ở thời điểm triển khai chưa đủ: phải tồn tại sau reboot, có khả năng phát hiện lỗi và có quy trình điều tra rõ ràng.

Đồ án chuyển các mô tả năng lực trong dự án “Linux Network Infrastructure & Systems Automation Lab” thành hệ thống có thể chạy và kiểm chứng: quản trị Ubuntu, DNS/DHCP, subnet ảo, iptables/UFW, Fail2ban, Bash/Python automation, logrotate, backup và runbook.

## Mục tiêu nghiệm thu

| Mã | Mục tiêu | Điều kiện nghiệm thu |
|---|---|---|
| R1 | Tái lập môi trường Linux | CLI tạo guest, Ansible provision, các file cấu hình và permissions nhất quán |
| R2 | DNS nội bộ | A/PTR chính xác qua UDP/TCP; NXDOMAIN đúng; AXFR bị từ chối |
| R3 | DHCP | Client nhận IP, gateway, DNS qua DHCP và đúng reservation theo MAC |
| R4 | Phân đoạn và NAT | LAN chỉ tới dịch vụ cho phép; NAT source và DNAT destination được xác minh |
| R5 | SSH và bảo vệ đăng nhập | Root/password SSH tắt; account operator dùng key; Fail2ban có jail |
| R6 | Tự động hóa sức khỏe | Log JSON, metrics; failure exit khi service/disk/backup không đạt |
| R7 | Sao lưu/khôi phục | Dump thật, checksum đúng, dữ liệu restore khớp; không ghi đè DB hoặc mất bản cũ khi lỗi |
| R8 | Khả năng vận hành | Sơ đồ, SOP, demo, bằng chứng test và checklist reboot |

## Phạm vi

Guest Ubuntu 24.04; IPv4; hai mạng /24 và một router; PostgreSQL16 local; TLS self-signed. Không triển khai Kubernetes/UniHub trong đồ án này. Không có VLAN trunk vật lý, HA router, replication database, external alert messaging, backup offsite hay public CA.

# Cơ sở lý thuyết

## TCP/IP, subnet và định tuyến

Máy trong cùng subnet trao đổi qua link layer và ARP. Hai subnet khác nhau cần router; địa chỉ default gateway phải nằm trong subnet của máy. Prefix /24 cung cấp 256 địa chỉ, trong đó network và broadcast không dùng làm địa chỉ host thông thường. DMZ và LAN trong đồ án là hai segment riêng; DHCP broadcast không tự đi qua router nếu không có relay.

Troubleshooting theo lớp giúp tránh thay đổi sai: kiểm tra link/interface, MAC và ARP, IP/subnet/route, port/firewall, TLS rồi giao thức ứng dụng. Các công cụ tương ứng gồm `ip`, `ss`, `tcpdump`, `dig`, `curl`, `traceroute` và journal. `netstat` là công cụ cũ tương đương một phần của `ss`; lab ưu tiên `ss` hiện hành.

## DNS và DHCP

DNS ánh xạ tên sang IP qua bản ghi A và IP sang tên qua PTR trong reverse zone. Authoritative DNS phục vụ dữ liệu của zone; recursive/forwarding resolver trả lời các tên bên ngoài. ACL giới hạn client recursion và zone transfer để giảm nguy cơ mở resolver ngoài phạm vi lab.

DHCP có quy trình Discover, Offer, Request, Ack; server gửi địa chỉ, subnet mask, default router, DNS và lease time. Reservation theo MAC cung cấp địa chỉ ổn định cho client demo. DNS record của client được khai báo tương ứng reservation; lab không có dynamic DNS update cho mọi lease.

## Firewall stateful và NAT

iptables phân biệt INPUT, OUTPUT và FORWARD. INPUT là gói đến chính guest, FORWARD là gói qua router. Conntrack cho phép reply bằng trạng thái ESTABLISHED/RELATED thay vì mở cổng trả lời rộng. Chính sách mặc định DROP cần được bổ sung các luồng thiết yếu như DHCP, DNS, web và ICMP phù hợp.

Source NAT/MASQUERADE thay địa chỉ nguồn khi đi ra WAN; Destination NAT thay đích khi nhận port forwarding. Trong LAN→DMZ, giữ nguyên source để log và ACL vẫn thấy địa chỉ client thật. UFW cung cấp giao diện quản lý firewall cho endpoints, còn router sử dụng iptables trực tiếp để minh họa routing/NAT.

Riêng web demo từ WAN8080, áp dụng thêm SNAT sang địa chỉ DMZ của router. Server và router có thể cùng management subnet 10.0.2.0/24 trong VirtualBox/QEMU; nếu giữ nguồn WAN, server có thể trả lời qua NIC management làm mất phiên DNAT. SNAT buộc reply đi qua router và chỉ áp dụng cho phiên đã DNAT.

## systemd, quyền Linux và SSH

systemd service quản lý quy trình, phụ thuộc khởi động và lỗi; timer lập lịch health/backup; OnFailure kích hoạt local alert. POSIX owner/group/mode hạn chế key, backup, cấu hình và log. SSH dùng public key, tắt root/password login, tạo account operator với quyền đọc trạng thái có giới hạn. Account bootstrap vẫn cần quyền sudo để cấu hình máy trong lab.

## Backup và khả năng phục hồi

Backup được đánh giá bằng khả năng restore, không chỉ bằng exit code của dump. Custom dump hỗ trợ pg_restore; manifest ghi nguồn, timestamp UTC, kích thước và SHA-256. Backup được tạo trong directory staging, kiểm tra trước khi rename thành package hoàn chỉnh. Lock ngăn hai job cạnh tranh; retention chỉ chạy sau thành công. Restore chỉ tạo database mới, không nhận database nguồn hoặc database đã tồn tại.

# Thiết kế hệ thống

## Topology

<!-- TOPOLOGY_IMAGE -->

| Máy | NIC dữ liệu | Dịch vụ |
|---|---|---|
| Router | dmz0 `10.20.10.1/24`, lan0 `10.20.20.1/24`, WAN DHCP | DHCP, iptables, forwarding, NAT/DNAT |
| Server | dmz0 `10.20.10.10/24` | BIND9, Nginx TLS, PostgreSQL, UFW, backup |
| Client | lan0 DHCP `10.20.20.100/24` | Công cụ kiểm thử và UFW |

Management NIC cho controller SSH vào guest ngay cả khi mạng lab lỗi. Endpoints không dùng management route/DNS làm đường Internet; UFW chặn outbound mới qua management ngoại trừ DHCP. Mạng nghiệp vụ vẫn qua router.

## Ma trận truy cập

| Luồng | Cho phép | Chính sách |
|---|---|---|
| Controller → guest management | TCP22 | SSH key |
| LAN → router | DHCP/ICMP | Cấp IP và chẩn đoán gateway |
| LAN → server | UDP/TCP53, TCP80/443, ICMP | DNS và web |
| LAN → server | TCP22/5432 bị chặn | Phân tách truy cập quản trị và database |
| DMZ → LAN | Kết nối mới bị chặn | Ngăn chuyển tiếp truy cập từ server vào client |
| Endpoints → WAN | TCP80/443, UDP123, ICMP | Cập nhật và dịch vụ cơ bản |
| Server DNS → upstream | UDP/TCP53 tới hai forwarders | DNS forwarding có giới hạn |
| WAN → router8080 | DNAT tới server80 | Demo qua localhost8080 trên controller |

OUTPUT của chính router là ACCEPT; giới hạn egress áp dụng ở FORWARD cho endpoints. Chính sách không được mô tả như allowlist cho toàn bộ traffic router. IPv6 không thuộc phạm vi và bị tắt để không có bypass ngoài policy IPv4.

## Dịch vụ

BIND9 listen loopback và IP DMZ, authoritative cho `infra.test` và hai reverse zones; chỉ lab subnets được query/recursion; zone transfer và dynamic update bị cấm. dnsmasq chỉ cấp DHCP (`port=0`) trên LAN. Nginx bind DMZ, có `/healthz` trả JSON, HTTP và TLS1.2/1.3. PostgreSQL chỉ listen localhost; seed giữ nguyên các dòng dữ liệu đã có.

Health script thu memory qua MemAvailable, disk, inode, load trên CPU, service state và tuổi backup hợp lệ. JSONL ghi có lock; metrics thay thế atomic. Timer chạy 5 phút; backup timer 02:00 ở múi giờ guest. Logrotate giữ 7 bản log đã xoay vòng. Backup dữ liệu giữ theo tuổi 7 ngày và không xoay khi dump thất bại.

# Triển khai bằng mã

## Cấu trúc

```text
lab.yml                 IP, MAC, tài nguyên và biến lab
Vagrantfile             VirtualBox / libvirt guest definitions
labctl                  Bootstrap / up / provision / verify / reboot
ansible/roles/          common, network, router, server, endpoint, operations
scripts/                health, backup, restore, render, integration, QEMU
containers/             Ubuntu test image và WAN probe
tests/                  Regression và fixture SSH
docs/                   Báo cáo, topology, SOP, demo, slide outline
artifacts/              Test evidence, PDF, zip source
```

Vagrant quản lý VM; Ansible chia theo common rồi router, server, client. Fixed MAC nhận diện management NIC ngay cả khi default route đã đổi. File Netplan cũ được lưu lại trong guest; cloud-init networking bị vô hiệu hóa để không ghi đè sau reboot. Cấu hình DNS/Nginx/iptables được kiểm tra trước khi restart.

QEMU TCG là backend VM độc lập để chạy khi host không có KVM/VirtualBox. Ubuntu cloud image được tải từ Canonical và đối chiếu SHA-256; NoCloud seed tạo account provision. Mạng LAN/DMZ nối bằng socket localhost, WAN dùng QEMU user networking. Backend này không tạo bridge, tuntap hoặc rule firewall trên host; tốc độ mô phỏng chậm hơn hypervisor có tăng tốc.

## Các bước sử dụng

```bash
./labctl bootstrap
./labctl doctor
./labctl up
./labctl verify
./labctl reboot
./labctl halt
```

Máy không có provider mặc định có thể chạy `LAB_PROVIDER=qemu ./labctl up`. Container integration chạy độc lập bằng `./labctl integration`. Private key và image/disk nằm trong `.lab`, không trong gói source.

# Phương pháp kiểm thử

## Ba mức kiểm chứng

Regression tests kiểm tra failure/concurrency/data validation. Integration chạy binary dịch vụ thật trong network namespaces và cùng template. VM verification kiểm tra SSH effective settings, active services/timers, route, DHCP lease, DNS/web/TLS, blocked ports, backup/restore và host forwarding. Reboot verification cần guest thực để khẳng định persistence.

## Các trường hợp quan trọng

- DHCP phải nhận cả IP, gateway và resolver, không chỉ thấy một static IP.
- Firewall test dùng listener đang chạy và tạm tắt UFW server để chứng minh router chặn.
- NAT kiểm tra source mà WAN probe thực sự nhận; DNAT kiểm tra JSON web health từ WAN8080.
- HTTPS dùng certificate được lấy qua kênh quản trị và `--cacert`, không bỏ qua xác minh.
- Backup và restore so sánh các dòng `lab_events`, không chỉ đếm file dump.
- Backup hỏng cùng kích thước phải bị checksum phát hiện; không tạo restore DB trước khi validation hoàn tất.
- Backup thất bại không xóa bản cũ; hai backup đồng thời không tạo hai package cạnh tranh.
- Restore target có SQL injection, tên nguồn hoặc target đã tồn tại bị từ chối.

## Bằng chứng tự động

<!-- TEST_EVIDENCE -->

# Vận hành và xử lý sự cố

Các SOP chi tiết trong `docs/RUNBOOK.md` gồm kiểm tra đầu ngày, DNS, DHCP, web/TLS, firewall/NAT, backup/restore, SSH/Fail2ban và reboot. Mỗi incident cần triệu chứng, thời điểm, ảnh hưởng, lệnh tái hiện, bằng chứng packet/log, nguyên nhân, bước khôi phục và kiểm tra sau sửa.

Ví dụ DNS bị dừng: client query timeout nhưng route và HTTP theo IP có thể vẫn đúng; health phát hiện named inactive; OnFailure ghi local alert; start named và chạy lại health/dig xác nhận hồi phục. Không mở toàn bộ firewall hoặc recursion để che lỗi chẩn đoán.

Kịch bản bảo vệ 12–15 phút trình bày topology, DHCP/DNS, web/NAT, firewall, SSH/health, backup/restore rồi incident demo. `docs/DEMO.md` cung cấp lệnh và các câu hỏi về INPUT/FORWARD, DORA, authoritative/recursive DNS, NAT, backup failure domain và giới hạn container evidence.

# Đánh giá và hướng phát triển

Sản phẩm cung cấp hạ tầng bằng mã, kiểm chứng luồng gói tin, automation có failure behavior và tài liệu vận hành. Giới hạn còn lại: một router/server, không HA; backup cùng server; certificate lab; chưa load test production; Fail2ban cần đối chiếu pattern auth thực; upstream DNS phụ thuộc Internet; box/package có thể thay đổi nếu không pin snapshot.

Hướng phát triển: backup offsite/encryption và restore định kỳ, DNS redundancy, monitoring collector/Prometheus/Grafana, TLS CA nội bộ, VPN management, egress policy theo nhu cầu ứng dụng, Ansible idempotence/lifecycle trong CI có hypervisor. Mỗi phần mở rộng cần tiêu chí nghiệm thu và bằng chứng riêng.

# Tài liệu tham khảo

1. [HashiCorp Vagrant — VirtualBox Networking](https://developer.hashicorp.com/vagrant/docs/providers/virtualbox/networking).
2. [vagrant-libvirt — Configuration](https://vagrant-libvirt.github.io/vagrant-libvirt/configuration.html).
3. [Canonical Netplan — YAML configuration](https://netplan.readthedocs.io/en/stable/netplan-yaml/).
4. [ISC BIND9 — Administrator Reference](https://bind9.readthedocs.io/en/v9.18.1/reference.html).
5. [dnsmasq — Manual](https://thekelleys.org.uk/dnsmasq/docs/dnsmasq-man.html).
6. [PostgreSQL16 — SQL dump and restore](https://www.postgresql.org/docs/16/backup-dump.html).
7. [QEMU — System invocation and networking](https://www.qemu.org/docs/master/system/invocation.html).
8. [Canonical — Ubuntu24.04 cloud images](https://cloud-images.ubuntu.com/noble/current/).
