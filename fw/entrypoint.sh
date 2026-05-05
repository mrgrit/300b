#!/usr/bin/env bash
# 300B Edge Firewall entrypoint — DNAT/forward 룰 적용 + dnsmasq 기동.
set -euo pipefail

/usr/local/bin/sshd_setup.sh

# IP forwarding 활성화 — fw 가 라우터 역할.
sysctl -w net.ipv4.ip_forward=1 >/dev/null
sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null 2>&1 || true

# 인터페이스 자동 감지 — docker compose 가 NIC 순서를 비결정적으로 할당하므로
# subnet 기반으로 edge/dmz/mgmt 매핑.
detect_iface_for_subnet() {
    local subnet_prefix="$1"   # 예: "172.30.10."
    ip -o -4 addr show 2>/dev/null | awk -v p="$subnet_prefix" '
        $4 ~ "^"p { sub(/\/.*/, "", $4); split($2, a, "@"); print a[1]; exit }'
}
EDGE_IFACE="$(detect_iface_for_subnet 172.30.10.)"
DMZ_IFACE="$(detect_iface_for_subnet 172.30.20.)"
MGMT_IFACE="$(detect_iface_for_subnet 172.30.40.)"
echo "[fw] iface map: edge=${EDGE_IFACE:-?}  dmz=${DMZ_IFACE:-?}  mgmt=${MGMT_IFACE:-?}"

if [ -z "${EDGE_IFACE:-}" ] || [ -z "${DMZ_IFACE:-}" ]; then
    echo "[fw] ⚠️ edge/dmz 인터페이스 자동 감지 실패 — 컨테이너 NIC 구성 확인."
fi

# WAF 의 dmz 측 IP 자동 해석 — docker DNS 로.
if [ -z "${WAF_DMZ_IP:-}" ]; then
    for h in 300b-waf waf; do
        # dmz 측 IP 만 골라야 — getent 가 모든 NIC 의 IP 를 반환하므로 172.30.20.x 필터.
        ip="$(getent ahosts "$h" 2>/dev/null | awk '$1 ~ /^172\.30\.20\./ {print $1; exit}')"
        if [ -n "$ip" ]; then
            WAF_DMZ_IP="$ip"
            break
        fi
    done
fi
if [ -z "${WAF_DMZ_IP:-}" ]; then
    echo "[fw] ⚠️ 300b-waf 의 dmz IP 해석 실패 — socat forward 미적용."
else
    echo "[fw] WAF_DMZ_IP=${WAF_DMZ_IP}"
    export WAF_DMZ_IP EDGE_IFACE DMZ_IFACE MGMT_IFACE
    envsubst '${WAF_DMZ_IP} ${EDGE_IFACE} ${DMZ_IFACE} ${MGMT_IFACE}' < /etc/nftables.nft.tpl > /etc/nftables.nft
    nft -f /etc/nftables.nft && echo "[fw] nftables 룰 로드 완료"

    # AWS NLB 시뮬: socat 이 host:80/443 으로 들어온 연결을 waf 로 L4 forward.
    # docker-proxy 가 fw 컨테이너 IP:80 으로 보내면 socat 이 받아 waf 로 다시 연결.
    echo "[fw] socat L4 forwarder 시작: 80/443 → ${WAF_DMZ_IP}"
    socat TCP-LISTEN:80,reuseaddr,fork  TCP:${WAF_DMZ_IP}:80  >/var/log/socat-80.log  2>&1 &
    socat TCP-LISTEN:443,reuseaddr,fork TCP:${WAF_DMZ_IP}:443 >/var/log/socat-443.log 2>&1 &
fi

# dnsmasq — Phase D 에서 활성화. fw 의 host_ip (eth0 — edge 측) 로 *.300b 응답.
HOST_IP="$(ip -4 -o addr show eth0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"
if [ -n "${HOST_IP:-}" ]; then
    export HOST_IP
    envsubst '${HOST_IP}' < /etc/dnsmasq.d/300b.conf.tpl > /etc/dnsmasq.d/300b.conf
    # /etc/resolv.conf 의 nameserver 가 dnsmasq 자신을 가리키지 않도록 — 무한 loop 방지.
    rm -f /etc/dnsmasq.d/300b.conf.tpl
    if ${ENABLE_DNSMASQ:-false} ; then
        # systemd default service 비활성 (이미 docker 라 의미 없지만 깔끔)
        rm -f /etc/dnsmasq.conf 2>/dev/null || true
        dnsmasq --conf-dir=/etc/dnsmasq.d --keep-in-foreground &
        echo "[fw] dnsmasq 기동 (background) — *.300b → ${HOST_IP}"
    else
        echo "[fw] dnsmasq 비활성 (ENABLE_DNSMASQ=false). Phase D 에서 활성화 예정."
    fi
fi

echo "[fw] sshd foreground"
exec /usr/sbin/sshd -D -e
