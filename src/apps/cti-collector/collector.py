#!/usr/bin/env python3
"""CCC CTI Collector — NVD 최근 CVE를 SubAgent(gemma3:4b)로 요약·태깅·저장.

설계 (로드맵 P2):
- Master(Claude Code)는 콘텐츠 제작, Manager(gpt-oss:120b)는 운영, SubAgent(gemma3:4b)는 경량 병렬
- 이 모듈은 SubAgent가 담당: NVD JSON feed → 한글 요약 + 태그 + 과목 매핑
- Master가 이후 이 데이터로 battle 시나리오 생성 (P3)

실행:
    python3 -m apps.cti-collector.collector --hours 24 --limit 30
    python3 -m apps.cti-collector.collector --source nvd
    python3 -m apps.cti-collector.collector --digest           # Manager로 일일 다이제스트 생성

환경변수:
    LLM_BASE_URL        Ollama URL (default: http://192.168.0.105:11434)
    LLM_SUBAGENT_MODEL  default: gemma3:4b
    LLM_MANAGER_MODEL   default: gpt-oss:120b (digest 용)
    CTI_OUT_DIR         default: contents/threats/
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request
from typing import Any

OLLAMA_URL = os.getenv("LLM_BASE_URL", "http://192.168.0.105:11434")
SUB_MODEL = os.getenv("LLM_SUBAGENT_MODEL", "gemma3:4b")
MGR_MODEL = os.getenv("LLM_MANAGER_MODEL", "gpt-oss:120b")
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT_DIR = pathlib.Path(os.getenv("CTI_OUT_DIR", str(ROOT / "contents" / "threats")))
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 과목 매핑 키워드 (CVE description/keyword → 과목)
COURSE_KEYWORDS = {
    "C1 attack": ["scan", "enumeration", "exploit", "metasploit", "shell", "rce", "remote code"],
    "C3 web-vuln": ["web", "http", "xss", "sql injection", "csrf", "ssrf", "deserialization", "apache", "nginx", "tomcat", "php"],
    "C4 compliance": ["policy", "gdpr", "pci", "hipaa", "standard"],
    "C5 soc": ["detection", "siem", "alert", "log"],
    "C6 cloud-container": ["container", "docker", "kubernetes", "k8s", "cloud", "aws", "gcp", "azure"],
    "C7 ai-security": ["llm", "ai model", "prompt", "ml model", "training"],
    "C8 ai-safety": ["jailbreak", "bypass safety", "alignment", "harmful"],
    "C9 autonomous": ["agent", "autonomous", "rl", "reinforcement"],
    "C13 attack-adv": ["persistence", "lateral movement", "c2", "command and control", "apt"],
    "C16 physical": ["firmware", "iot", "rfid", "usb", "ics", "scada"],
    "C17 iot": ["iot", "embedded", "mqtt", "coap", "zigbee"],
    "C19 agent-ir": ["incident response", "forensics", "containment", "eradication"],
    "C20 agent-ir-adv": ["supply chain", "0day", "n-day", "hybrid phishing", "deepfake"],
}


# ── HTTP 헬퍼 ────────────────────────────────────────────

def _http_json(url: str, data: dict | None = None, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data else None,
        headers={"Content-Type": "application/json", "User-Agent": "ccc-cti/1.0"},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _ollama_chat(model: str, prompt: str, timeout: int = 30, temperature: float = 0.1) -> str:
    try:
        r = _http_json(f"{OLLAMA_URL}/api/chat", {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": 400},
        }, timeout=timeout)
        return (r.get("message") or {}).get("content", "").strip()
    except Exception as e:
        return f"[LLM 오류: {e}]"


# ── NVD 수집 ────────────────────────────────────────────

def fetch_nvd_recent(hours: int = 24, limit: int = 30) -> list[dict]:
    """NVD 2.0 API에서 최근 N시간 공개 CVE 가져오기.

    NVD JSON 스키마 2.0: https://services.nvd.nist.gov/rest/json/cves/2.0
    """
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(hours=hours)
    params = {
        "pubStartDate": start.strftime("%Y-%m-%dT%H:%M:%S.000"),
        "pubEndDate": end.strftime("%Y-%m-%dT%H:%M:%S.000"),
        "resultsPerPage": min(limit, 200),
    }
    url = "https://services.nvd.nist.gov/rest/json/cves/2.0?" + urllib.parse.urlencode(params)
    try:
        data = _http_json(url, timeout=45)
    except Exception as e:
        print(f"[NVD] 수집 실패: {e}", file=sys.stderr)
        return []
    out = []
    for v in data.get("vulnerabilities", [])[:limit]:
        c = v.get("cve", {})
        cve_id = c.get("id", "")
        descs = c.get("descriptions", [])
        desc_en = next((d["value"] for d in descs if d.get("lang") == "en"), "")
        metrics = c.get("metrics", {})
        cvss_v31 = ((metrics.get("cvssMetricV31") or [{}])[0].get("cvssData") or {})
        severity = cvss_v31.get("baseSeverity", "UNKNOWN")
        score = cvss_v31.get("baseScore", 0)
        refs = [r.get("url", "") for r in c.get("references", [])[:3]]
        out.append({
            "id": cve_id,
            "source": "NVD",
            "published": c.get("published", ""),
            "description_en": desc_en[:2000],
            "severity": severity,
            "cvss_score": score,
            "references": refs,
        })
    return out


# ── SubAgent 요약 ────────────────────────────────────────

def summarize_cve(cve: dict) -> dict:
    """SubAgent(gemma3:4b)가 CVE 한 건을 한글 요약·분류·태깅."""
    prompt = (
        "다음 CVE 정보를 한국어로 요약하라. JSON만 출력 (코드블록·주석 금지):\n\n"
        f"CVE: {cve['id']}\n"
        f"CVSS: {cve.get('severity','?')} ({cve.get('cvss_score','?')})\n"
        f"Description: {cve.get('description_en','')[:1200]}\n\n"
        '형식: {"summary": "2-3문장 한글 요약", '
        '"impact": "영향 받는 제품·버전 한 줄", '
        '"attack_vector": "공격 벡터 한 줄 (network/local/physical 등)", '
        '"tags": ["기술 태그 최대 5개"]}'
    )
    raw = _ollama_chat(SUB_MODEL, prompt, timeout=30)
    # JSON 추출 (LLM이 코드블록 씌우는 경우 대비)
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return {"summary": raw[:300], "impact": "", "attack_vector": "", "tags": []}
    try:
        parsed = json.loads(m.group(0))
    except Exception:
        return {"summary": raw[:300], "impact": "", "attack_vector": "", "tags": []}
    return {
        "summary": str(parsed.get("summary", ""))[:500],
        "impact": str(parsed.get("impact", ""))[:200],
        "attack_vector": str(parsed.get("attack_vector", ""))[:150],
        "tags": [str(t)[:40] for t in (parsed.get("tags") or [])[:5]],
    }


def map_to_courses(cve: dict, enriched: dict) -> list[str]:
    """키워드 기반 교과목 매핑. 중복 과목은 한 번만."""
    text = " ".join([
        cve.get("description_en", ""),
        enriched.get("summary", ""),
        enriched.get("impact", ""),
        enriched.get("attack_vector", ""),
        " ".join(enriched.get("tags", [])),
    ]).lower()
    matches = []
    for course, kws in COURSE_KEYWORDS.items():
        if any(kw in text for kw in kws):
            matches.append(course)
    return matches[:5]


# ── 저장 ────────────────────────────────────────────────

def save_threat(cve: dict, enriched: dict, courses: list[str]) -> pathlib.Path:
    day = cve.get("published", "")[:10] or dt.date.today().isoformat()
    day_dir = OUT_DIR / day
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{cve['id']}.json"
    doc = {**cve, **enriched, "courses": courses, "collected_at": dt.datetime.now().isoformat()}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ── Manager 일일 다이제스트 ──────────────────────────────

def make_digest(day: str | None = None) -> pathlib.Path:
    day = day or dt.date.today().isoformat()
    day_dir = OUT_DIR / day
    if not day_dir.exists():
        print(f"[digest] {day} 데이터 없음", file=sys.stderr)
        return day_dir / "digest.md"
    items = []
    for p in sorted(day_dir.glob("CVE-*.json")):
        try:
            items.append(json.loads(p.read_text()))
        except Exception:
            continue
    if not items:
        return day_dir / "digest.md"
    # severity 순 정렬 (CRITICAL > HIGH > MEDIUM > LOW)
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}
    items.sort(key=lambda x: (order.get(x.get("severity", "UNKNOWN"), 9), -float(x.get("cvss_score") or 0)))
    # 상위 5개로 Manager에게 narrative 요청
    top = items[:5]
    ctx = "\n\n".join([
        f"- {i['id']} [{i.get('severity','?')}/{i.get('cvss_score','?')}]: {i.get('summary','')} (과목: {', '.join(i.get('courses', []))})"
        for i in top
    ])
    prompt = (
        "다음은 오늘 발표된 상위 보안 취약점입니다. 한국어로 3-5개 문단의 다이제스트를 작성하라.\n"
        "구조: (1) 오늘의 헤드라인, (2) 주목 취약점 해설, (3) CCC 실습 과목 매핑 제안.\n\n"
        f"{ctx}"
    )
    narrative = _ollama_chat(MGR_MODEL, prompt, timeout=60, temperature=0.3)
    md = [
        f"# 위협 다이제스트 — {day}",
        "",
        f"> 수집: {len(items)}건 · SubAgent({SUB_MODEL}) 요약 · Manager({MGR_MODEL}) 다이제스트",
        "",
        "## 탑 5",
        "",
    ]
    for i in top:
        md.append(f"### {i['id']} · {i.get('severity','?')} ({i.get('cvss_score','?')})")
        md.append(f"- 요약: {i.get('summary','')}")
        md.append(f"- 영향: {i.get('impact','')}")
        md.append(f"- 벡터: {i.get('attack_vector','')}")
        md.append(f"- 태그: {', '.join(i.get('tags', []))}")
        md.append(f"- 관련 과목: {', '.join(i.get('courses', []) or ['(미매핑)'])}")
        md.append(f"- 참고: {' '.join(i.get('references', [])[:2])}")
        md.append("")
    md.append("## Manager 다이제스트")
    md.append("")
    md.append(narrative)
    out = day_dir / "digest.md"
    out.write_text("\n".join(md), encoding="utf-8")
    return out


# ── CLI ────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24, help="최근 N시간")
    ap.add_argument("--limit", type=int, default=30, help="최대 CVE 수")
    ap.add_argument("--digest", action="store_true", help="일일 다이제스트만 재생성 (Manager 사용)")
    ap.add_argument("--day", default=None, help="digest 대상 날짜 (YYYY-MM-DD)")
    args = ap.parse_args()

    if args.digest:
        out = make_digest(args.day)
        print(f"[digest] {out}")
        return

    print(f"[CTI] NVD 수집 중 (last {args.hours}h, max {args.limit})…")
    cves = fetch_nvd_recent(hours=args.hours, limit=args.limit)
    print(f"[CTI] {len(cves)}건 확보")
    for i, cve in enumerate(cves, 1):
        print(f"  [{i}/{len(cves)}] {cve['id']} {cve.get('severity','?')} ({cve.get('cvss_score','?')})", end=" ", flush=True)
        enriched = summarize_cve(cve)
        courses = map_to_courses(cve, enriched)
        path = save_threat(cve, enriched, courses)
        print(f"→ {path.name} · 과목:{','.join(courses) or '-'}")
    # 다이제스트도 이어서 생성
    if cves:
        out = make_digest()
        print(f"[digest] {out}")


if __name__ == "__main__":
    main()
