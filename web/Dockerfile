FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

RUN apt-get update && apt-get install -y --no-install-recommends \
        apache2 \
        libapache2-mod-security2 \
        modsecurity-crs \
        openssh-server \
        sudo \
        ca-certificates \
        curl \
        wget \
        iproute2 \
        iputils-ping \
        net-tools \
        dnsutils \
        vim-tiny \
        less \
        procps \
        rsyslog \
        cron \
        python3 \
        tzdata \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && rm -rf /var/lib/apt/lists/*

# ModSecurity CRS 활성화.
RUN a2enmod security2 headers rewrite proxy proxy_http \
    && cp /etc/modsecurity/modsecurity.conf-recommended /etc/modsecurity/modsecurity.conf \
    && sed -ri 's|^SecRuleEngine .*|SecRuleEngine On|' /etc/modsecurity/modsecurity.conf

COPY common/sshd_setup.sh /usr/local/bin/sshd_setup.sh
COPY web/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY web/landing/ /var/www/html/
# systemctl/journalctl shim — 학생이 실서버처럼 systemctl status apache2 등 사용 가능.
COPY common/systemctl3.py /usr/local/bin/systemctl3.py
COPY common/journalctl3.py /usr/local/bin/journalctl3.py
RUN chmod +x /usr/local/bin/sshd_setup.sh /usr/local/bin/entrypoint.sh \
                /usr/local/bin/systemctl3.py /usr/local/bin/journalctl3.py \
    && ln -sf /usr/local/bin/systemctl3.py /usr/local/bin/systemctl \
    && ln -sf /usr/local/bin/journalctl3.py /usr/local/bin/journalctl

EXPOSE 22 80
CMD ["/usr/local/bin/entrypoint.sh"]
