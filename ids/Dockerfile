FROM ubuntu:22.04

# 300B IDS — AWS GuardDuty / VPC Traffic Mirroring 시뮬레이션.
# Suricata IDS 모드로 dmz 인터페이스 sniff → eve.json 알람 발행 → siem 으로 forward.

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

RUN apt-get update && apt-get install -y --no-install-recommends \
        suricata \
        rsyslog \
        iproute2 \
        iputils-ping \
        net-tools \
        tcpdump \
        dnsutils \
        openssh-server \
        sudo \
        ca-certificates \
        curl \
        vim-tiny \
        less \
        procps \
        cron \
        jq \
        python3 \
        tzdata \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && rm -rf /var/lib/apt/lists/*

# ETOpen 룰 다운로드 (오프라인 대비 — 빌드 실패해도 진행).
RUN suricata-update update-sources 2>/dev/null || true \
    && suricata-update 2>/dev/null || true

COPY common/sshd_setup.sh /usr/local/bin/sshd_setup.sh
COPY ids/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY ids/suricata.yaml /etc/suricata/300b-overrides.yaml
# systemctl/journalctl shim
COPY common/systemctl3.py /usr/local/bin/systemctl3.py
COPY common/journalctl3.py /usr/local/bin/journalctl3.py
RUN chmod +x /usr/local/bin/sshd_setup.sh /usr/local/bin/entrypoint.sh \
                /usr/local/bin/systemctl3.py /usr/local/bin/journalctl3.py \
    && ln -sf /usr/local/bin/systemctl3.py /usr/local/bin/systemctl \
    && ln -sf /usr/local/bin/journalctl3.py /usr/local/bin/journalctl

EXPOSE 22
CMD ["/usr/local/bin/entrypoint.sh"]
