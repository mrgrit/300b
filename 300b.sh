#!/usr/bin/env bash
# =========================================================
# 300B 실습 환경 — 학생 1인용 단일 VM 자동 구축 스크립트
# =========================================================
# 사용법 (Ubuntu 22.04 server VM 안에서):
#     git clone <ccc-repo> && cd ccc/standalone
#     bash 300b.sh up         # 빌드 + 기동
#     bash 300b.sh down       # 정지
#     bash 300b.sh status     # 상태
#     bash 300b.sh logs <svc> # 로그
#     bash 300b.sh smoke      # 헬스체크
#
# 전제: Bridge 네트워크 1개로 VMware 설정 (Windows 호스트와 같은 LAN).
# 외부 LLM (Ollama) 주소는 .env 의 LLM_BASE_URL 로 지정.
# ---------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { printf "${GREEN}[300b]${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}[300b]${NC} %s\n" "$*"; }
err()  { printf "${RED}[300b]${NC} %s\n" "$*" >&2; }

ensure_env() {
    if [ ! -f "$HERE/.env" ]; then
        log ".env 가 없어서 .env.example 을 복사합니다 — 외부 LLM 주소만 확인하세요."
        cp "$HERE/.env.example" "$HERE/.env"
    fi
    set -a; . "$HERE/.env"; set +a
}

ensure_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        log "Docker 미설치 — 설치를 진행합니다 (sudo 필요)."
        sudo apt-get update
        sudo apt-get install -y ca-certificates curl gnupg lsb-release
        sudo install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
            sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        sudo chmod a+r /etc/apt/keyrings/docker.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
              https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
            sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
        sudo apt-get update
        sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
                                docker-buildx-plugin docker-compose-plugin
        sudo usermod -aG docker "$USER" || true
        warn "현재 셸에서는 docker 그룹이 적용되지 않을 수 있습니다 — newgrp docker 후 재실행."
    fi
    if ! docker info >/dev/null 2>&1; then
        err "docker daemon 에 접근할 수 없습니다. 'sudo systemctl start docker' 또는 newgrp docker 후 재실행."
        exit 1
    fi
}

ensure_vmax_map_count() {
    # Wazuh indexer 가 OpenSearch 기반 — vm.max_map_count >= 262144 요구.
    cur="$(sysctl -n vm.max_map_count 2>/dev/null || echo 0)"
    if [ "$cur" -lt 262144 ]; then
        log "vm.max_map_count=$cur → 262144 로 상향 (Wazuh indexer 용)."
        if sudo -n sysctl -w vm.max_map_count=262144 >/dev/null 2>&1; then
            echo 'vm.max_map_count=262144' | sudo -n tee /etc/sysctl.d/99-300b.conf >/dev/null
        else
            warn "sudo 패스워드가 필요합니다. 별도 터미널에서 한 번만 실행하세요:"
            warn "  sudo sysctl -w vm.max_map_count=262144"
            warn "  echo 'vm.max_map_count=262144' | sudo tee /etc/sysctl.d/99-300b.conf"
            warn "→ 그 후 'bash 300b.sh up' 재실행. Wazuh 미사용이면 무시 가능."
        fi
    fi
}

ensure_wazuh_certs() {
    # Wazuh single-node 4.10 — 첫 1회 SSL cert 생성. 결과는 wazuh-certs/certs/ 에 저장.
    # docker compose 가 host path 가 없을 때 빈 디렉토리로 자동 mount 하는 함정 회피용으로
    # 핵심 파일 9개를 모두 검증한다.
    local missing=0
    for f in root-ca.pem root-ca.key root-ca-manager.pem admin.pem admin-key.pem \
             wazuh.indexer.pem wazuh.indexer-key.pem \
             wazuh.manager.pem wazuh.manager-key.pem \
             wazuh.dashboard.pem wazuh.dashboard-key.pem; do
        [ ! -f "$HERE/wazuh-certs/certs/$f" ] && missing=1
    done
    if [ "$missing" = "1" ]; then
        log "Wazuh SSL 인증서 생성 (wazuh-certs-generator)"
        # docker 가 자동 생성한 빈 디렉토리들이 있으면 정리 후 재생성.
        find "$HERE/wazuh-certs/certs" -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} + 2>/dev/null || true
        ( cd "$HERE/wazuh-certs" && docker compose -f generate.yaml run --rm generator )
    fi
    # cert generator 가 일부 파일을 root:docker 0400 으로 만드므로 alpine 으로 권한 정리.
    log "Wazuh cert 권한 정리"
    docker run --rm -v "$HERE/wazuh-certs/certs:/c" alpine sh -c 'chmod 755 /c && chmod 644 /c/*' >/dev/null
}

