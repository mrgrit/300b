#!/usr/bin/env bash
# 300B WAF entrypoint — Apache + ModSecurity + reverse proxy + (Phase C: TLS).
set -euo pipefail

/usr/local/bin/sshd_setup.sh

# rsyslog — modsec audit log 를 siem 으로 forward (Phase B/이후 활성).
service rsyslog start 2>/dev/null || true

# Apache vhost upstream 컨테이너가 아직 안 떴을 때 a2ensite 가 ProxyPass 를 즉시 해석 안 하므로 OK
# (Apache 는 첫 요청 때 DNS lookup).

# Phase C: TLS cert 자동 생성 (이미 있으면 skip).
if [ -d /opt/cert-gen ] && [ "${ENABLE_TLS:-false}" = "true" ]; then
    if [ ! -f /etc/ssl/300b/ca.pem ]; then
        echo "[waf] 자체 CA + 서버 인증서 9개 생성 중 …"
        bash /opt/cert-gen/gen.sh
    fi
    # 443 vhost 활성 (TLS 용)
    for h in 00-landing juice dvwa neobank govportal mediforum admin ai wazuh bastion portal; do
        a2ensite "${h}-tls.conf" 2>/dev/null || true
    done
fi

mkdir -p /var/run/apache2 /var/log/apache2

# envvars unbound var workaround.
set +u
. /etc/apache2/envvars
set -u

# config 검증 — 실패면 즉시 종료해서 학생이 stderr 보고 디버그.
apache2ctl configtest

echo "[waf] sshd background + apache2 foreground"
/usr/sbin/sshd -e
exec apache2 -D FOREGROUND
