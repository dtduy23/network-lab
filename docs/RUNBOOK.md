# Runbook vận hành và xử lý sự cố

Các lệnh quản trị dưới đây thực hiện **trong guest** sau `./labctl ssh NODE`, trừ lệnh ghi rõ chạy trên controller. Account `vagrant` dùng sudo; account operator chỉ dùng các lệnh đọc đã được cấp trong sudoers. Sau khi sửa thủ công để thực hành, `./labctl provision` đưa file cấu hình được quản lý về trạng thái khai báo.

## SOP-01: Kiểm tra đầu ngày

```bash
# Controller
./labctl verify
# Từng guest
sudo systemctl --no-pager status ssh fail2ban lab-health.timer
sudo systemctl start lab-health.service
sudo tail -n 1 /var/log/network-lab/health.jsonl | jq
sudo cat /var/lib/network-lab/health.prom
sudo systemctl list-timers --all
df -h /; df -i /; free -h; uptime
```

Server kiểm tra thêm `lab-backup.timer`, backup mới nhất, `named`, `nginx`, `postgresql@16-main`. Exit code health: `0` khỏe, `1` có ngưỡng vượt/service không hoạt động/backup thiếu hoặc cũ, `2` lỗi đọc cấu hình/đo dữ liệu. Systemd OnFailure ghi alert vào `/var/log/network-lab/alerts.jsonl` và journal; đây là cảnh báo local, chưa gửi email/Slack.

## SOP-02: DNS không phân giải

1. Client: `ip -4 addr show lan0`, `ip route`, `resolvectl status`; phân biệt lỗi IP, route và resolver.
2. `dig @10.20.10.10 www.infra.test +time=2 +tries=1`; nếu direct query thành công nhưng query bình thường thất bại, kiểm tra DNS nhận qua DHCP.
3. Thử cả UDP và TCP: `dig +tcp @10.20.10.10 www.infra.test`; một số câu trả lời lớn dùng TCP.
4. Server: `sudo ss -lntup | rg ':53'`, `sudo named-checkconf -z`, `sudo journalctl --no-pager -u named -n 50`.
5. Router: `sudo iptables -nvL FORWARD`; packet capture đồng thời hai phía.

```bash
# Client
sudo tcpdump -ni lan0 'port 53'
# Router
sudo tcpdump -ni lan0 'port 53'
sudo tcpdump -ni dmz0 'port 53'
# Server
sudo tcpdump -ni dmz0 'port 53'
```

`NXDOMAIN` nghĩa là resolver trả lời tên không tồn tại; timeout có thể là firewall/route/service; `REFUSED` là policy DNS. Không mở `allow-recursion { any; };` để xử lý nhanh. Tên ngoài còn phụ thuộc forwarders và Internet; các kiểm thử local không chứng minh mọi resolver bên ngoài truy cập được.

## SOP-03: DHCP không cấp IP

```bash
# Router
sudo dnsmasq --test
sudo systemctl --no-pager status dnsmasq
sudo journalctl --no-pager -u dnsmasq -n 100
sudo cat /var/lib/misc/dnsmasq.leases
sudo tcpdump -ni lan0 'udp port 67 or udp port 68'
# Client dùng systemd-networkd
sudo networkctl status lan0
sudo networkctl renew lan0
ip -4 addr show lan0
ip route show default
resolvectl status lan0
```

Kiểm tra DORA: Discover → Offer → Request → Ack. Không có Discover ở router: sai NIC, sai internal network, link down. Có Discover nhưng không Offer: service/interface/firewall. Có nhiều Offer: provider hoặc DHCP server khác đang hoạt động; tắt DHCP của mạng lab ở provider, không tắt DHCP management. Reservation dựa trên MAC trong `lab.yml`; không tự đổi MAC client.

## SOP-04: Web hoặc TLS lỗi

```bash
# Client
curl -v --max-time 5 http://www.infra.test/healthz
# Server
sudo nginx -t
sudo ss -lntp | rg ':80|:443'
sudo tail -n 30 /var/log/nginx/network-lab-error.log
sudo openssl x509 -in /etc/nginx/network-lab-tls/server.crt -noout -dates -ext subjectAltName
```

Certificate self-signed cần được lấy từ server qua management SSH và dùng `curl --cacert`. `./labctl verify` làm việc này tự động. Lỗi certificate không có nghĩa là lỗi firewall; không dùng `curl -k` làm bằng chứng TLS được kiểm chứng.

## SOP-05: Firewall/NAT

