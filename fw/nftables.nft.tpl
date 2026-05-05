#!/usr/sbin/nft -f
# 300B Edge Firewall — entrypoint 가 envsubst 로 ${EDGE_IFACE}, ${DMZ_IFACE} 치환 후 적용.
# AWS Network Firewall 의 stateful filter 시뮬레이션 (L3/L4 ALLOW/DROP, 로깅).
# 실제 L4 forward 는 socat 가 user space 에서 처리 (docker-proxy 호환).

flush ruleset

table inet filter {
    chain input {
        type filter hook input priority 0 ; policy accept ;
        # SSH 는 mgmt 망에서만 허용 — bastion 통하지 않은 직접 접근 차단 (학습용).
        iifname "${MGMT_IFACE}" tcp dport 22 accept
        tcp dport 22 drop comment "ssh from non-mgmt"
        # 80/443 은 socat 이 listen — 패킷이 INPUT 으로 전달되어 socat 이 처리.
        # 그 외 INPUT 정책은 학습용으로 accept.
    }

    chain forward {
        type filter hook forward priority 0 ; policy drop ;
        ct state established,related accept
        # 학습용: 다른 forward 는 일단 모두 drop (egress filter Phase B 에서 추가).
        log prefix "[300b-fw drop fwd] " level info
    }

    chain output {
        type filter hook output priority 0 ; policy accept ;
    }
}

# 학습용 NAT 룰 — 현재 실제로는 socat 이 L4 forward 하므로 적용 안 됨.
# 학생이 "AWS NAT GW 룰 작성" 학습용으로 참조 가능.
table ip nat {
    chain prerouting {
        type nat hook prerouting priority -100 ;
        # 참고: socat 이 80/443 listen 하므로 PREROUTING DNAT 는 hit 안 됨.
        # 학생이 "이 룰이 hit 안 되는 이유" 를 이해하는 것도 학습 포인트.
    }

    chain postrouting {
        type nat hook postrouting priority 100 ;
        # dmz 로 보낼 때 source NAT — socat 가 이미 source IP 변경하므로 의미 없음.
        oifname "${DMZ_IFACE}" masquerade
    }
}
