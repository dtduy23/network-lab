# Timeline Git dựng lại: 15/09–14/10/2026

Lịch sử Git này được dựng lại từ bộ source hiện tại theo lộ trình 30 ngày, tính cả ngày đầu và ngày cuối. Ngày tác giả và ngày commit được gán theo các mốc dưới đây; chúng không phải nhật ký xác nhận công việc đã diễn ra vào những ngày đó.

Ngày nghiệm thu thực tế vẫn là **14/10/2026**. Các timestamp trong kết quả kiểm thử và biên bản nghiệm thu được giữ nguyên.

| Ngày | Nội dung commit | Thành phần |
|---|---|---|
| 15/09/2026 | Khởi tạo cấu trúc và cấu hình lab | `.gitignore`, `.gitattributes`, `lab.yml`, dependencies, Makefile |
| 17/09/2026 | Khai báo VM và kiểm tra controller | Vagrantfile, doctor, inventory, Ansible config |
| 19/09/2026 | Cấu hình nền tảng và SSH | Common role, operator, sudo, Fail2ban |
| 21/09/2026 | Cấu hình mạng guest | Netplan theo MAC, route, sysctl |
| 23/09/2026 | Triển khai router | DHCP, iptables, NAT/DNAT, firewall service |
| 25/09/2026 | Triển khai dịch vụ DMZ | BIND9, Nginx/TLS, PostgreSQL, dữ liệu demo |
| 27/09/2026 | Cấu hình firewall endpoint | UFW cho server và client |
| 29/09/2026 | Bổ sung sao lưu và khôi phục | Backup, manifest/checksum, restore sang DB mới |
| 01/10/2026 | Bổ sung vận hành định kỳ | Healthcheck, alert, systemd timer, logrotate |
| 03/10/2026 | Tích hợp CLI và orchestration | `labctl`, render templates, các playbook triển khai |
| 05/10/2026 | Thêm provider QEMU | Cloud image, NoCloud seed, mạng và vòng đời VM |
| 07/10/2026 | Thêm regression và xác minh VM | Pytest, verify playbook, reboot playbook |
| 09/10/2026 | Thêm integration và CI | Docker lab, kiểm tra gói tin, GitHub Actions |
| 11/10/2026 | Thêm kịch bản sự cố và nghiệm thu | Failure drills, ghi nhận VM, tổng hợp bằng chứng |
| 13/10/2026 | Hoàn thiện tài liệu và xuất bản | Kiến trúc, SOP, demo, báo cáo, slide, script đóng gói |
| 14/10/2026 | Bàn giao source và bằng chứng thực tế | README, timeline, kết quả kiểm thử và nghiệm thu |

Các commit nhóm file theo chức năng để đọc và rà soát. Đây là cách chia bộ source hoàn chỉnh thành các mốc, không phải bản tái hiện từng thay đổi trung gian. Có thể xem lịch sử bằng:

```bash
git log --reverse --format='%h %ad %s' --date=short
```

Git lưu source, tài liệu gốc và bằng chứng nghiệm thu đã rà soát. VM, khóa riêng, môi trường Python, file PDF/ZIP xuất ra và log runtime thô nằm ngoài Git theo `.gitignore`; chúng vẫn được giữ tại máy và có thể sinh lại bằng các lệnh trong README.
