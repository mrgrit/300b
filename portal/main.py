"""300B Portal — AWS Console 풍 학습용 운영 대시보드.

FastAPI + Jinja2 + HTMX. docker socket / suricata eve.json / modsec_audit.log /
sshd auth.log / wazuh API 를 통합해서 한 화면에서 보여준다.
"""

from __future__ import annotations

import json
import os
import re
import socket
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import docker
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

app = FastAPI(title="300B Portal", docs_url="/api/docs", redoc_url=None)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


# Docker SDK — host 의 /var/run/docker.sock 을 read-only 마운트 받음.
def docker_client() -> docker.DockerClient:
    return docker.DockerClient(base_url="unix:///var/run/docker.sock")


# ─── 공통 헬퍼 ──────────────────────────────────────────────

TIER_BY_NETWORK = {
    "300b-edge": "Edge",
    "300b-dmz": "DMZ",
    "300b-private": "Private",
    "300b-mgmt": "Mgmt",
}


def container_summary(c: Any) -> dict[str, Any]:
    """docker 컨테이너 객체에서 portal 표시용 dict 추출."""
    attrs = c.attrs
    networks = attrs.get("NetworkSettings", {}).get("Networks", {})
    nics = []
    tiers = set()
    for net_name, info in networks.items():
        nics.append({
            "network": net_name,
            "ip": info.get("IPAddress"),
        })
        if net_name in TIER_BY_NETWORK:
            tiers.add(TIER_BY_NETWORK[net_name])
    state = attrs.get("State", {})
    started_at = state.get("StartedAt", "")
    image = attrs.get("Config", {}).get("Image", "")
    ports = []
    for k, vlist in (attrs.get("NetworkSettings", {}).get("Ports") or {}).items():
        if vlist:
            for v in vlist:
                ports.append(f"{v.get('HostIp', '0.0.0.0')}:{v.get('HostPort')}→{k}")
    return {
        "name": c.name,
        "id_short": c.id[:12],
        "status": c.status,
        "health": state.get("Health", {}).get("Status") if state.get("Health") else None,
        "image": image,
        "started_at": started_at,
        "tiers": sorted(tiers),
        "nics": nics,
        "ports": ports,
        "is_300b": c.name.startswith("300b-") or c.name in {
            "juiceshop", "dvwa", "neobank", "govportal", "mediforum",
            "adminconsole", "aicompanion",
            "wazuh-indexer", "wazuh-manager", "wazuh-dashboard",
        },
    }


def list_300b_containers() -> list[dict[str, Any]]:
    cl = docker_client()
    out = []
    for c in cl.containers.list(all=True):
        s = container_summary(c)
        if s["is_300b"]:
            out.append(s)
    out.sort(key=lambda x: (
        # tier 순서: Edge → DMZ → Private → Mgmt
        ["Edge", "DMZ", "Private", "Mgmt"].index(x["tiers"][0]) if x["tiers"] else 99,
        x["name"],
    ))
    return out


# ─── 페이지 ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> Any:
    try:
        containers = list_300b_containers()
    except Exception as e:
        containers = []
        err = str(e)
    else:
        err = None

    by_tier: dict[str, list[Any]] = {"Edge": [], "DMZ": [], "Private": [], "Mgmt": []}
    counts = {"running": 0, "exited": 0, "other": 0}
    for c in containers:
        for t in c["tiers"] or ["Mgmt"]:
            by_tier.setdefault(t, []).append(c)
        if c["status"] == "running":
            counts["running"] += 1
        elif c["status"] in ("exited", "dead"):
            counts["exited"] += 1
        else:
            counts["other"] += 1

    # 최근 알람 / 활동 (best-effort)
    try:
        ids_alerts = read_eve_alerts(limit=5)
    except Exception:
        ids_alerts = []
    try:
        modsec_recent = read_modsec_audit(limit=5)
    except Exception:
        modsec_recent = []

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "page": "dashboard",
            "containers": containers,
            "by_tier": by_tier,
            "counts": counts,
            "ids_alerts": ids_alerts,
            "modsec_recent": modsec_recent,
            "err": err,
        },
    )


@app.get("/resources", response_class=HTMLResponse)
async def resources(request: Request) -> Any:
    """EC2-like 컨테이너 목록."""
    containers = list_300b_containers()
    return templates.TemplateResponse(
        "resources.html",
        {"request": request, "page": "resources", "containers": containers},
    )


@app.get("/network", response_class=HTMLResponse)
async def network(request: Request) -> Any:
    """VPC 토폴로지 SVG."""
    containers = list_300b_containers()
    by_network: dict[str, list[Any]] = {}
    for c in containers:
        for nic in c["nics"]:
            by_network.setdefault(nic["network"], []).append({
                "name": c.name if hasattr(c, "name") else c["name"],
                "ip": nic["ip"],
            })
    return templates.TemplateResponse(
        "network.html",
        {"request": request, "page": "network", "by_network": by_network},
    )


@app.get("/logs", response_class=HTMLResponse)
async def logs_index(request: Request) -> Any:
    containers = list_300b_containers()
    return templates.TemplateResponse(
        "logs_index.html",
        {"request": request, "page": "logs", "containers": containers},
    )


@app.get("/logs/{name}", response_class=HTMLResponse)
async def logs_view(request: Request, name: str) -> Any:
    return templates.TemplateResponse(
        "logs_view.html",
        {"request": request, "page": "logs", "name": name},
    )


