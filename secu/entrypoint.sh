#!/usr/bin/env bash
set -euo pipefail

/usr/local/bin/sshd_setup.sh

# IP forward — 학습용이라 가능한 경우에만 (--privileged 가 아니면 silent skip).
sysctl -w net.ipv4.ip_forward=1 2>/dev/null || true

# rsyslog (514/udp,tcp 수신은 siem 이 담당하므로 secu 는 forwarder 만).
service rsyslog start 2>/dev/null || true

# Suricata — 컨테이너 인터페이스 자동 감지.
IFACE="$(ip -o -4 route show to default | awk '{print $5; exit}')"
if [ -n "${IFACE:-}" ] && command -v suricata >/dev/null 2>&1; then
    echo "[secu] suricata on iface=${IFACE}"
    suricata -i "${IFACE}" -D 2>/dev/null || echo "[secu] suricata 시작 실패 (privileged 필요)"
fi

# dnsmasq — 컨테이너 간 이름 분해는 docker DNS 가 처리하므로 옵션.
service dnsmasq start 2>/dev/null || true

echo "[secu] sshd foreground"
exec /usr/sbin/sshd -D -e
