"""Bastion 프롬프트 엔진 — 목적별 분리된 시스템 프롬프트

PLANNING 단계에서 두 가지 프롬프트를 순서대로 사용:
  1. build_planning_prompt() — Skill 선택용 (Tool Calling 또는 JSON fallback)
  2. build_system_prompt()   — 일반 컨텍스트 (Q&A 및 결과 분석용)
"""
from __future__ import annotations
import os

from packages.bastion.skills import SKILLS
from packages.bastion.playbook import list_playbooks


def build_planning_prompt(vm_ips: dict[str, str] = None,
                          rag_context: str = "",
                          prev_context: str = "",
                          learned_context: str = "") -> str:
    """Skill 선택 전용 프롬프트 — 간결하고 명확한 지시만 포함.

    Tool Calling 모드: 모델이 tool_calls 필드로 응답.
    JSON fallback 모드: {"skill": "...", "params": {...}} 형식으로 응답.
    """
    sections = []

    # Skill 매핑 정보를 프롬프트에 포함 (모델이 skill 선택할 수 있도록)
    skill_map = "\n".join(
        f"  - {name}: {s['description']} (target: {s.get('target_vm','auto')})"
        for name, s in SKILLS.items()
    )
    sections.append(
        "너는 Bastion 보안 운영 에이전트다.\n"
        "사용자 요청을 분석하고 적절한 Skill을 선택해 실행한다.\n\n"
        "## 분류 원칙 — 실행(Execute) vs 답변(Answer)\n\n"
        "다음 기준으로 요청을 분류한다:\n\n"
        "**실행 (Skill 사용)** — 인프라에 변화를 주거나 상태를 조회하는 모든 작업:\n"
        "  • 시스템 상태 조회, 서비스 확인, 파일 읽기, 로그 검색\n"
        "  • 설정 변경, 룰 추가/삭제, 서비스 재시작\n"
        "  • 네트워크 스캔, 취약점 테스트, 공격 시뮬레이션\n"
        "  • 명령어(curl, nmap, grep 등)가 포함된 요청\n"
        "  • 동사가 실행 의미('확인', '설정', '스캔', '시도', '추가', '삭제', '조회',\n"
        "    '공격', '삽입', '우회', '추출', '전송', '생성', '점검' 등)인 요청\n\n"
        "**답변 (도구 없이 직접 응답)** — 순수 지식/개념 질문에 한정:\n"
        "  • 정의, 원리, 이론, 비교, 역사, 트렌드 설명\n"
        "  • 예시 코드/구조 작성 (인프라 실행 불필요)\n"
        "  • 정책/아키텍처/프레임워크 설계 문서 작성\n\n"
        "**판단 기준**: 요청을 수행하려면 실제 서버에 접속해야 하는가?\n"
        "  예 → Skill 사용. 아니오 → 직접 답변.\n"
        "  애매하면 Skill 사용 (실행이 우선).\n\n"
        f"## 사용 가능한 Skill\n{skill_map}\n\n"
        "## VM 추론\n"
        "대상 VM이 명시되지 않으면 요청 내용의 키워드로 추론:\n"
        "  - 공격 도구(nmap/hydra/curl/nikto/sqlmap) → attacker\n"
        "  - 방화벽/IPS(nftables/suricata/IDS) → secu\n"
        "  - 웹(apache/modsecurity/docker/JuiceShop) → web\n"
        "  - SIEM/로그(wazuh/alerts/알림/에이전트) → siem\n"
        "  - LLM/AI(ollama/python3/스크립트) → manager\n"
        "  - 명시적 IP가 있으면 그 IP의 VM을 선택\n"
    )

    # VM 인프라 정보 — 역할 + 설치된 서비스 + 주요 파일 경로
    if vm_ips:
        infra_detail = (
            "## 현재 인프라 상세\n"
            f"  attacker ({vm_ips.get('attacker','?')}): 공격 도구 — nmap, hydra, nikto, sqlmap, curl, dirb\n"
            f"  secu ({vm_ips.get('secu','?')}): 방화벽+IPS — nftables, Suricata\n"
            f"    - 설정: /etc/suricata/suricata.yaml\n"
            f"    - 커스텀 룰: /etc/suricata/rules/local.rules\n"
            f"    - 로그: /var/log/suricata/eve.json, fast.log, stats.log\n"
            f"  web ({vm_ips.get('web','?')}): 웹서버+WAF — Apache, ModSecurity CRS, JuiceShop(:3000), Docker\n"
            f"    - ModSec 설정: /etc/modsecurity/modsecurity.conf\n"
            f"    - 감사 로그: /var/log/apache2/modsec_audit.log\n"
            f"  siem ({vm_ips.get('siem','?')}): SIEM+CTI — Wazuh Manager, Dashboard(:443), OpenCTI(:8080), Docker\n"
            f"    - 설정: /var/ossec/etc/ossec.conf\n"
            f"    - 커스텀 룰: /var/ossec/etc/rules/local_rules.xml\n"
            f"    - 알림: /var/ossec/logs/alerts/alerts.json\n"
            f"    - API: https://localhost:55000 (wazuh-wui/wazuh-wui)\n"
            f"  manager ({vm_ips.get('manager','?')}): Bastion 자체 — Ollama 프록시, Python3\n"
        )
        sections.append(infra_detail)

    # 이전 실행 컨텍스트
    if prev_context:
        sections.append(prev_context)

    # 학습된 경험 (experience learning)
    if learned_context:
        sections.append(learned_context)

    # RAG 컨텍스트
    if rag_context:
        sections.append(rag_context)

    return "\n\n".join(sections)


def build_system_prompt(vm_ips: dict[str, str] = None,
                        student_info: dict = None,
                        extra_context: str = "") -> str:
    """범용 시스템 프롬프트 — Q&A·결과 분석용."""
    sections = []

    sections.append(
        "너는 CCC Bastion 보안 운영 에이전트다.\n"
        "학생의 사이버보안 인프라에서 보안 운영, 모니터링, 인시던트 대응을 수행한다.\n"
        "항상 한국어로 답변하며 결과는 간결하게 요약한다."
    )

    # Skill 목록
    skill_lines = "\n".join(
        f"  {name}: {s['description']}"
        for name, s in SKILLS.items()
    )
    sections.append(f"사용 가능한 Skill:\n{skill_lines}")

    # Playbook 목록
    playbooks = list_playbooks()
    if playbooks:
        pb_lines = "\n".join(
            f"  {p['playbook_id']}: {p['title']} ({p['steps']}단계)"
            for p in playbooks
        )
        sections.append(f"등록된 Playbook (우선 적용):\n{pb_lines}")

    # VM 인프라
    if vm_ips:
        vm_lines = "\n".join(f"  {role}: {ip}" for role, ip in vm_ips.items())
        sections.append(f"현재 인프라:\n{vm_lines}")

    # 학생 컨텍스트
    if student_info:
        sections.append(
            f"사용자: {student_info.get('name', '?')} "
            f"(rank: {student_info.get('rank', 'rookie')}, "
            f"blocks: {student_info.get('total_blocks', 0)})"
        )

    # CCC.md 운영 지침
    ccc_md = os.path.join(os.path.dirname(__file__), "..", "..", "CCC.md")
    if os.path.exists(ccc_md):
        try:
            with open(ccc_md, encoding="utf-8") as f:
                content = f.read()[:2000]
            if content:
                sections.append(f"[운영 지침]\n{content}")
        except Exception:
            pass

    # 추가 컨텍스트
    if extra_context:
        sections.append(f"[추가 컨텍스트]\n{extra_context}")

    return "\n\n".join(sections)