cmd_up() {
    ensure_env
    ensure_docker
    ensure_vmax_map_count
    ensure_wazuh_certs
    log "docker compose build (첫 실행 10~15 분, attacker msf 포함)"
    docker compose build
    log "docker compose up -d"
    docker compose up -d
    log "기동 완료. 1 분 대기 후 smoke 테스트 권장 → bash $0 smoke"
    cmd_status
}

cmd_down() {
    ensure_env
    docker compose down
}

cmd_destroy() {
    ensure_env
    warn "모든 컨테이너 + 볼륨 + 이미지 삭제 — 5 초 후 진행 (Ctrl-C 로 취소)"
    sleep 5
    docker compose down -v --rmi local
}

cmd_status() {
    ensure_env
    echo "─── 컨테이너 상태 ───"
    docker compose ps --format 'table {{.Name}}\t{{.Service}}\t{{.Status}}\t{{.Ports}}'
    echo
    VMIP="$(hostname -I | awk '{print $1}')"
    cat <<EOF
─── 외부 접속 정보 (Windows → VM IP: ${VMIP}) ───
SSH (bastion 만 노출 — ProxyJump 모델):
  ssh ${SSH_USER:-ccc}@${VMIP} -p ${SSH_PORT_BASTION:-2204}     # bastion 점프 호스트

  내부 컨테이너 (bastion 경유):
    학생 PC ~/.ssh/config 에 다음 한 번 추가:
      Host 300b-bastion
        HostName ${VMIP}
        Port ${SSH_PORT_BASTION:-2204}
        User ccc
      Host 300b-*
        ProxyJump 300b-bastion
        User ccc
    그 후:
      ssh 300b-attacker / 300b-waf / 300b-secu / 300b-siem / 300b-fw / 300b-ids

웹/대시보드 (모두 fw → waf 경유):
  http://${VMIP}/                  Landing 페이지 (안내)
  http://juice.300b/               Juice Shop      (학생 PC /etc/hosts 또는 DNS 설정 후)
  http://dvwa.300b/                DVWA
  http://neobank.300b/             NeoBank
  http://govportal.300b/           GovPortal
  http://mediforum.300b/           MediForum
  http://admin.300b/               AdminConsole
  http://ai.300b/                  AICompanion
  http://wazuh.300b/               Wazuh Dashboard (admin / SecretPassword)
  http://bastion.300b/health       Bastion API

학생 PC /etc/hosts 추가 (한 번):
  ${VMIP} juice.300b dvwa.300b neobank.300b govportal.300b mediforum.300b admin.300b ai.300b wazuh.300b bastion.300b
EOF
}

cmd_logs() {
    ensure_env
    docker compose logs -f --tail=200 "${1:-}"
}

