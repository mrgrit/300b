#!/usr/bin/env bash
set -euo pipefail

/usr/local/bin/sshd_setup.sh

service rsyslog start 2>/dev/null || true

# Apache 부트 — envvars 가 unbound vars 를 사용해 set -u 와 충돌하므로 잠시 해제.
mkdir -p /var/run/apache2 /var/log/apache2
set +u
. /etc/apache2/envvars
set -u
echo "[web] sshd background + apache2 foreground"
/usr/sbin/sshd -e
exec apache2 -D FOREGROUND
