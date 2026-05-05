#!/usr/bin/env python3
"""뉴스·커뮤니티 수집기 — CVE 외 보안 이슈.

특히 AI 에이전트 관련 공격/피격 사례 우선 처리.

소스 (RSS/Atom):
- The Hacker News: AI/malware/APT
- BleepingComputer: breaking security
- Dark Reading: enterprise security
- Krebs on Security: investigative
- Hacker News (API): community 화제
- Reddit r/netsec (RSS)

우선순위 boost 키워드:
- AI agent attack: "ai agent", "llm agent", "autonomous attack", "agent hijack",
  "prompt injection", "jailbreak", "rogue ai", "ai weaponization",
  "agentic malware", "llm worm", "multi-agent attack"
- AI being attacked: "model theft", "model extraction", "model poisoning",
  "backdoor attack", "llm supply chain", "prompt leak", "ai training data breach"

배포 이식성:
- RSS URL env override (`CTI_NEWS_FEEDS`)
- LLM URL·모델 기존 env 재사용
- stdlib xml.etree만 사용 (외부 의존성 없음)
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT_DIR = pathlib.Path(os.getenv("CTI_OUT_DIR", str(ROOT / "contents" / "threats")))
OLLAMA_URL = os.getenv("LLM_BASE_URL", "http://192.168.0.105:11434")
SUB_MODEL = os.getenv("LLM_SUBAGENT_MODEL", "gemma3:4b")
MGR_MODEL = os.getenv("LLM_MANAGER_MODEL", "gpt-oss:120b")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-7")

# RSS 기본 피드 (env CTI_NEWS_FEEDS로 JSON 배열 override 가능)
DEFAULT_FEEDS = [
    {"name": "The Hacker News", "url": "https://feeds.feedburner.com/TheHackersNews", "category": "general"},
    {"name": "BleepingComputer", "url": "https://www.bleepingcomputer.com/feed/", "category": "general"},
    {"name": "Dark Reading", "url": "https://www.darkreading.com/rss.xml", "category": "general"},
    {"name": "Krebs on Security", "url": "https://krebsonsecurity.com/feed/", "category": "general"},
    {"name": "SecurityWeek", "url": "https://www.securityweek.com/feed/", "category": "general"},
    # AI 보안 특화
    {"name": "Schneier", "url": "https://www.schneier.com/feed/atom/", "category": "analysis"},
]

_env_feeds = os.getenv("CTI_NEWS_FEEDS")
if _env_feeds:
    try:
        DEFAULT_FEEDS = json.loads(_env_feeds)
    except Exception:
        pass

# ── 키워드 분류 ─────────────────────────────────────────

AI_AGENT_ATTACK_KWS = [
    "ai agent", "llm agent", "autonomous attack", "agent hijack", "agent attack",
    "prompt injection", "agentic", "llm worm", "multi-agent", "rogue ai",
    "ai weaponization", "autonomous hacking", "llm exploit", "agent-based attack",
    "claude attack", "chatgpt exploit", "copilot exploit", "ai-powered attack",
    "ai agent 공격", "에이전트 공격", "ai 에이전트 악용",
]

AI_UNDER_ATTACK_KWS = [
    "model theft", "model extraction", "model inversion", "model poisoning",
    "backdoor attack", "llm supply chain", "prompt leak", "jailbreak",
    "training data breach", "indirect prompt injection", "rag poisoning",
    "tool poisoning", "ai model attack", "llm vulnerability",
    "모델 탈취", "ai 공격", "프롬프트 주입", "탈옥",
]

GENERIC_ATTACK_KWS = [
    "0day", "zero-day", "rce", "lateral movement", "ransomware", "apt",
    "supply chain", "phishing", "malware", "exploit", "c2", "command and control",
]


def classify(title: str, summary: str) -> tuple[str, int]:
    """Text 기반 분류. 반환: (category, priority 0-100)."""
    text = (title + " " + summary).lower()
    if any(kw in text for kw in AI_AGENT_ATTACK_KWS):
        return "ai_agent_attack", 100
    if any(kw in text for kw in AI_UNDER_ATTACK_KWS):
        return "ai_under_attack", 90
    if any(kw in text for kw in GENERIC_ATTACK_KWS):
        return "attack_technique", 60
    return "general", 30


# ── RSS 파서 ────────────────────────────────────────────

def _http_get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (ccc-cti-collector/1.0)"
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_feed(feed: dict) -> list[dict]:
    """RSS 2.0 또는 Atom 피드 파싱. 지난 7일 이내 항목만."""
    try:
        raw = _http_get(feed["url"])
    except Exception as e:
        print(f"[{feed['name']}] fetch 실패: {e}", file=sys.stderr)
        return []
    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"[{feed['name']}] XML 파싱 실패: {e}", file=sys.stderr)
        return []

    items: list[dict] = []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)

    # RSS 2.0: channel/item
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        pub_dt = _parse_date(pub)
        if pub_dt and pub_dt < cutoff:
            continue
        desc_clean = re.sub(r"<[^>]+>", " ", desc)[:800]
        items.append({
            "source": feed["name"],
            "title": title, "link": link,
            "summary_en": desc_clean,
            "published": pub_dt.isoformat() if pub_dt else pub,
        })
    # Atom: entry
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        link_el = entry.find("atom:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        summary = (entry.findtext("atom:summary", default="", namespaces=ns)
                   or entry.findtext("atom:content", default="", namespaces=ns) or "").strip()
        pub = (entry.findtext("atom:updated", default="", namespaces=ns)
               or entry.findtext("atom:published", default="", namespaces=ns) or "").strip()
        pub_dt = _parse_date(pub)
        if pub_dt and pub_dt < cutoff:
            continue
        summary_clean = re.sub(r"<[^>]+>", " ", summary)[:800]
        items.append({
            "source": feed["name"],
            "title": title, "link": link,
            "summary_en": summary_clean,
            "published": pub_dt.isoformat() if pub_dt else pub,
        })
    return items


def _parse_date(s: str) -> dt.datetime | None:
    if not s:
        return None
    # RSS: "Sun, 20 Apr 2025 12:34:56 +0000"
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            d = dt.datetime.strptime(s.replace("GMT", "+0000"), fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
            return d
        except Exception:
            continue
    return None


# ── Hacker News API ────────────────────────────────────

def fetch_hackernews_top(limit: int = 30) -> list[dict]:
    """HN top 30에서 보안 관련 제목만 필터링."""
    try:
        top_ids = json.loads(_http_get("https://hacker-news.firebaseio.com/v0/topstories.json").decode())[:limit]
    except Exception as e:
        print(f"[HN] top fetch 실패: {e}", file=sys.stderr)
        return []
    items = []
    for item_id in top_ids:
        try:
            d = json.loads(_http_get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json").decode())
        except Exception:
            continue
        title = d.get("title", "")
        text_low = title.lower()
        # 보안 관련만 필터
        if not any(k in text_low for k in ["security", "attack", "exploit", "hack", "vulnerability",
                                             "breach", "cve", "llm", "ai", "agent", "malware", "phish"]):
            continue
        items.append({
            "source": "Hacker News",
            "title": title,
            "link": d.get("url") or f"https://news.ycombinator.com/item?id={item_id}",
            "summary_en": (d.get("text") or "")[:500],
            "published": dt.datetime.fromtimestamp(d.get("time", 0), tz=dt.timezone.utc).isoformat(),
        })
    return items


# ── LLM ────────────────────────────────────────────────

def _chat(prompt: str, system: str = "", model: str = None, timeout: int = 60, json_mode: bool = True) -> str:
    model = model or SUB_MODEL
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = {"model": model, "messages": messages, "stream": False,
            "options": {"temperature": 0.1, "num_predict": 2000}}
    if json_mode:
        body["format"] = "json"
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/chat",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        return (d.get("message") or {}).get("content", "")
    except Exception as e:
        return ""


def _chat_master(prompt: str, system: str = "", timeout: int = 120) -> str:
    """고우선 항목용 — Anthropic Claude 우선, Ollama Manager fallback."""
    if ANTHROPIC_API_KEY:
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps({
                    "model": ANTHROPIC_MODEL, "max_tokens": 3000,
                    "messages": [{"role": "user", "content": prompt}],
                    "system": system or "",
                }).encode(),
                headers={"Content-Type": "application/json",
                         "x-api-key": ANTHROPIC_API_KEY,
                         "anthropic-version": "2023-06-01"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode())
            for b in d.get("content") or []:
                if b.get("type") == "text":
                    return b.get("text", "")
        except Exception:
            pass
    return _chat(prompt, system, model=MGR_MODEL, timeout=timeout, json_mode=False)


def summarize_item(item: dict) -> dict:
    """SubAgent 요약·태깅."""
    prompt = (
        "다음 보안 뉴스를 한국어로 요약·분류하라. JSON만:\n\n"
        f"제목: {item['title']}\n\n"
        f"원문 요약: {item.get('summary_en','')[:600]}\n\n"
        '형식: {"summary": "2-3문장 한글 요약", "tags": ["최대 5개"], '
        '"severity": "CRITICAL|HIGH|MEDIUM|LOW", "technique": "공격 기법 명칭"}'
    )
    raw = _chat(prompt, "너는 보안 뉴스 분석가다.", json_mode=True)
    try:
        m = re.search(r"\{[\s\S]*\}", raw)
        return json.loads(m.group(0)) if m else {}
    except Exception:
        return {}


DEEP_ANALYSIS_SYSTEM = """너는 AI 에이전트 보안 전문 분석가다.
주어진 뉴스/이슈에 대해 상세한 기술 분석을 한국어 markdown으로 작성한다.

