# Cài đặt và tái lập lab

## 1. Yêu cầu

- Controller Linux: Python ≥3.11, `python3-venv`, SSH client, Ruby, ShellCheck; Vagrant 2.4.x.
- Máy cá nhân khuyến nghị 8 GB RAM, 4 CPU và ≥12 GB đĩa trống. Ba VM cấp tổng 3 GB RAM, chưa tính overhead hypervisor.
- Guest cố định Ubuntu 24.04, PostgreSQL 16. Không dùng playbook này để quản lý máy cá nhân hoặc máy chủ sẵn có.
- Internet lần đầu để tải box, package Ubuntu và dependency Python. Controller dependency pin trong `requirements.txt`; package guest lấy security updates của Ubuntu. Muốn bất biến toàn bộ phải pin box version và snapshot kho package.

Ubuntu/Debian controller:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv openssh-client ruby shellcheck
./labctl bootstrap
```

Bootstrap chỉ tạo `.venv`, `.lab/keys/operator`, Vagrant home và Ansible temp trong dự án. Các private key không nằm trong source bàn giao.

## 2. Provider mặc định: VirtualBox

Cài VirtualBox và Vagrant theo hướng dẫn chính thức phù hợp kernel/controller. Cấu hình hai **internal networks** `network-infra-dmz` và `network-infra-lan`; provider không cấp DHCP cho hai mạng này. dnsmasq trong router là DHCP server của LAN.

```bash
./labctl doctor
./labctl up
./labctl verify
```

Box mặc định `bento/ubuntu-24.04`. Có thể đặt `LAB_BOX` nếu box thay thế có Ubuntu 24.04, systemd, Netplan và user `vagrant` với SSH key. Box phải hỗ trợ provider bạn chọn.

```bash
LAB_BOX=bento/ubuntu-24.04 ./labctl up
```

Vagrant NIC 1 giữ DHCP phục vụ SSH management; fixed MAC trong `lab.yml` cho Ansible nhận diện NIC chính xác khi provision lại. Router dùng NIC này làm WAN. Server/client không nhận default route/DNS từ management NIC; route mặc định đi qua router và UFW chặn kết nối outbound mới qua management, trừ DHCP. Kết nối SSH đã được thiết lập vẫn đi được nhờ state tracking.

## 3. Provider thay thế: libvirt/KVM

Controller cần KVM truy cập được, libvirt system connection, quyền quản lý mạng libvirt và plugin `vagrant-libvirt`. Việc cài hypervisor là thao tác trên máy cá nhân, thực hiện theo tài liệu chính thức của Ubuntu và vagrant-libvirt.

```bash
# labctl dùng Vagrant home riêng, vì vậy cài plugin vào đúng home này.
export VAGRANT_HOME="$PWD/.lab/vagrant-home"
vagrant plugin install vagrant-libvirt
LAB_PROVIDER=libvirt ./labctl doctor
LAB_PROVIDER=libvirt ./labctl up
LAB_PROVIDER=libvirt ./labctl verify
```

DMZ/LAN dùng `veryisolated`, `dhcp_enabled=false`, host IP cuối subnet `.254` để tránh địa chỉ router `.1`. Management dùng `172.29.240.0/24`. Không chạy đồng thời hai bản lab cùng subnet trên một Docker daemon/provider. Provider sẽ báo lỗi khi network có subnet trùng.

Nếu provider không có artifact cho box mặc định, dùng `LAB_BOX` trỏ tới box Ubuntu 24.04 có libvirt; kiểm tra metadata trước khi tải. Bộ bàn giao không cam kết box/provider tùy ý tương thích.

## 4. Kiểm thử khi chưa có hypervisor

Docker integration chỉ cần Docker engine, quyền gọi daemon và khoảng 2 GB đĩa cho image Ubuntu. Không cần `--privileged`; `NET_ADMIN` chỉ cấp trong container kiểm thử.

```bash
./labctl bootstrap
./labctl test
./labctl integration
cat artifacts/integration-results.json
```

Runner tạo prefix `network-infra-check-<id>`, hai bridge internal và một WAN bridge. IP `.254` của Docker không làm gateway thực nghiệm; gateway trong server/client được đổi sang router `.1`. Mọi container/network của lần chạy được xóa ở `finally`; image được giữ để lần sau chạy nhanh.

Nếu tiến trình bị SIGKILL hoặc máy mất điện, xem nhãn `network-infra.run` và xóa **đúng tài nguyên của lần chạy bị gián đoạn**; không dùng `docker system prune`.

## 4b. VM đầy đủ không cần KVM: QEMU TCG

Chế độ này dùng Ubuntu cloud image chính thức và mô phỏng CPU bằng phần mềm. Cần `qemu-system-x86_64`, `qemu-img`, curl và SSH; không cần libvirt, bridge, tuntap, sudo hoặc truy cập `/dev/kvm`.

```bash
sudo apt-get install -y qemu-system-x86 qemu-utils curl
./labctl bootstrap
LAB_PROVIDER=qemu ./labctl doctor
LAB_PROVIDER=qemu ./labctl up
./labctl verify
./labctl reboot
./labctl drills
./labctl halt
```

Mặc định QEMU cấp router512 MB, server1024 MB, client512 MB (2 GB tổng); nếu máy rộng RAM, đặt `LAB_QEMU_MEMORY_SCALE=1` để dùng tài nguyên như Vagrant. Lần boot đầu có thể mất vài phút; SSH được đợi tối đa10 phút/node. Log boot ở `.lab/qemu/NODE/console.log`.

2 GB là RAM cấp cho guest; emulator còn có overhead trên host. Sau khi xem demo, dùng `./labctl halt` để giữ dữ liệu và giải phóng tài nguyên. Bộ cấu hình Ansible tắt SSH multiplexing và dùng keepalive để tránh dùng lại phiên quản trị cũ sau thay đổi firewall.

LAN/DMZ dùng QEMU socket chỉ bind localhost:22110/22120. SSH bind localhost:2222/2200/2201; router forwarding bind localhost:8080. Cần các cổng này trống. Disk qcow2 overlay 16GB nằm trong workspace; image base được xác minh SHA-256 khi tải. Khóa provision khác khóa operator. `halt` tắt qua ACPI và giữ đĩa; `destroy` dừng và xóa overlays/seed của ba VM, giữ image cache và key. Khi backend QEMU đã được ghi nhận, `up` tự tiếp tục backend đó nếu không đặt LAB_PROVIDER. Đổi sang Vagrant cần destroy backend trước để tránh hai lab tranh cổng/trạng thái.

Tham khảo [QEMU networking](https://www.qemu.org/docs/master/system/invocation.html), [Ubuntu cloud images và checksums](https://cloud-images.ubuntu.com/noble/current/).

## 5. Provision, SSH và thu bằng chứng

```bash
./labctl provision
./labctl ssh server
./labctl verify | tee artifacts/vm-verification.txt
```

`ssh-config` tạo inventory thực từ port và key của Vagrant. Host key được lưu ở `.lab/known_hosts`, lần kết nối đầu dùng `accept-new`; khi VM đã destroy/recreate, xóa đúng entry cũ bằng `ssh-keygen -R '[127.0.0.1]:PORT' -f .lab/known_hosts` hoặc hostname thực tương ứng. Không bỏ host key checking toàn cục.

Đăng nhập operator: lấy IP/port từ `.lab/ssh-config`, dùng `ssh -i .lab/keys/operator -p PORT operator@HOST`. Không dùng operator để provision; account này chủ yếu xem log và trạng thái.

## 6. Báo cáo và gói bàn giao

```bash
sudo apt-get install -y pandoc texlive-xetex fonts-noto-core
./labctl report
python3 scripts/package.py
```

PDF được tạo trong `artifacts/bao-cao-do-an.pdf`, gói source trong `artifacts/network-infra-project.zip`. Báo cáo tự đọc JSON kiểm thử thật, không đánh dấu VM đã kiểm chứng khi chưa có kết quả VM.

Tài liệu tham khảo: [Vagrant networking](https://developer.hashicorp.com/vagrant/docs/providers/virtualbox/networking), [vagrant-libvirt configuration](https://vagrant-libvirt.github.io/vagrant-libvirt/configuration.html), [Netplan YAML](https://netplan.readthedocs.io/en/stable/netplan-yaml/).