cmd_smoke() {
    ensure_env
    pass=0; fail=0
    # HTTP 200/302 응답이면 통과 — 학습 환경이라 컨텐츠 검증보다 가용성 우선.
    check() {
        local name="$1" url="$2" expect_codes="${3:-200|301|302}"
        local code
        code="$(curl -sk --max-time 8 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo 000)"
        if echo "$code" | grep -qE "$expect_codes"; then
            printf "  ${GREEN}✓${NC} %-22s %s  (HTTP %s)\n" "$name" "$url" "$code"; pass=$((pass+1))
        else
            printf "  ${RED}✗${NC} %-22s %s  (HTTP %s)\n" "$name" "$url" "$code"; fail=$((fail+1))
        fi
    }
    echo "─── HTTP 헬스 (모든 트래픽 fw → waf 통과) ───"
    HTTP_PORT="${PORT_HTTP:-80}"
    PROXY="http://localhost:${HTTP_PORT}"
    check_host() {
        local name="$1" host="$2" path="${3:-/}" expect="${4:-200|301|302}"
        local code
        code="$(curl -sk --max-time 8 -H "Host: ${host}" -o /dev/null -w '%{http_code}' "${PROXY}${path}" 2>/dev/null || echo 000)"
        if echo "$code" | grep -qE "$expect"; then
            printf "  ${GREEN}✓${NC} %-22s Host:%-22s %s  (HTTP %s)\n" "$name" "$host" "$path" "$code"; pass=$((pass+1))
        else
            printf "  ${RED}✗${NC} %-22s Host:%-22s %s  (HTTP %s)\n" "$name" "$host" "$path" "$code"; fail=$((fail+1))
        fi
    }
    check_host "landing"          "localhost"        "/"
    check_host "juice"            "juice.300b"       "/"
    check_host "dvwa"             "dvwa.300b"        "/"
    check_host "neobank"          "neobank.300b"     "/"
    check_host "govportal"        "govportal.300b"   "/"
    check_host "mediforum"        "mediforum.300b"   "/"
    check_host "admin"            "admin.300b"       "/"
    check_host "ai"               "ai.300b"          "/"
    check_host "wazuh dashboard"  "wazuh.300b"       "/"   "200|301|302|503"
    check_host "bastion API"      "bastion.300b"     "/health"

    echo
    echo "─── SSH 헬스 (bastion 만 외부 노출) ───"
    port="${SSH_PORT_BASTION:-2204}"
    banner="$(timeout 3 bash -c "exec 3<>/dev/tcp/localhost/$port && head -c 40 <&3" 2>/dev/null || true)"
    if echo "$banner" | grep -qi "ssh"; then
        printf "  ${GREEN}✓${NC} %-22s tcp/%s  %s\n" "bastion" "$port" "${banner//$'\n'/ }"; pass=$((pass+1))
    else
        printf "  ${RED}✗${NC} %-22s tcp/%s  banner=%s\n" "bastion" "$port" "${banner:-(empty)}"; fail=$((fail+1))
    fi

    echo
    echo "─── 격리 검증 (직접 접근 차단되어야 함) ───"
    # 이전 모델에서 노출했던 포트들이 이제 차단되어야 함.
    deny_check() {
        local name="$1" port="$2"
        local code
        code="$(curl -s --max-time 3 -o /dev/null -w '%{http_code}' "http://localhost:${port}/" 2>/dev/null || echo 000)"
        if [ "$code" = "000" ]; then
            printf "  ${GREEN}✓${NC} %-22s :%s  refused (격리 OK)\n" "$name" "$port"; pass=$((pass+1))
        else
            printf "  ${RED}✗${NC} %-22s :%s  HTTP %s — 직접 노출됨!\n" "$name" "$port" "$code"; fail=$((fail+1))
        fi
    }
    deny_check "juiceshop direct"  "3000"
    deny_check "dvwa direct"       "8080"
    deny_check "neobank direct"    "3001"
    echo
    echo "  종합: $pass pass / $fail fail"
    [ $fail -eq 0 ] && echo "  ✅ 전부 통과" || echo "  ⚠️ 일부 fail — bash $0 logs <svc> 로 확인"
}

case "${1:-up}" in
    up)      cmd_up ;;
    down)    cmd_down ;;
    destroy) cmd_destroy ;;
    status)  cmd_status ;;
    logs)    shift; cmd_logs "$@" ;;
    smoke)   cmd_smoke ;;
    *)       echo "사용: $0 [up|down|destroy|status|logs <svc>|smoke]"; exit 1 ;;
esac
