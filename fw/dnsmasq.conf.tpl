# 300B Private DNS — fw 가 *.300b.lab 도메인을 자신의 VM-host IP 로 응답.
# AWS Route 53 private hosted zone 시뮬레이션. 학생 PC 의 DNS 서버를 VM IP 로 지정하면
# 별도 /etc/hosts 편집 없이 juice.300b.lab 등 사용 가능.

# wildcard A record — 학생이 다양한 sub-host 만들어도 fw 로 자동 해석.
address=/.300b.lab/${HOST_IP}

# 로컬 docker DNS 로 fallback (컨테이너 이름 해석 — 다른 컨테이너 이름 질의 대응)
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

# DHCP 비활성화 — docker bridge 가 IP 할당.
no-dhcp-interface=
