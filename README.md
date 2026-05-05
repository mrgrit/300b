# 300B 실습 환경 — 4-tier (AWS-style) 단일 VM 배포

학생 PC 의 VMware VM 1대 안에 **AWS 풀 스택 보안 아키텍처를 흉내낸 docker 컨테이너**들로 모두 띄운다.

```
       Edge → DMZ → Private + Mgmt 4-tier 분리
       방화벽(nftables+socat) → WAF(Apache+ModSec) → vuln backends
       IDS(Suricata) sniff · Bastion-only SSH · 사설 DNS · 자체 CA TLS
```

📘 **상세 사용 가이드 (학생용 / 교육용)**: [USAGE.md](./USAGE.md)
— VM 만들기부터 첫 실습 시나리오, 모든 ID/비밀번호, 트러블슈팅 FAQ, AWS 매핑 표 포함

## VM 권장 사양

| 등급 | CPU | RAM | Disk | 비고 |
|------|-----|-----|------|------|
| **최소** | 2 vCPU | 6 GB | 40 GB | Wazuh 제외 |
| **권장** | 4 vCPU | 12 GB | 60 GB | 풀 스택 (Wazuh + msf 포함) |
| **안전** | 6 vCPU | 16 GB | 80 GB | 풀 스택 + 동시 실습 여유 |

## 빠른 시작 (학생용)

1. Ubuntu 22.04 server VM 1대 준비 (VMware **Bridge 네트워크 1개**)
2. 위 권장 사양으로 CPU/RAM/Disk 할당
3. VM 안에서:
   ```bash
   git clone https://github.com/mrgrit/300b
   cd 300b
   cp .env.example .env       # LLM_BASE_URL 만 학교 GPU 서버 주소로 수정
   bash 300b.sh up            # 첫 빌드 10~15 분 (msf 포함)
   bash 300b.sh smoke
   ```
4. 학생 PC DNS 또는 hosts 설정 (USAGE.md §3 참조). VM IP 는 `bash 300b.sh status` 로 확인.
5. 브라우저: `http://juice.300b.lab/`, `https://wazuh.300b.lab/` 등.

## 컨테이너 구성 (총 17개)

| Tier | 컨테이너 | 역할 |
|------|----------|------|
| **Edge** | 300b-fw | nftables + socat L4 forward (host:80,443 → waf) + dnsmasq |
| **DMZ** | 300b-waf | Apache + ModSecurity + OWASP CRS, 9 vhost reverse proxy, self-signed CA |
| **DMZ sidecar** | 300b-ids | Suricata IDS passive sniff, eve.json → siem |
| **Mgmt** | 300b-bastion | SSH jumphost + Bastion API + KG |
| **Mgmt** | 300b-secu | nftables/Suricata/dnsmasq 학습용 |
| **Mgmt** | 300b-siem | rsyslog 수신 + cti-collector |
| **Mgmt** | 300b-attacker | 13 도구 + Metasploit (private 에 dual-NIC) |
| **Mgmt (Wazuh)** | wazuh-indexer / manager / dashboard | OpenSearch + agent + Web UI |
| **Private** | juiceshop / dvwa / neobank / govportal / mediforum / adminconsole / aicompanion | 7 vuln backends (외부 포트 노출 ❌) |

**외부 노출 호스트 포트는 단 4개**: 80 (HTTP), 443 (HTTPS), 53 (DNS), 2204 (bastion SSH).

## 학생 접속

### 브라우저
```
http://juice.300b.lab/         OWASP Juice Shop
https://juice.300b.lab/        TLS (self-signed CA — http://VMIP/300b-ca.crt 다운로드 import)
http://dvwa.300b.lab/          DVWA
http://neobank.300b.lab/       NeoBank
http://govportal.300b.lab/     GovPortal
http://mediforum.300b.lab/     MediForum
http://admin.300b.lab/         AdminConsole
http://ai.300b.lab/            AICompanion (외부 LLM 사용)
https://wazuh.300b.lab/        Wazuh Dashboard (admin / SecretPassword)
http://bastion.300b.lab/health Bastion API
```

학생 PC 가 `*.300b.lab` 을 VM IP 로 해석하려면 1택:

| 방식 | 작업 | 장점 |
|------|------|------|
| **A. DNS 서버 변경** | Windows 어댑터 DNS 를 VM_IP 로 | 한 번 설정, 자동 해석 |
| **B. /etc/hosts** | 9줄 수동 추가 (USAGE.md §3-B) | DNS 권한 없을 때 |

### SSH (Bastion ProxyJump 모델)
모든 내부 컨테이너 SSH 는 bastion (port 2204) 만 외부 노출. 학생 PC `~/.ssh/config` 에 1회 추가:
```ssh-config
Host 300b-bastion
  HostName <VM_IP>
  Port 2204
  User ccc

Host 300b-*
  ProxyJump 300b-bastion
  User ccc
```
그 후: `ssh 300b-attacker`, `ssh 300b-waf`, `ssh 300b-fw` 등.

## AWS 매핑

| AWS | 300B |
|-----|------|
| Internet Gateway | host port mapping (fw, bastion) |
| Network Firewall | 300b-fw nftables |
| ALB + WAF | 300b-waf Apache + ModSec |
| GuardDuty / VPC Flow | 300b-ids Suricata |
| Bastion Host | 300b-bastion (jumphost) |
| Public subnet | 300b-edge (172.30.10/24) |
| DMZ subnet | 300b-dmz (172.30.20/24) |
| Private subnet | 300b-private (172.30.30/24, **internal: true**) |
| Mgmt subnet | 300b-mgmt (172.30.40/24) |
| Route 53 (private zone) | dnsmasq on 300b-fw |
| ACM (private CA) | self-signed CA on 300b-waf |
| CloudWatch / Security Hub | Wazuh manager + dashboard |

## 명령어

```bash
bash 300b.sh up        # 빌드 + 기동 (VM_IP 자동 .env 주입)
bash 300b.sh status    # 상태 + 외부 접속 정보 + ProxyJump 안내
bash 300b.sh smoke     # 헬스 체크 (HTTP+HTTPS 9 vhost + SSH bastion + 격리 검증)
bash 300b.sh logs <svc>
bash 300b.sh down
bash 300b.sh destroy   # 컨테이너+볼륨+이미지 삭제
```

## 운영 메모

- Wazuh indexer 는 `vm.max_map_count >= 262144` 요구 — 스크립트가 자동 적용.
- 첫 빌드 시 attacker 의 metasploit omnibus 다운로드 (~800 MB).
- bastion·cti·waf 코드는 컨테이너 빌드 시점에 이미지에 베이크.
- bastion KG / evidence DB 는 `300b-bastion-data` 볼륨에 영속.
- private 망은 `internal: true` — vuln 사이트가 침해돼도 외부 C2/exfil 차단됨.
- self-signed root CA `http://<VM_IP>/300b-ca.crt` 다운로드 후 PC import 시 HTTPS 경고 사라짐.

## 검증 상태

| 영역 | 상태 |
|------|------|
| 17 컨테이너 부트 | ✅ |
| 9 vhost HTTP 200/302 | ✅ |
| 9 vhost HTTPS 200/302 (self-signed CA) | ✅ |
| ssh -J ccc@VM:2204 ccc@300b-attacker | ✅ |
| 직접 :3000/:3001/.../:8080 노출 거부 | ✅ |
| private vuln 외부 도달 불가 (격리) | ✅ |
| AICompanion → 외부 LLM (mgmt 경유) | ✅ |
| dnsmasq *.300b.lab 응답 | ✅ |
| systemctl/journalctl shim (5 mgmt 컨테이너) | ✅ |
