FROM ubuntu:22.04

# 300B Edge Firewall — AWS NLB + Network Firewall + Route 53 Resolver 의 단일 VM 시뮬레이션.
# 역할:
#   1. host:80, host:443 trafic 받아서 dmz 의 waf 로 DNAT 포워딩
#   2. nftables egress allowlist (mgmt 망에 한정 — Phase B)
#   3. dnsmasq 로 *.300b.lab 도메인 사설 DNS 서비스 (Phase D)
#   4. ssh 학습용 (학생이 nft list ruleset 등 직접 확인)

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

RUN apt-get update && apt-get install -y --no-install-recommends \
        nftables \
        iptables \
        iproute2 \
        iputils-ping \
        net-tools \
        tcpdump \
        dnsutils \
        bind9-utils \
        dnsmasq \
        socat \
        openssh-server \
        sudo \
        ca-certificates \
        curl \
        vim-tiny \
        less \
        procps \
        cron \
        python3 \
        gettext-base \
        tzdata \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY common/sshd_setup.sh /usr/local/bin/sshd_setup.sh
COPY fw/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY fw/nftables.nft.tpl /etc/nftables.nft.tpl
COPY fw/dnsmasq.conf.tpl /etc/dnsmasq.d/300b.conf.tpl
# systemctl/journalctl shim
COPY common/systemctl3.py /usr/local/bin/systemctl3.py
COPY common/journalctl3.py /usr/local/bin/journalctl3.py
RUN chmod +x /usr/local/bin/sshd_setup.sh /usr/local/bin/entrypoint.sh \
                /usr/local/bin/systemctl3.py /usr/local/bin/journalctl3.py \
    && ln -sf /usr/local/bin/systemctl3.py /usr/local/bin/systemctl \
    && ln -sf /usr/local/bin/journalctl3.py /usr/local/bin/journalctl

EXPOSE 22 53/udp 53/tcp 80 443
CMD ["/usr/local/bin/entrypoint.sh"]
