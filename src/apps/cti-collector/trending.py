#!/usr/bin/env python3
"""지속 화제 토픽 감지 → 누적 심층 분석 '특집' 생성.

로직:
1. 최근 N일간 수집된 news/*.json 전부 로드
2. 태그·키워드 기반 클러스터링 (공통 토픽 식별)
3. 3일+ 반복 등장 AND 5건+ 기사 AND priority 60+ 인 토픽 = trending
4. Master(Claude/gpt-oss)가 누적 분석 (역사·진화·현재·대응) markdown 생성
5. 저장: contents/threats/trending/<topic-slug>/
    - analysis.md (상세 분석)
    - sources.json (관련 기사 목록)
    - updated (최종 갱신 시각)

출력은 Admin UI의 새 섹션 "Featured" 에 노출.

배포 이식성: 기존 env 재사용, stdlib만.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT_DIR = pathlib.Path(os.getenv("CTI_OUT_DIR", str(ROOT / "contents" / "threats")))
TRENDING_DIR = OUT_DIR / "trending"
TRENDING_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = os.getenv("LLM_BASE_URL", "http://192.168.0.105:11434")
MGR_MODEL = os.getenv("LLM_MANAGER_MODEL", "gpt-oss:120b")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-7")


# ── LLM ────────────────────────────────────────────────

def _chat_master(prompt: str, system: str = "", timeout: int = 150) -> str:
    """Master Agent 호출 — 상세 분석용."""
    if ANTHROPIC_API_KEY:
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps({
                    "model": ANTHROPIC_MODEL, "max_tokens": 4000,
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
        except Exception as e:
            print(f"[master anthropic 실패: {e}]", file=sys.stderr)
    # Ollama fallback
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/chat",
            data=json.dumps({
                "model": MGR_MODEL,
                "messages": ([{"role": "system", "content": system}] if system else []) +
                            [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 4000},
            }).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        return (d.get("message") or {}).get("content", "")
    except Exception as e:
        return f"[ollama 실패: {e}]"


# ── 수집된 뉴스 로드 ────────────────────────────────────

def load_recent_news(days: int = 14) -> list[dict]:
    """최근 N일 news 모두 로드."""
    cutoff = dt.date.today() - dt.timedelta(days=days)
    items = []
    for day_dir in OUT_DIR.iterdir():
        if not day_dir.is_dir():
            continue
        # day_dir name이 YYYY-MM-DD 형식인지
        if not re.match(r"\d{4}-\d{2}-\d{2}$", day_dir.name):
            continue
        try:
            day = dt.date.fromisoformat(day_dir.name)
        except Exception:
            continue
        if day < cutoff:
            continue
        news_dir = day_dir / "news"
        if not news_dir.exists():
            continue
        for p in news_dir.glob("*.json"):
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
                doc["_path"] = str(p.relative_to(OUT_DIR.parent))
                doc["_day"] = day_dir.name
                items.append(doc)
            except Exception:
                continue
    return items


# ── 토픽 클러스터링 ─────────────────────────────────────

# 토픽 키워드 후보 — 정규화된 형태 (소문자, 공백 없음)
_TOPIC_KEYWORDS = {
    # AI 에이전트 공격
    "prompt_injection": ["prompt injection", "indirect prompt", "프롬프트 주입"],
    "llm_jailbreak": ["jailbreak", "탈옥", "jailbreaking"],
    "agent_hijack": ["agent hijack", "agentic malware", "rogue ai", "rogue agent"],
    "model_extraction": ["model extraction", "model theft", "모델 탈취"],
    "rag_poisoning": ["rag poisoning", "vector store attack", "retrieval attack"],
    "llm_worm": ["llm worm", "multi-agent", "worm ai"],
    # 전통 공격
    "ransomware": ["ransomware", "랜섬웨어"],
    "apt": ["apt", "advanced persistent"],
    "supply_chain": ["supply chain", "공급망"],
    "zero_day": ["0day", "zero-day", "zero day"],
    # 플랫폼·제품
    "wordpress": ["wordpress", "wp-content", "워드프레스"],
    "kubernetes": ["kubernetes", "k8s"],
    "apache": ["apache"],
    "openai_related": ["openai", "chatgpt", "gpt-4", "gpt-5"],
    "anthropic_related": ["anthropic", "claude"],
}


def cluster_topics(items: list[dict]) -> dict:
    """각 기사에 매칭되는 토픽 키 찾기. topic → list[item]."""
    clusters: dict[str, list[dict]] = collections.defaultdict(list)
    for it in items:
        text = " ".join([
            str(it.get("title", "")),
            str(it.get("summary", "")),
            str(it.get("summary_en", "")),
            str(it.get("technique", "")),
            " ".join(it.get("tags") or []),
        ]).lower()
        matched = False
        for topic, kws in _TOPIC_KEYWORDS.items():
            if any(kw.lower() in text for kw in kws):
                clusters[topic].append(it)
                matched = True
        # 매칭 안 된 항목도 'other'에 (통계용)
        if not matched:
            clusters["_other"].append(it)
    return dict(clusters)


def find_trending(clusters: dict, min_days: int = 3, min_articles: int = 5) -> list[dict]:
    """N일 이상, M건 이상 조건 만족하는 토픽 식별."""
    trending = []
    for topic, items in clusters.items():
        if topic == "_other":
            continue
        if len(items) < min_articles:
            continue
        days = {it["_day"] for it in items}
        if len(days) < min_days:
            continue
        # 평균 우선순위
        avg_pri = sum(it.get("priority", 0) for it in items) / len(items)
        trending.append({
            "topic": topic,
            "article_count": len(items),
            "day_span": len(days),
            "first_seen": min(days),
            "last_seen": max(days),
            "avg_priority": round(avg_pri, 1),
            "articles": items,
        })
    # 우선순위 + 기간 기준 정렬
    trending.sort(key=lambda t: (-t["avg_priority"], -t["day_span"], -t["article_count"]))
    return trending


# ── 특집 생성 ──────────────────────────────────────────

FEATURE_SYSTEM = """너는 CCC 교육 플랫폼의 '최신 보안 특집' 편집자다.
최근 N일간 여러 기사에서 반복된 보안 토픽에 대해 누적 분석 markdown을 작성한다.

