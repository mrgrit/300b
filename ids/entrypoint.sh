#!/usr/bin/env bash
# 300B IDS entrypoint — Suricata IDS 모드로 dmz 인터페이스 sniff.
# eve.json → rsyslog forward → siem (Wazuh manager 가 받음).
set -euo pipefail

/usr/local/bin/sshd_setup.sh

# rsyslog 로 eve.json 을 siem 으로 forward (siem 컨테이너 514/udp).
mkdir -p /etc/rsyslog.d /var/log/suricata
cat > /etc/rsyslog.d/30-300b-ids.conf <<EOF
# Suricata eve.json → siem (rsyslog imfile + omfwd)
module(load="imfile")
input(type="imfile" File="/var/log/suricata/eve.json" Tag="suricata" Severity="info")
*.* @300b-siem:514
EOF
service rsyslog start 2>/dev/null || true

# Suricata 인터페이스 자동 감지 — dmz 측 (300b-dmz network) 의 eth*.
IFACE="$(ip -o -4 route show to default 2>/dev/null | awk '{print $5; exit}')"
# default route 는 edge 일 수 있으니, 보통 dmz 가 두 번째 인터페이스. 두 NIC 둘 다 sniff 해도 무방.
ALL_IFACES="$(ip -o link show | awk -F': ' '{print $2}' | grep -E '^eth' | tr '\n' ',' | sed 's/,$//')"
SNIFF_IFACE="${SURICATA_IFACE:-${ALL_IFACES:-eth0}}"

echo "[ids] suricata sniff interface(s)=${SNIFF_IFACE}"
mkdir -p /var/log/suricata /var/run/suricata

# Suricata 가 IDS 모드로 백그라운드 실행. 이미 떠있으면 skip.
if ! pgrep -x suricata >/dev/null; then
    suricata -i "${SNIFF_IFACE}" \
             -l /var/log/suricata \
             --pidfile /var/run/suricata/suricata.pid \
             -D 2>&1 | head -20 || echo "[ids] suricata 시작 실패 — privileged/cap 확인."
fi

# 시작 후 상태 확인 — 학생용 가시화.
sleep 2
if pgrep -x suricata >/dev/null; then
    echo "[ids] ✅ suricata running (pid=$(pgrep -x suricata))"
else
    echo "[ids] ⚠️ suricata not running — /var/log/suricata/suricata.log 확인"
fi

echo "[ids] sshd foreground"
exec /usr/sbin/sshd -D -e
