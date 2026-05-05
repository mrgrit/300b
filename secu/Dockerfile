FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

RUN apt-get update && apt-get install -y --no-install-recommends \
        nftables \
        iptables \
        suricata \
        dnsmasq \
        rsyslog \
        openssh-server \
        sudo \
        ca-certificates \
        curl \
        iproute2 \
        iputils-ping \
        net-tools \
        tcpdump \
        dnsutils \
        bind9-utils \
        vim-tiny \
        less \
        procps \
        cron \
        python3 \
        tzdata \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && rm -rf /var/lib/apt/lists/*

# Suricata 룰 업데이트 1회 (오프라인 대비) — 실패해도 빌드 계속.
RUN suricata-update update-sources 2>/dev/null || true \
    && suricata-update 2>/dev/null || true

COPY common/sshd_setup.sh /usr/local/bin/sshd_setup.sh
COPY secu/entrypoint.sh /usr/local/bin/entrypoint.sh
# systemctl/journalctl shim (gdraheim/docker-systemctl-replacement) — 학생이 실서버처럼 systemctl status/start/restart 사용 가능.
COPY common/systemctl3.py /usr/local/bin/systemctl3.py
COPY common/journalctl3.py /usr/local/bin/journalctl3.py
RUN chmod +x /usr/local/bin/sshd_setup.sh /usr/local/bin/entrypoint.sh \
                /usr/local/bin/systemctl3.py /usr/local/bin/journalctl3.py \
    && ln -sf /usr/local/bin/systemctl3.py /usr/local/bin/systemctl \
    && ln -sf /usr/local/bin/journalctl3.py /usr/local/bin/journalctl

EXPOSE 22 514/udp 514/tcp
CMD ["/usr/local/bin/entrypoint.sh"]