@app.get("/logs/{name}/tail", response_class=PlainTextResponse)
async def logs_tail(name: str, lines: int = 200) -> str:
    """HTMX 가 polling 으로 호출 — 컨테이너 stdout 의 최근 N 줄."""
    cl = docker_client()
    try:
        c = cl.containers.get(name)
    except docker.errors.NotFound:
        return f"(container '{name}' not found)"
    try:
        raw = c.logs(tail=lines, timestamps=True).decode("utf-8", errors="replace")
    except Exception as e:
        return f"(logs error: {e})"
    return raw


# ─── WAF / IDS / Audit ────────────────────────────────

WAF_LOGS = "/portal-data/waf-logs"      # waf 의 /var/log/apache2 마운트 (compose 에서)
IDS_LOGS = "/portal-data/ids-logs"      # ids 의 /var/log/suricata 마운트


def read_modsec_audit(limit: int = 30) -> list[dict[str, str]]:
    """waf 의 modsec_audit.log 또는 vhost 별 access.log 에서 차단된 요청 추출 (best-effort)."""
    out: list[dict[str, str]] = []
    log = Path(WAF_LOGS) / "modsec_audit.log"
    if log.exists():
        try:
            content = log.read_text(errors="replace")
        except Exception:
            content = ""
        # ModSecurity audit log 는 multiple-line — 간단히 마지막 N entries 만 슬라이스.
        entries = content.split("--")
        for e in entries[-limit:]:
            if "Message:" in e or "Rule" in e:
                out.append({
                    "raw": e[:500],
                })
    return out[-limit:]


def read_eve_alerts(limit: int = 50) -> list[dict[str, Any]]:
    """suricata eve.json 의 최근 alert 만 추출."""
    out: list[dict[str, Any]] = []
    log = Path(IDS_LOGS) / "eve.json"
    if log.exists():
        try:
            with log.open() as f:
                lines = f.readlines()[-2000:]
            for line in lines:
                try:
                    j = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if j.get("event_type") == "alert":
                    out.append({
                        "ts": j.get("timestamp", ""),
                        "src_ip": j.get("src_ip", ""),
                        "dst_ip": j.get("dest_ip", ""),
                        "signature": j.get("alert", {}).get("signature", ""),
                        "category": j.get("alert", {}).get("category", ""),
                        "severity": j.get("alert", {}).get("severity", 0),
                    })
        except Exception:
            pass
    return out[-limit:]


@app.get("/waf", response_class=HTMLResponse)
async def waf_view(request: Request) -> Any:
    entries = read_modsec_audit(limit=50)
    return templates.TemplateResponse(
        "waf.html", {"request": request, "page": "waf", "entries": entries},
    )


@app.get("/ids", response_class=HTMLResponse)
async def ids_view(request: Request) -> Any:
    alerts = read_eve_alerts(limit=200)
    sig_counter = Counter(a["signature"] for a in alerts if a["signature"])
    top_sigs = sig_counter.most_common(10)
    return templates.TemplateResponse(
        "ids.html",
        {"request": request, "page": "ids", "alerts": alerts[-50:], "top_sigs": top_sigs},
    )


@app.get("/audit", response_class=HTMLResponse)
async def audit_view(request: Request) -> Any:
    """bastion 의 /var/log/auth.log 를 docker exec 로 읽기 (CloudTrail 시뮬)."""
    cl = docker_client()
    auth_log = "(no entries)"
    try:
        b = cl.containers.get("300b-bastion")
        # 직접 파일 읽기 (read API 가 binary 라 demo 단순화)
        rc, output = b.exec_run("tail -n 80 /var/log/auth.log", demux=False)
        auth_log = output.decode("utf-8", errors="replace") if output else "(empty)"
    except Exception as e:
        auth_log = f"(error: {e})"

    return templates.TemplateResponse(
        "audit.html",
        {"request": request, "page": "audit", "auth_log": auth_log},
    )


# ─── Wazuh / Bastion 외부 링크 (deep integration 은 후속) ───────

@app.get("/wazuh-redirect")
async def wazuh_redirect() -> Any:
    """Wazuh dashboard 로 redirect (waf 통한 https://wazuh.300b.lab/)."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="https://wazuh.300b.lab/", status_code=302)


@app.get("/agent", response_class=HTMLResponse)
async def agent_view(request: Request) -> Any:
    """bastion API 의 health/skills 표시 + chat 링크."""
    bastion_api = "http://300b-bastion:8003"
    health: dict[str, Any] = {"status": "unknown"}
    skills: list[Any] = []
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{bastion_api}/health")
            if r.status_code == 200:
                health = r.json()
            api_key = os.environ.get("API_KEY", "300b-api-key-2026")
            r = await c.get(f"{bastion_api}/skills", headers={"X-API-Key": api_key})
            if r.status_code == 200:
                skills = r.json() if isinstance(r.json(), list) else r.json().get("skills", [])
    except Exception as e:
        health = {"status": "error", "msg": str(e)}

    return templates.TemplateResponse(
        "agent.html",
        {"request": request, "page": "agent", "health": health, "skills": skills},
    )


# ─── Health (자체) ─────────────────────────────────────────

@app.get("/health")
async def health() -> Any:
    return {"status": "ok", "service": "300b-portal", "ts": datetime.utcnow().isoformat() + "Z"}
