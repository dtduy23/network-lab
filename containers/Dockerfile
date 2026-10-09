FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    bind9 bind9-utils dnsutils dnsmasq nginx postgresql-16 postgresql-client-16 \
    python3 openssl iproute2 iptables ufw isc-dhcp-client netcat-openbsd curl \
    tcpdump fail2ban rsyslog logrotate netplan.io systemd openssh-server sudo \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /etc/network-lab /var/log/network-lab /var/lib/network-lab \
    /var/backups/network-lab /var/www/network-lab /etc/nginx/network-lab-tls \
    /run/sshd /run/fail2ban /var/lib/misc
CMD ["sleep", "infinity"]
