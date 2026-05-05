#!/usr/bin/env bash
set -euo pipefail

/usr/local/bin/sshd_setup.sh

# msf DB 초기화 (msf 가 설치된 경우만, --init-only).
if command -v msfdb >/dev/null 2>&1; then
    msfdb init --no-prompt 2>/dev/null || true
fi

# 학생 홈에 안내 파일.
HOME_DIR="/home/${SSH_USER:-ccc}"
mkdir -p "$HOME_DIR"
cat > "$HOME_DIR/README.txt" <<'EOF'
300B Attacker 컨테이너 — 13 도구 + Metasploit + Impacket
주요 명령:
  nmap, hydra, sqlmap, nikto, dirb, gobuster, whatweb,
  enum4linux, hashcat, john, smbclient, msfconsole,
  impacket-secretsdump, impacket-psexec, impacket-smbclient

타깃 (docker network 내부 DNS):
  300b-web        : Apache + ModSecurity (수업용 reverse proxy)
  juiceshop      : http://juiceshop:3000
  dvwa           : http://dvwa:80
  neobank        : http://neobank:3001
  govportal      : http://govportal:3002
  mediforum      : http://mediforum:3003
  adminconsole   : http://adminconsole:3004
  aicompanion    : http://aicompanion:3005
  300b-secu       : nftables/Suricata gateway
  300b-siem       : rsyslog 514, cti-collector
  wazuh-manager  : 1514 (agent), 514 (syslog)

Wazuh dashboard 는 호스트(VM) 외부 https://<VM_IP>:1443 에서 접속.
EOF
chown "${SSH_USER:-ccc}":"${SSH_USER:-ccc}" "$HOME_DIR/README.txt" 2>/dev/null || true

echo "[attacker] sshd foreground"
exec /usr/sbin/sshd -D -e