## 구조
# 특집: <토픽 이름>

## 1. 왜 지금 주목해야 하나
- 최근 N일간 몇 건의 기사가 나왔는지
- 왜 이 시점에 집중되는지

## 2. 토픽 개요 (배경 + 역사)
- 기본 개념
- 초기 사례와 진화

## 3. 최근 사례 분석
- 기사별 핵심 요약 (가장 중요한 3-5건)
- 공격 방법·도구 패턴

## 4. 기술적 심층 분석
- 공격 원리 상세
- AI 에이전트와의 연관성
- 기존 공격과 차이

## 5. 방어·탐지
- 네트워크·애플리케이션·모델 레벨 방어
- CCC Bastion으로 대응 가능한 범위

## 6. CCC 교육 연계
- 관련 과목 매핑 (C1-C20)
- 특강·실습·battle 아이디어

## 7. 추가 리소스
- 원본 기사 링크, 관련 CVE, 도구

3000-4500자 분량. 학생(대학 학부~석사)이 읽고 이해 가능한 수준.
"""


def generate_feature(trend: dict) -> str:
    topic = trend["topic"]
    articles = trend["articles"][:15]  # 최대 15건 컨텍스트로
    ctx_list = []
    for a in articles:
        ctx_list.append(
            f"- [{a.get('_day','?')}] {a.get('title','')} (출처: {a.get('source','')}, "
            f"우선순위 {a.get('priority','?')})\n  요약: {a.get('summary','')[:200]}\n  원문: {a.get('link','')}"
        )
    ctx = "\n".join(ctx_list)
    prompt = (
        f"## 토픽: {topic}\n"
        f"- 기간: {trend['first_seen']} ~ {trend['last_seen']} ({trend['day_span']}일)\n"
        f"- 기사 수: {trend['article_count']}건\n"
        f"- 평균 우선순위: {trend['avg_priority']}\n\n"
        f"## 관련 기사\n{ctx}\n\n"
        f"위 자료를 종합한 '특집' markdown을 작성하라."
    )
    return _chat_master(prompt, FEATURE_SYSTEM, timeout=180)


def save_feature(trend: dict, md: str) -> pathlib.Path:
    topic_dir = TRENDING_DIR / trend["topic"]
    topic_dir.mkdir(parents=True, exist_ok=True)
    (topic_dir / "analysis.md").write_text(md, encoding="utf-8")
    # sources.json
    sources = [{k: v for k, v in a.items() if k not in ("summary_en",)} for a in trend["articles"][:20]]
    (topic_dir / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    # meta
    meta = {k: v for k, v in trend.items() if k != "articles"}
    meta["updated"] = dt.datetime.now().isoformat()
    (topic_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return topic_dir


# ── 파이프라인 ──────────────────────────────────────────

def run(days: int = 14, min_days: int = 3, min_articles: int = 5) -> dict:
    items = load_recent_news(days=days)
    if not items:
        return {"error": f"최근 {days}일 수집된 news 없음 — 먼저 news_collector 실행"}
    clusters = cluster_topics(items)
    trending = find_trending(clusters, min_days=min_days, min_articles=min_articles)
    if not trending:
        return {
            "total_items": len(items),
            "trending_count": 0,
            "note": f"기준 미달 (최소 {min_days}일 · {min_articles}건). 현재 큰 클러스터: "
                    + ", ".join(f"{k}({len(v)})" for k, v in list(sorted(clusters.items(), key=lambda x: -len(x[1])))[:5]),
        }
    results = []
    for trend in trending[:10]:  # 상위 10개까지
        md = generate_feature(trend)
        if md and not md.startswith("[ollama 실패"):
            path = save_feature(trend, md)
            results.append({"topic": trend["topic"], "path": str(path.relative_to(ROOT)),
                           "article_count": trend["article_count"], "day_span": trend["day_span"]})
            print(f"  feature: {trend['topic']} ({trend['article_count']}건, {trend['day_span']}일) → {path.name}", flush=True)
    return {"total_items": len(items), "trending_count": len(results), "features": results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--min-days", type=int, default=3)
    ap.add_argument("--min-articles", type=int, default=5)
    args = ap.parse_args()
    result = run(days=args.days, min_days=args.min_days, min_articles=args.min_articles)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
