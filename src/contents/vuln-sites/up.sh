#!/usr/bin/env bash
# vuln-sites — 5 사이트 일괄 배포 + smoke PoC 자동 검증
# 사용: bash contents/vuln-sites/up.sh [up|down|restart|status|smoke]
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SITES=(neobank govportal mediforum adminconsole aicompanion)
PORTS=(3001 3002 3003 3004 3005)

NETWORK="300b-vuln"

ensure_network() {
    if ! docker network ls --format '{{.Name}}' | grep -qx "$NETWORK"; then
        echo "  → docker network create $NETWORK"
        docker network create "$NETWORK" >/dev/null
    fi
}

cmd_up() {
    ensure_network
    for s in "${SITES[@]}"; do
        echo "▶ $s"
        ( cd "$HERE/$s" && docker compose up -d --build 2>&1 | tail -3 )
    done
    echo
    cmd_status
}

cmd_down() {
    for s in "${SITES[@]}"; do
        echo "▶ stop $s"
        ( cd "$HERE/$s" && docker compose down 2>&1 | tail -2 )
    done
}

cmd_restart() {
    cmd_down
    cmd_up
}

cmd_status() {
    echo "─── 컨테이너 상태 ───"
    for s in "${SITES[@]}"; do
        st=$(docker inspect -f '{{.State.Status}}' "$s" 2>/dev/null || echo "missing")
        printf "  %-15s %s\n" "$s" "$st"
    done
}

cmd_smoke() {
    echo "─── 5 사이트 헬스 + 1-PoC 자동 검증 ───"
    declare -A POC_URL
    POC_URL[neobank]="http://localhost:3001/health"            # 기존 사이트 — /health
    POC_URL[govportal]="http://localhost:3002/health"          # 기존 사이트 — /health
    POC_URL[mediforum]="http://localhost:3003/_health"         # 신규 — /_health
    POC_URL[adminconsole]="http://localhost:3004/_health"
    POC_URL[aicompanion]="http://localhost:3005/_health"

    declare -A POC_GREP
    POC_GREP[neobank]='"NeoBank"'
    POC_GREP[govportal]='"status"'
    POC_GREP[mediforum]='"vulns":22'
    POC_GREP[adminconsole]='"vulns":28'
    POC_GREP[aicompanion]='"vulns":25'

    pass=0; fail=0
    for s in "${SITES[@]}"; do
        url="${POC_URL[$s]}"
        expect="${POC_GREP[$s]}"
        body=$(curl -s --max-time 5 "$url" 2>&1)
        if echo "$body" | grep -q "$expect"; then
            echo "  ✓ $s ($url) → $expect 매칭"
            pass=$((pass+1))
        else
            echo "  ✗ $s ($url) → 응답: ${body:0:80}"
            fail=$((fail+1))
        fi
    done
    echo
    echo "─── 1-PoC 취약점 검증 (대표 1개 / 사이트) ───"
    # NeoBank — index 페이지 banking 키워드 + /api/admin/users auth required (구조 검증)
    if curl -s --max-time 5 http://localhost:3001/ 2>/dev/null | grep -qi "neobank\|banking"; then
        echo "  ✓ neobank index 페이지 정상"; pass=$((pass+1))
    else
        echo "  ✗ neobank index 응답 이상"; fail=$((fail+1))
    fi
    # GovPortal index
    if curl -s --max-time 5 http://localhost:3002/ 2>/dev/null | grep -qi "민원\|gov\|portal"; then
        echo "  ✓ govportal index 페이지 정상"; pass=$((pass+1))
    else
        echo "  ✗ govportal index 응답 이상"; fail=$((fail+1))
    fi
    # MediForum V07 /api/users PII
    if curl -s --max-time 5 http://localhost:3003/api/users 2>/dev/null | grep -q '"ssn"'; then
        echo "  ✓ mediforum V07 PII (/api/users → ssn 노출)"; pass=$((pass+1))
    else
        echo "  ✗ mediforum V07 — /api/users 응답에 ssn 없음"; fail=$((fail+1))
    fi
    # AdminConsole V14 default admin/admin → V20 broken auth
    if curl -s --max-time 5 http://localhost:3004/api/users/list 2>/dev/null | grep -q '"api_token"'; then
        echo "  ✓ adminconsole V20 broken auth (/api/users/list → api_token 노출)"; pass=$((pass+1))
    else
        echo "  ✗ adminconsole V20 — /api/users/list 응답에 api_token 없음"; fail=$((fail+1))
    fi
    # AICompanion V05 system prompt leak
    if curl -s --max-time 5 http://localhost:3005/api/debug/prompt 2>/dev/null | grep -q "AICompanion"; then
        echo "  ✓ aicompanion V05 system prompt leak"; pass=$((pass+1))
    else
        echo "  ✗ aicompanion V05 — /api/debug/prompt 응답 미확인"; fail=$((fail+1))
    fi
    echo
    echo "──────────────────────────────────"
    echo "  종합: $pass pass / $fail fail"
    [ $fail -eq 0 ] && echo "  ✅ 모든 PoC 통과" || echo "  ⚠️ 일부 fail — 위 로그 확인"
}

case "${1:-up}" in
    up)      cmd_up ;;
    down)    cmd_down ;;
    restart) cmd_restart ;;
    status)  cmd_status ;;
    smoke)   cmd_smoke ;;
    *) echo "사용: $0 [up|down|restart|status|smoke]"; exit 1 ;;
esac
