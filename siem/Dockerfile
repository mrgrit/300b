FROM ubuntu:22.04

# 300B SIEM 사이드카: Wazuh manager/indexer/dashboard 는 별도 서비스 (wazuh 공식 이미지).
# 이 컨테이너는 cti-collector(NVD/뉴스 수집) + rsyslog 보조 + ssh 접근만 담당.

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        openssh-server \
        sudo \
        ca-certificates \
        curl \
        wget \
        git \
        rsyslog \
        cron \
        jq \
        iproute2 \
        iputils-ping \
        net-tools \
        dnsutils \
        vim-tiny \
        less \
        procps \
        tzdata \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && rm -rf /var/lib/apt/lists/*

# rsyslog 가 다른 컨테이너 514/udp 를 받을 수 있도록 입력 모듈 활성화.
RUN printf '%s\n' \
        'module(load="imudp")' \
        'input(type="imudp" port="514")' \
        'module(load="imtcp")' \
        'input(type="imtcp" port="5514")' \
        > /etc/rsyslog.d/10-300b-listener.conf

# cti-collector 코드를 컨테이너 안에 복사 — 호스트 마운트 없음.
COPY src/apps/cti-collector  /opt/app/apps/cti-collector
COPY src/contents/threats    /opt/app/contents/threats
RUN touch /opt/app/__init__.py /opt/app/apps/__init__.py /opt/app/apps/cti-collector/__init__.py 2>/dev/null || true

COPY common/sshd_setup.sh /usr/local/bin/sshd_setup.sh
COPY siem/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/sshd_setup.sh /usr/local/bin/entrypoint.sh

EXPOSE 22 514/udp 5514/tcp
CMD ["/usr/local/bin/entrypoint.sh"]
