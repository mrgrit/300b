FROM ubuntu:22.04

# 300B WAF — Apache + ModSecurity v2 + OWASP CRS, 8 vhost reverse proxy.
# AWS ALB + AWS WAF 단일 VM 시뮬레이션.

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
        openssl \
        tzdata \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && rm -rf /var/lib/apt/lists/*

# ModSecurity + 필요한 mod 활성.
RUN a2enmod security2 headers rewrite proxy proxy_http proxy_wstunnel ssl deflate \
    && cp /etc/modsecurity/modsecurity.conf-recommended /etc/modsecurity/modsecurity.conf \
    && sed -ri 's|^SecRuleEngine .*|SecRuleEngine On|' /etc/modsecurity/modsecurity.conf \
    && sed -ri 's|^SecAuditEngine .*|SecAuditEngine RelevantOnly|' /etc/modsecurity/modsecurity.conf

# Debian modsecurity-crs 패키지가 /etc/modsecurity/crs/ 에 룰 + crs-setup.conf 자동 배치.
# /etc/apache2/mods-enabled/security2.conf 가 이미 IncludeOptional /etc/modsecurity/*.conf 로 로드.
# 추가 include 불필요 (중복 시 'rule with same id' 에러).

# 기본 default vhost 비활성 — name-based vhost 만 사용.
RUN a2dissite 000-default 2>/dev/null || true

COPY common/sshd_setup.sh /usr/local/bin/sshd_setup.sh
COPY waf/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY waf/vhost/ /etc/apache2/sites-available/
COPY waf/landing/ /var/www/landing/
COPY waf/cert-gen/ /opt/cert-gen/
# systemctl/journalctl shim
COPY common/systemctl3.py /usr/local/bin/systemctl3.py
COPY common/journalctl3.py /usr/local/bin/journalctl3.py
RUN chmod +x /usr/local/bin/sshd_setup.sh /usr/local/bin/entrypoint.sh \
                /usr/local/bin/systemctl3.py /usr/local/bin/journalctl3.py \
    && find /opt/cert-gen -name '*.sh' -exec chmod +x {} \; 2>/dev/null || true \
    && ln -sf /usr/local/bin/systemctl3.py /usr/local/bin/systemctl \
    && ln -sf /usr/local/bin/journalctl3.py /usr/local/bin/journalctl

# 10 개 vhost 활성 (landing + 9 backend). HTTP 만 — TLS 는 Phase C 에서 cert 생성 후 활성.
RUN for h in 00-landing juice dvwa neobank govportal mediforum admin ai wazuh bastion; do \
        a2ensite "${h}.conf" 2>/dev/null || true ; \
    done

EXPOSE 22 80 443
CMD ["/usr/local/bin/entrypoint.sh"]
