#!/usr/bin/env bash
set -euo pipefail

/usr/local/bin/sshd_setup.sh

service rsyslog start 2>/dev/null || true

# cti-collector 가 컨테이너 안에 있으면 cron 등록.
if [ -f /opt/app/apps/cti-collector/collector.py ]; then
    cat > /etc/cron.d/300b-cti <<'EOF'
# 300B CTI Collector — 매일 04:30 NVD CVE 수집
30 4 * * * root cd /opt/app && /usr/bin/python3 -m apps.cti-collector.collector --hours 24 --limit 30 >> /var/log/300b-cti.log 2>&1
EOF
    chmod 644 /etc/cron.d/300b-cti
    service cron start 2>/dev/null || true
    echo "[siem] cti-collector cron 등록 완료"
fi

echo "[siem] sshd foreground"
exec /usr/sbin/sshd -D -e