## 구조
# 제목 (원 제목 한글화)

## 1. 이슈 개요
- 무엇이, 언제, 누가

## 2. 공격 원리 (상세)
- AI 에이전트가 어떻게 공격에 쓰였나 (또는 어떻게 공격당했나)
- 기술 스택, API 호출 흐름, 핵심 알고리즘
- 기존 공격과의 차이점

## 3. 재현/시연 가능성
- 학습용으로 어떤 부분을 재현 가능한지
- 위험 수준 (실전 적용 가능성)

## 4. 방어·탐지 방안
- 네트워크 레벨, 애플리케이션 레벨, 모델 레벨
- Suricata/Wazuh 등 기존 도구로 탐지 가능한가

## 5. CCC 교육 연계
- 관련 과목 (C1~C20) 매핑 제안
- 특강·실습 주제 아이디어

## 6. 추가 자료
- 원문 링크, 관련 CVE, 연구 논문

2000-3000자 분량. 기술적으로 구체적으로.
"""


def deep_analyze(item: dict) -> str:
    """Master(Claude/gpt-oss)가 상세 분석."""
    prompt = (
        f"## 뉴스\n제목: {item['title']}\n"
        f"출처: {item.get('source','')}\n"
        f"링크: {item.get('link','')}\n"
        f"발표: {item.get('published','')}\n"
        f"원문 요약: {item.get('summary_en','')}\n\n"
        f"이 이슈를 기술적으로 상세 분석한 markdown 교안을 작성하라."
    )
    return _chat_master(prompt, DEEP_ANALYSIS_SYSTEM, timeout=150)


# ── 저장 ────────────────────────────────────────────────

def save_news(item: dict, analysis: dict, deep_md: str = "") -> pathlib.Path:
    day = (item.get("published") or "")[:10] or dt.date.today().isoformat()
    # slug: 제목 해시 앞 8자 + 첫 단어
    slug = hashlib.sha1(item["title"].encode()).hexdigest()[:10]
    day_dir = OUT_DIR / day / "news"
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{slug}.json"
    doc = {**item, **analysis, "collected_at": dt.datetime.now().isoformat()}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    if deep_md:
        md_path = day_dir / f"{slug}.md"
        md_path.write_text(deep_md, encoding="utf-8")
        doc["deep_analysis_path"] = str(md_path.relative_to(OUT_DIR.parent))
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ── 파이프라인 ──────────────────────────────────────────

def collect_all(max_items: int = 50, deep_top: int = 5) -> dict:
    """전체 수집·분석 파이프라인.

    - 모든 피드 + HN에서 후보 수집
    - 중복 제거, 우선순위 분류
    - 상위 `deep_top`개 AI 에이전트 관련 이슈는 Master 상세 분석
    """
    all_items: list[dict] = []
    for feed in DEFAULT_FEEDS:
        all_items.extend(parse_feed(feed))
    all_items.extend(fetch_hackernews_top(limit=30))

    # 중복 제거 (link 기준)
    seen = set()
    dedup = []
    for it in all_items:
        key = it.get("link") or it.get("title", "")
        if key in seen:
            continue
        seen.add(key)
        dedup.append(it)

    # 분류 + 우선순위
    for it in dedup:
        cat, pri = classify(it["title"], it.get("summary_en", ""))
        it["category"] = cat
        it["priority"] = pri

    # 우선순위 정렬
    dedup.sort(key=lambda x: -x["priority"])
    dedup = dedup[:max_items]

    print(f"[news] 수집 {len(dedup)}건 (상위 {deep_top} 상세분석)")

    deep_count = 0
    saved: list[pathlib.Path] = []
    for i, it in enumerate(dedup):
        analysis = summarize_item(it)
        deep_md = ""
        # 상위 deep_top개 중 AI 에이전트 관련만 상세 분석
        if deep_count < deep_top and it["category"] in ("ai_agent_attack", "ai_under_attack"):
            print(f"  [{i+1}/{len(dedup)}] (deep) {it['title'][:70]}", flush=True)
            deep_md = deep_analyze(it)
            deep_count += 1
        else:
            print(f"  [{i+1}/{len(dedup)}] {it['category']}/{it['priority']} {it['title'][:60]}", flush=True)
        saved.append(save_news(it, analysis, deep_md))

    return {
        "total": len(dedup),
        "deep_analyzed": deep_count,
        "by_category": {c: sum(1 for x in dedup if x["category"] == c)
                        for c in ["ai_agent_attack", "ai_under_attack", "attack_technique", "general"]},
        "files": len(saved),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=50, help="최대 수집 건수")
    ap.add_argument("--deep", type=int, default=5, help="상세 분석 상위 N건 (AI 에이전트 관련만)")
    args = ap.parse_args()
    result = collect_all(max_items=args.max, deep_top=args.deep)
    print(f"\n결과: {result}")


if __name__ == "__main__":
    main()