```bash
# Router
sudo iptables-save
sudo iptables -nvL INPUT
sudo iptables -nvL FORWARD
sudo iptables -t nat -nvL
sysctl net.ipv4.ip_forward
sudo journalctl --no-pager -k | rg 'LAB .* DROP'
# Server/client
sudo ufw status verbose
sudo ss -lntup
```

Kiểm tra từ L1→L7: link/interface, IP/MAC và ARP, route, port/firewall, TLS, HTTP/service log. `nc` thất bại khi không có listener không chứng minh firewall; integration mở listener thật và tạm tắt UFW server để chứng minh router chặn. Không flush firewall trên host để sửa lab.

Khôi phục policy guest router:

Controller có thể chạy `./labctl firewall` để dùng lại router role và kiểm tra policy trước khi nạp.

```bash
sudo iptables-restore --test < /etc/network-lab/iptables.rules
sudo systemctl restart lab-firewall
sudo systemctl restart fail2ban
```

Khôi phục UFW server/client:

```bash
sudo bash /etc/network-lab/apply-ufw.sh
sudo systemctl restart fail2ban
```

Firewall reload có thể xóa chain ban hiện tại; Fail2ban restart dựng lại chain. Luôn kiểm tra `fail2ban-client status sshd` sau đó.

## SOP-06: Backup và restore drill

```bash
# Server
sudo systemctl start lab-backup.service
sudo journalctl --no-pager -u lab-backup.service -n 30
sudo find /var/backups/network-lab -maxdepth 2 -type f
# Thay PACKAGE bằng directory thực do backup in ra trong journal.
sudo python3 /usr/local/sbin/validate_backup.py /var/backups/network-lab/PACKAGE
sudo /usr/local/sbin/lab-restore /var/backups/network-lab/PACKAGE lab_restore_drill
sudo -u postgres psql -X -d lab_restore_drill -c 'SELECT * FROM lab_events ORDER BY id;'
sudo -u postgres dropdb lab_restore_drill
```

Restore chỉ nhận database mới `lab_restore_*`, từ chối target đã tồn tại hoặc tên nguồn `labapp`. Trước khi tạo DB, kiểm tra manifest, thời gian có timezone, kích thước và SHA-256. Restore dùng transaction và exit-on-error; nếu lỗi sau createdb, xóa chính DB tạm vừa tạo. Nếu người khác tạo cùng tên trước createdb, không cài cleanup trap và không xóa DB của họ.

Không đưa private key, dump thật hoặc dữ liệu nhạy cảm lên repo. Backup hiện có cùng failure domain với server; bổ sung offsite/encryption và xác minh restore định kỳ nếu triển khai thực tế. `pg_dump` chỉ bao phủ database lab; không backup cluster roles, tablespaces hoặc WAL/PITR.

## SOP-07: SSH và Fail2ban

```bash
sudo sshd -t
sudo sshd -T | rg 'permitrootlogin|passwordauthentication|kbdinteractiveauthentication|maxauthtries'
sudo fail2ban-client status sshd
sudo fail2ban-client set sshd banip 10.20.20.200
sudo iptables-save | rg f2b
sudo fail2ban-client set sshd unbanip 10.20.20.200
```

Dùng một IP test lab chưa có máy dùng; không ban IP controller. Vì SSH password đã bị tắt, log có thể là failed publickey/auth failure; filter sshd vẫn cần đối chiếu journal thực. Integration xác minh filter với fixture failed-password và kiểm tra ban/unban thật; chưa mô phỏng đủ chuỗi lỗi khóa SSH theo thời gian trong VM.

## SOP-08: Tái lập và checklist reboot

```bash
# Controller
./labctl halt
./labctl up
./labctl verify
./labctl provision
```

Sau reboot kiểm tra: NIC giữ đúng tên/MAC, không có default route management trên endpoints, DHCP lease/resolver đúng, firewall được nạp trước dịch vụ, named/nginx/PostgreSQL/Fail2ban active, timers active. Chạy provision lần hai và kiểm tra các file cấu hình không thay đổi ngoài thao tác vận hành chủ động như backup/seed verification.

## Mẫu báo cáo sự cố

```text
Incident ID / thời điểm / người xử lý:
Ảnh hưởng: DNS, DHCP, web, SSH hay backup; máy/subnet nào bị ảnh hưởng?
Triệu chứng và bước tái hiện:
Bằng chứng: lệnh, timestamp, log, capture, route/rule counters.
Nguyên nhân đã xác minh:
Thay đổi khôi phục / rollback:
Kết quả kiểm tra sau sửa:
Hành động phòng ngừa / giới hạn chưa kiểm chứng:
```
