#!/usr/bin/env bash
# 300B Bastion entrypoint — sshd + bastion uvicorn + jumphost SSH config 자동 생성.
set -euo pipefail

/usr/local/bin/sshd_setup.sh

# ─── jumphost ~/.ssh/config 자동 생성 ───────────────────────────
# 학생이 bastion 안에서 'ssh attacker' 만 쳐도 동작하도록 alias 등록.
# Mgmt + dmz + edge 의 모든 코어 컨테이너 등록.
SSH_USER="${SSH_USER:-ccc}"
HOME_DIR="/home/${SSH_USER}"
mkdir -p "${HOME_DIR}/.ssh"
cat > "${HOME_DIR}/.ssh/config" <<'EOF'
# 300B 내부 컨테이너 SSH alias — bastion 컨테이너 안에서 사용.
# 학생: ssh attacker, ssh waf, ssh fw 등으로 바로 진입.

Host *
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR

# Mgmt tier
Host attacker 300b-attacker
    HostName 300b-attacker
    User ccc

Host secu 300b-secu
    HostName 300b-secu
    User ccc

Host siem 300b-siem
    HostName 300b-siem
    User ccc

# Edge / DMZ
Host fw 300b-fw
    HostName 300b-fw
    User ccc

Host waf 300b-waf
    HostName 300b-waf
    User ccc

Host ids 300b-ids
    HostName 300b-ids
    User ccc

# Wazuh manager (sshd 미장착 — 참고용)
Host wazuh-manager
    HostName wazuh-manager
    User root
EOF
chown -R "${SSH_USER}:${SSH_USER}" "${HOME_DIR}/.ssh"
chmod 700 "${HOME_DIR}/.ssh"
chmod 600 "${HOME_DIR}/.ssh/config"

# Login banner — 학생이 bastion 들어왔을 때 안내.
cat > /etc/motd <<'EOF'

╔══════════════════════════════════════════════════════╗
║  300B Bastion — 점프 호스트 (jumphost)                ║
║                                                       ║
║  내부 컨테이너 SSH 진입:                               ║
║    ssh attacker     # 공격자 컨테이너                   ║
║    ssh waf          # WAF (ModSecurity)                ║
║    ssh secu         # 보안 게이트웨이                   ║
║    ssh siem         # SIEM (rsyslog/CTI)               ║
║    ssh fw           # 엣지 방화벽                       ║
║    ssh ids          # IDS (Suricata)                   ║
║                                                       ║
║  Bastion API:                                         ║
║    curl localhost:8003/health                         ║
║                                                       ║
║  로그아웃: exit                                        ║
╚══════════════════════════════════════════════════════╝

EOF

# ─── bastion 코드 검증 ───────────────────────────
if [ ! -f /opt/app/apps/bastion/api.py ]; then
    echo "[bastion] 코드 누락 — 이미지 빌드 문제. sshd 만 띄우고 대기"
    exec /usr/sbin/sshd -D -e
fi

# .env 자동 생성.
mkdir -p /opt/app/apps/bastion
cat > /opt/app/apps/bastion/.env <<EOF
LLM_BASE_URL=${LLM_BASE_URL:-http://host.docker.internal:11434}
LLM_MANAGER_MODEL=${LLM_MANAGER_MODEL:-gpt-oss:120b}
LLM_SUBAGENT_MODEL=${LLM_SUBAGENT_MODEL:-gemma3:4b}
API_KEY=${API_KEY:-300b-api-key-2026}
JWT_SECRET=${JWT_SECRET:-300b-jwt-secret-2026}
EOF

# bastion 이 KG/evidence DB 를 찾을 위치를 환경변수로 명시.
export BASTION_GRAPH_DB="${BASTION_GRAPH_DB:-/opt/app/data/bastion_graph.db}"
export BASTION_PLAYBOOKS_DIR="${BASTION_PLAYBOOKS_DIR:-/opt/app/contents/playbooks}"
mkdir -p /opt/app/data /opt/app/contents/playbooks

# sshd 백그라운드, bastion API 포어그라운드.
/usr/sbin/sshd -e
echo "[bastion] uvicorn :8003"
cd /opt/app
exec python3 -m uvicorn apps.bastion.api:app --host 0.0.0.0 --port 8003
