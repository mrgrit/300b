#!/usr/bin/env bash
set -euo pipefail

/usr/local/bin/sshd_setup.sh

# bastion 코드는 컨테이너 빌드 시점에 복사됨 (/opt/app/apps/bastion/api.py).
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

# bastion 이 KG/evidence DB 를 찾을 위치를 환경변수로 명시 (컨테이너 내부 영구 경로).
export BASTION_GRAPH_DB="${BASTION_GRAPH_DB:-/opt/app/data/bastion_graph.db}"
export BASTION_PLAYBOOKS_DIR="${BASTION_PLAYBOOKS_DIR:-/opt/app/contents/playbooks}"
mkdir -p /opt/app/data /opt/app/contents/playbooks

# sshd 백그라운드, bastion API 포어그라운드.
/usr/sbin/sshd -e
echo "[bastion] uvicorn :8003"
cd /opt/app
exec python3 -m uvicorn apps.bastion.api:app --host 0.0.0.0 --port 8003
