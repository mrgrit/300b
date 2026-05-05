# 300B 실습 환경 — 학생 1인용 단일 VM 배포

중앙 서버 없이 학생 PC 의 VMware VM 1대 안에 모든 인프라를 Docker 컨테이너로 띄우는 버전.

## 빠른 시작 (학생용)

1. Ubuntu 22.04 server VM 1대 준비 (VMware Bridge 네트워크 1개 — 학생 PC LAN 과 같은 대역)
2. CPU 4 vCPU 이상, **RAM 12 GB 이상** 권장 (Wazuh indexer 가 메모리 큼), Disk 60 GB
3. VM 안에서:
   ```bash
   git clone https://github.com/mrgrit/300b
   cd 300b
   cp .env.example .env       # LLM_BASE_URL 만 학교 GPU 서버 주소로 수정
   bash 300b.sh up  # 첫 빌드 10~15 분 소요 (msf 포함)
   bash 300b.sh smoke
   ```
4. Windows 에서 접속:
   - SSH: `ssh ccc@<VM_IP> -p 220{1..5}`  (암호 `ccc`)
   - 브라우저: `http://<VM_IP>:3000` (Juice Shop), `https://<VM_IP>:1443` (Wazuh) 등

## 컨테이너 구성 (총 14개)

| 그룹 | 컨테이너 | 노출 포트 | 비고 |
|------|----------|----------|------|
| 코어 | 300b-secu | 2201/ssh | nftables + Suricata + dnsmasq |
| 코어 | 300b-web | 2202/ssh, 80 | Apache + ModSecurity + landing |
| 코어 | 300b-siem | 2203/ssh | rsyslog + cti-collector cron |
| 코어 | 300b-bastion | 2204/ssh, 8003 | bastion API (KG 통합 그대로) |
| 코어 | 300b-attacker | 2205/ssh | nmap/hydra/sqlmap/.../msf 13+α |
| Wazuh | wazuh-indexer | (내부) | OpenSearch |
| Wazuh | wazuh-manager | 1514, 1515, 514/udp | agent + syslog |
| Wazuh | wazuh-dashboard | 1443→5601 | Web UI (admin/SecretPassword) |
| 취약 | juiceshop | 3000 | OWASP Juice Shop |
| 취약 | dvwa | 8080→80 | DVWA |
| 취약 | neobank/govportal/mediforum/adminconsole/aicompanion | 3001-3005 | 자체 5종 |

## 네트워크

- **VM 외부**: Bridge 1개 → 학생 PC LAN의 1 IP. Windows 에서 `<VM_IP>:포트`.
- **VM 내부 docker**:
  - `300b-edu` (172.30.30.0/24) — 공방전 트래픽 (attacker ↔ web/vuln 사이트, secu 게이트웨이)
  - `300b-mgmt` (172.30.40.0/24) — 관리/로그 (bastion ↔ 모든 코어, siem ↔ wazuh)

multi-VM L2 isolation 이 필수인 일부 advanced 랩 (C13/C14 lateral movement) 은
docker network 분리로 **L3 레벨 격리 ~90% 시뮬레이션**. 100% 재현은 standalone 에서 불가.

## AI/GPU

이 VM 안에서는 LLM 미실행. `.env` 의 `LLM_BASE_URL` 이 외부 학교 GPU 서버 (Ollama) 를 가리킴.
AICompanion 컨테이너는 `LLM_BACKEND=ollama` 로 바꾸면 같은 외부 서버를 사용.

## 명령어

```bash
bash 300b.sh up        # 빌드 + 기동
bash 300b.sh status    # 상태 + 외부 접속 정보
bash 300b.sh smoke     # 헬스 체크
bash 300b.sh logs <svc> # 로그
bash 300b.sh down      # 정지
bash 300b.sh destroy   # 컨테이너+볼륨+이미지 삭제 (--reset)
```

## 운영 메모

- Wazuh indexer 는 `vm.max_map_count >= 262144` 요구 — 스크립트가 자동 적용.
- 첫 빌드 시 attacker 컨테이너가 metasploit omnibus 다운로드(약 800 MB)로 시간이 걸림.
  네트워크 좁으면 `BUILD_MSF=0 docker compose build 300b-attacker` 로 끄고 학생이 별도 설치.
- bastion·cti 코드는 컨테이너 빌드 시점에 이미지에 베이크됨. 호스트 마운트 없음 (컨테이너만 받으면 동작).
- siem 컨테이너의 cti-collector 는 매일 04:30 cron 으로 NVD CVE 수집 → `300b-cti-data` 볼륨에 저장.
- bastion KG / evidence DB 는 `300b-bastion-data` 볼륨에 영속. 학생이 직접 만져도 destroy 시 삭제.

## 검증 상태 (2026-05-05 기준, 이 서버에서 빌드/기동 테스트)

| 서비스 | 상태 | 비고 |
|--------|------|------|
| 300b-secu/web/siem/bastion/attacker | ✅ pass | SSH 5 포트 모두 OpenSSH banner 응답 |
| 5 자체 vuln-sites + JuiceShop + DVWA | ✅ pass | HTTP 200/302 |
| 300b-bastion API /health | ✅ pass | KG 4모듈 loaded, 33 skills, sqlite DB 자동 생성 |
| siem cti-collector cron | ✅ pass | /etc/cron.d/300b-cti 등록됨 |
| **Wazuh single-node 3 services** | ⚠️ **첫 부팅 plugin 로드 이슈** | indexer 의 OpenSearchSecurityPlugin 첫 부팅 실패. 권한·SSL config 추가 디버그 필요 — v2 단계 |

Wazuh 가 안정화되기 전까지는 syslog 수집을 300b-siem 컨테이너의 rsyslog (`514/udp`, `5514/tcp`)
로 모아 `/var/log/syslog` 에서 직접 확인 가능.
