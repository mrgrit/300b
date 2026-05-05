# 300B Private DNS — Phase D 에서 활성화. *.300b 도메인을 fw 자신의 host_ip 로 응답.
# AWS Route 53 private hosted zone 시뮬레이션.

# wildcard A record — 학생 PC 의 DNS 서버를 VM IP 로 지정하면 모든 *.300b 가 fw 로 옴.
address=/.300b/${HOST_IP}

# 로컬 docker DNS 로 fallback (컨테이너 이름 해석)
server=127.0.0.11

# 외부 도메인 forwarding — 학생이 일반 인터넷도 사용 가능하도록.
server=8.8.8.8
server=1.1.1.1

# 인터페이스 — fw 의 모든 NIC 에서 listen.
listen-address=0.0.0.0
bind-interfaces

# 로깅 — 학습용으로 모든 query 기록.
log-queries
log-facility=/var/log/dnsmasq.log

# 캐시
cache-size=1000

# DHCP 비활성화 — 우린 docker bridge 가 IP 할당.
no-dhcp-interface=
