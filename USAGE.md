# 300B 실습 환경 — 사용 가이드 (교육용)

> 본 문서는 **학생** 입장에서 처음부터 끝까지 따라할 수 있도록 작성되었습니다.
> 스크린샷·교수자 추가 안내가 필요하면 강의 자료에서 확인하세요.

---

## 목차

1. [환경 개요](#1-환경-개요)
2. [학생 PC 사전 준비](#2-학생-pc-사전-준비)
3. [Ubuntu VM 만들기 (VMware)](#3-ubuntu-vm-만들기-vmware)
4. [300B 설치](#4-300b-설치)
5. [기본 ID / 비밀번호 — 모든 서비스](#5-기본-id--비밀번호--모든-서비스)
6. [Windows 에서 접속하기](#6-windows-에서-접속하기)
7. [첫 실습 시나리오 (5분 워크쓰루)](#7-첫-실습-시나리오-5분-워크쓰루)
8. [명령어 치트시트](#8-명령어-치트시트)
9. [트러블슈팅 FAQ](#9-트러블슈팅-faq)
10. [비밀번호·키 변경](#10-비밀번호키-변경)
11. [고급 — 네트워크 / 볼륨 / 로그](#11-고급--네트워크--볼륨--로그)

---

## 1. 환경 개요

300B 는 학생 PC 한 대에 **VMware VM 1개** 를 만들고, 그 안에 **Docker 컨테이너 14개**
를 띄워서 사이버보안 실습을 위한 모든 인프라를 한 번에 구성합니다.

```
[학생 Windows PC]
        │
        ├─ ssh / 브라우저
        ▼
[Ubuntu 22.04 VM (Bridge IP)]
        │
        ├─ Docker network: 300b-edu (172.30.30.0/24)   공방전 트래픽
        └─ Docker network: 300b-mgmt (172.30.40.0/24)  관리·로그
              │
              ├─ 코어 5: secu / web / siem / bastion / attacker
              ├─ Wazuh 3: indexer / manager / dashboard
              └─ 취약 7: juiceshop / dvwa / neobank / govportal /
                          mediforum / adminconsole / aicompanion
```

학생이 다루는 것은 **이 VM 하나** 뿐. 중앙 서버 의존 없음.
LLM(Ollama) 만 외부 학교 GPU 서버를 사용합니다 (.env 의 `LLM_BASE_URL`).

---

## 2. 학생 PC 사전 준비

### 최소·권장 사양

| 등급 | 학생 호스트 PC | VM 할당 |
|------|---------------|---------|
| 최소 | RAM 12 GB / 4 core / Disk 100 GB | 6 GB / 2 vCPU / 40 GB (Wazuh 제외) |
| 권장 | RAM 16 GB / 6 core / Disk 150 GB | 12 GB / 4 vCPU / 60 GB (풀 스택) |
| 안전 | RAM 32 GB / 8 core / Disk 200 GB | 16 GB / 6 vCPU / 80 GB |

### 설치할 소프트웨어 (학생 호스트)

1. **VMware Workstation Player** (무료, 개인 학습용) 또는 VMware Workstation Pro
   - https://www.vmware.com/products/workstation-player.html
2. **Ubuntu 22.04 server ISO** 다운로드
   - https://releases.ubuntu.com/22.04/
   - `ubuntu-22.04.x-live-server-amd64.iso` (약 2 GB)
3. **SSH 클라이언트** — Windows 10/11 기본 OpenSSH 또는 PuTTY / MobaXterm
4. **모던 브라우저** — Chrome / Edge / Firefox (Wazuh dashboard 호환)

---

## 3. Ubuntu VM 만들기 (VMware)

### 3-1. 새 VM 생성

VMware Player → `Create a New Virtual Machine`

1. **Installer disc image (iso)** → 다운로드한 Ubuntu 22.04 ISO 선택
2. Guest OS: Linux → Ubuntu 64-bit
3. VM 이름: `300b-lab` (자유)
4. **Disk size**: 60 GB 권장 (`Store as a single file` 또는 split — 자유)
5. 완료 후 **Edit virtual machine settings** 진입

### 3-2. 하드웨어 설정

| 항목 | 권장값 |
|------|-------|
| Memory | 12288 MB (12 GB) |
| Processors | 4 cores |
| **Network Adapter** | **Bridged (Replicate physical network connection state 체크)** |
| (선택) Network Adapter 2 | 사용 X |

> ⚠️ **Bridge 가 핵심**입니다. NAT 로 두면 Windows 에서 VM 으로 접속할 때
> VMware 의 포트포워딩 설정을 일일이 추가해야 합니다.

### 3-3. Ubuntu 설치

전원 ON → ISO 부팅 → Ubuntu Server 설치 진행:

- 언어: English / 한국어 (선택)
- 키보드: 자동
- 네트워크: DHCP 자동 설정 (Bridge 라 학생 PC LAN 의 IP 가 잡힘)
  - **이 IP 메모해두세요** — 예: `192.168.0.45`
- 저장소: 전체 디스크 사용
- Profile setup:
  - Your name: `student` (자유)
  - Your server's name: `300b-lab`
  - Username: `student` (자유)
  - Password: 자유 (이 암호는 **VM 자체 SSH 용** — 컨테이너 SSH 와 별개)
- **Install OpenSSH server** ✅ 체크 (필수)
- Featured snaps: 모두 unchecked
- 설치 완료 후 재부팅

### 3-4. VM IP 확인

VM 콘솔 또는 Windows 에서:

```bash
ip a | grep inet
```

→ 예: `192.168.0.45/24` 형식. 이걸 `<VM_IP>` 로 사용합니다.

---

## 4. 300B 설치

VM 안에서 (콘솔 직접 또는 Windows 에서 ssh `student@<VM_IP>` 접속):

### 4-1. Git 설치 + 클론

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/mrgrit/300b
cd 300b
```

### 4-2. .env 파일 생성

```bash
cp .env.example .env
nano .env   # 또는 vi
```

**반드시 확인할 항목**: `LLM_BASE_URL` 을 학교에서 안내한 GPU 서버 주소로 변경.

```dotenv
LLM_BASE_URL=http://192.168.0.105:11434   # ← 학교 GPU IP
```

다른 항목은 그대로 두어도 동작합니다 (포트 충돌이 있으면 그때만 수정).

### 4-3. 첫 실행

```bash
bash 300b.sh up
```

처음 실행 시 자동으로 다음을 수행합니다:
1. Docker 미설치면 자동 설치 (sudo 패스워드 1회 입력)
2. `vm.max_map_count` 설정 (Wazuh indexer 요구사항)
3. Wazuh SSL 인증서 1회 생성
4. Docker 이미지 14개 빌드 (**약 10~20 분 소요** — 첫 실행만)
5. 모든 컨테이너 기동
6. 접속 정보 출력

빌드가 길어 보여도 끝까지 기다리세요. msf(Metasploit) 다운로드가 약 800 MB 입니다.

### 4-4. 헬스 체크

```bash
bash 300b.sh smoke
```

기대 결과:
```
─── 헬스 체크 ───
  ✓ 300b-web landing       http://localhost:80/  (HTTP 200)
  ✓ bastion /health        http://localhost:8003/health  (HTTP 200)
  ✓ juiceshop              http://localhost:3000/  (HTTP 200)
  ... (총 10 줄)
─── SSH 헬스 (banner) ───
  ✓ secu                   tcp/2201  SSH-2.0-OpenSSH_8.9p1
  ... (총 5 줄)
  종합: 15 pass / 0 fail
  ✅ 전부 통과
```

`fail` 이 있으면 `bash 300b.sh logs <서비스명>` 으로 원인 확인.

---

## 5. 기본 ID / 비밀번호 — 모든 서비스

> ⚠️ **데모용 default 비밀번호입니다.** 실습실 외부에서 접속 가능한 환경이면 반드시 변경하세요. 변경 방법은 [§10](#10-비밀번호키-변경) 참조.

### 5-1. SSH (컨테이너 5개)

| 컨테이너 | 호스트 포트 | 계정 | 암호 | sudo |
|---------|-----------|------|------|------|
| 300b-secu | 2201 | `ccc` | `ccc` | NOPASSWD ✅ |
| 300b-web | 2202 | `ccc` | `ccc` | NOPASSWD ✅ |
| 300b-siem | 2203 | `ccc` | `ccc` | NOPASSWD ✅ |
| 300b-bastion | 2204 | `ccc` | `ccc` | NOPASSWD ✅ |
| 300b-attacker | 2205 | `ccc` | `ccc` | NOPASSWD ✅ |

추가로 모든 컨테이너에 `root` / `ccc` 가 활성화되어 있습니다 (sudo 막힐 때 비상용).

### 5-2. SIEM / 보안 콘솔

| 서비스 | URL | 계정 | 암호 | 비고 |
|--------|-----|------|------|------|
| **Wazuh Dashboard** | `https://<VM_IP>:1443` | `admin` | `SecretPassword` | 자체 서명 인증서 → 브라우저 경고 무시 |
| Wazuh Manager API | 내부 `:55000` | `wazuh-wui` | `MyS3cr37P450r.*-` | 컨테이너 내부에서만 호출 |
| Wazuh Indexer | 내부 `:9200` | `admin` | `SecretPassword` | OpenSearch REST API |

브라우저 처음 접속 시 SSL 경고가 나옵니다 → `Advanced` → `Proceed to ...` 클릭.

### 5-3. Bastion API (운영 보조 에이전트)

| 항목 | 값 |
|------|-----|
| URL | `http://<VM_IP>:8003` |
| 인증 헤더 | `X-API-Key: 300b-api-key-2026` |
| 헬스체크 | `GET /health` (인증 불필요) |
| 채팅 | `POST /chat` (NDJSON 스트림) |
| Skill 목록 | `GET /skills` |
| Playbook 목록 | `GET /playbooks` |
| KG 헬스 | `GET /kg/health` |

예:
```bash
curl http://<VM_IP>:8003/health
curl -H "X-API-Key: 300b-api-key-2026" http://<VM_IP>:8003/skills
```

### 5-4. 취약 웹 (공격 대상)

학생이 공격을 연습하는 대상입니다 — 의도적으로 취약합니다.

| 사이트 | URL | 기본 로그인 / 노트 |
|--------|-----|------------------|
| **DVWA** | `http://<VM_IP>:8080` | `admin` / `password` (첫 접속 시 `Create / Reset Database` 클릭) |
| **Juice Shop** | `http://<VM_IP>:3000` | 회원가입형. admin 은 SQLi 또는 CTF 챌린지로 획득 |
| **NeoBank** | `http://<VM_IP>:3001` | 시드 사용자 인덱스/`/api/users` 에서 확인. 30 취약점 |
| **GovPortal** | `http://<VM_IP>:3002` | 시드 사용자 페이지 내 안내. 25 취약점 |
| **MediForum** | `http://<VM_IP>:3003` | `/api/users` PII 노출 V07 챌린지. 22 취약점 |
| **AdminConsole** | `http://<VM_IP>:3004` | `admin` / `admin` (V14 default cred 자체가 취약점). 28 취약점 |
| **AICompanion** | `http://<VM_IP>:3005` | LLM 챗봇. prompt injection / system prompt leak. 25 취약점 |

> 시드 사용자 / API 토큰 등 세부 정보는 각 사이트의 `/health` 또는 `/_health` 엔드포인트, 그리고 인덱스 페이지에 의도적으로 노출됩니다 — 학생이 발견해야 하는 취약점입니다.

### 5-5. 환경변수 (`.env`)

학생이 한 번에 보고 변경하는 곳:

```dotenv
# 외부 LLM
LLM_BASE_URL=http://192.168.0.105:11434
LLM_MANAGER_MODEL=gpt-oss:120b
LLM_SUBAGENT_MODEL=gemma3:4b

# SSH 계정 (모든 컨테이너 공통)
SSH_USER=ccc
SSH_PASS=ccc

# API 인증
API_KEY=300b-api-key-2026
JWT_SECRET=300b-jwt-secret-2026
```

---

## 6. Windows 에서 접속하기

### 6-1. SSH (Windows 10/11)

기본 PowerShell 또는 cmd 에서:
```powershell
ssh ccc@192.168.0.45 -p 2201    # secu 컨테이너
```
(`192.168.0.45` 자리는 본인 VM IP)

처음 접속 시 호스트 키 확인 메시지 → `yes` 입력.

암호 입력 화면 → `ccc`

### 6-2. PuTTY 사용 시

| 필드 | 값 |
|------|-----|
| Host Name | `192.168.0.45` |
| Port | `2201` (또는 2202~2205) |
| Connection type | SSH |
| 로그인: | `ccc` / `ccc` |

### 6-3. SCP 로 파일 전송

```powershell
# Windows → 컨테이너
scp -P 2205 .\payload.txt ccc@192.168.0.45:/home/ccc/

# 컨테이너 → Windows
scp -P 2205 ccc@192.168.0.45:/home/ccc/result.txt .
```

### 6-4. 브라우저 접속

| 서비스 | URL |
|--------|-----|
| 랜딩 (모든 링크 모음) | `http://192.168.0.45/` |
| Wazuh | `https://192.168.0.45:1443` |
| Juice Shop | `http://192.168.0.45:3000` |
| NeoBank | `http://192.168.0.45:3001` |
| GovPortal | `http://192.168.0.45:3002` |
| MediForum | `http://192.168.0.45:3003` |
| AdminConsole | `http://192.168.0.45:3004` |
| AICompanion | `http://192.168.0.45:3005` |
| DVWA | `http://192.168.0.45:8080` |
| Bastion API | `http://192.168.0.45:8003/health` |

---

## 7. 첫 실습 시나리오 (5분 워크쓰루)

처음 환경 동작을 체감해 보는 가장 짧은 코스.

### 시나리오: attacker → web (NeoBank) 정찰 → SQLi 확인 → SIEM 로그 확인

```bash
# 1. Windows → attacker 컨테이너 SSH 접속
ssh ccc@192.168.0.45 -p 2205

# 2. 컨테이너 내부 DNS 로 NeoBank 발견
nslookup neobank
# → 172.30.30.x 응답

# 3. 포트 스캔 + 웹 서비스 식별
nmap -sV neobank
whatweb http://neobank:3001

# 4. SQLi 자동 탐지 (의도된 취약점 — 학습 환경에서만!)
sqlmap -u "http://neobank:3001/api/login" --data='{"u":"a","p":"b"}' --batch --level=2

# 5. Windows 브라우저 → https://192.168.0.45:1443 (Wazuh)
#    Discover → 최근 이벤트에 nmap / sqlmap 트래픽 확인
```

### 다른 시작점

- **DVWA**: 가장 친숙한 OWASP Top10 연습장. 첫 로그인 후 `Setup / Reset DB` 1회.
- **Juice Shop**: CTF 형식. 100+ 챌린지. Score Board 발견부터 시작 (`/#/score-board`).
- **Bastion AI 챗**: `curl -H "X-API-Key: 300b-api-key-2026" -X POST http://<VM_IP>:8003/chat -d '{"message":"이 환경 자가진단 해줘"}'`

---

## 8. 명령어 치트시트

```bash
# ─── 운영 ───
bash 300b.sh up         # 빌드 + 기동 (첫 실행 또는 .env 변경 후)
bash 300b.sh down       # 정지 (데이터 유지)
bash 300b.sh status     # 컨테이너 상태 + 외부 접속 정보 출력
bash 300b.sh smoke      # 15개 헬스체크 한번에
bash 300b.sh logs <svc> # 특정 서비스 로그 (실시간 tail)
bash 300b.sh destroy    # ⚠️ 모든 컨테이너 + 볼륨 + 이미지 삭제 (학생 데이터 모두 사라짐)

# ─── 개별 컨테이너 ───
docker ps                                # 실행 중 컨테이너 목록
docker exec -it 300b-attacker bash       # 호스트(VM)에서 컨테이너 직접 진입
docker logs -f wazuh-dashboard           # 실시간 로그
docker stats --no-stream                 # 메모리·CPU 사용량 스냅샷

# ─── 네트워크 ───
docker network inspect 300b-edu          # 공방전 네트워크 (attacker ↔ vuln)
docker network inspect 300b-mgmt         # 관리 네트워크

# ─── 데이터 볼륨 ───
docker volume ls | grep 300b
docker volume inspect 300b_300b-bastion-data    # bastion KG DB 위치
```

---

## 9. 트러블슈팅 FAQ

### Q1. `bash 300b.sh up` 첫 실행 시 sudo 비밀번호 묻고 멈춤
첫 실행은 Docker 자동 설치 / sysctl 변경에 sudo 필요합니다. **VM 콘솔에서 직접 실행** 또는 ssh 세션을 인터랙티브하게 유지해주세요. 비밀번호는 Ubuntu 설치 때 만든 `student` 계정 암호입니다.

### Q2. wazuh-indexer 가 자꾸 재시작
- VM RAM < 8 GB 인 경우 발생. README 권장 사양 확인.
- `vm.max_map_count` 적용 안 된 경우. 다음 명령 1회 실행:
  ```bash
  sudo sysctl -w vm.max_map_count=262144
  echo 'vm.max_map_count=262144' | sudo tee /etc/sysctl.d/99-300b.conf
  ```
- SSL 인증서 손상. 다음으로 재생성:
  ```bash
  rm -rf wazuh-certs/certs/*
  bash 300b.sh up
  ```

### Q3. `https://<VM_IP>:1443` 가 안 열림
- Wazuh 첫 부팅은 약 60~90 초 소요. 잠깐 기다린 후 재시도.
- 브라우저 SSL 경고는 자체 서명 인증서 → `Advanced` → `Proceed`.
- VM 방화벽: `sudo ufw status` → 비활성이면 OK. 활성이면 1443 허용.

### Q4. 포트 충돌 (`port is already allocated`)
다른 docker 컨테이너 또는 호스트 서비스가 점유 중. 해결:
- `sudo ss -tlnp | grep <포트>` 로 점유자 확인
- 또는 `.env` 에서 해당 `PORT_*` 변수를 비어있는 포트로 변경 후 `bash 300b.sh up`

### Q5. Windows 에서 VM 의 docker 컨테이너로 ping 이 안 됨
이는 **정상**입니다. 컨테이너 내부 IP (172.30.30.x) 는 학생 PC LAN 에 노출되지 않습니다. 호스트 포트(`<VM_IP>:포트`)로 접근하세요.

### Q6. AICompanion 에서 LLM 응답이 `[mock]` 으로 옴
`.env` 의 `LLM_BASE_URL` 이 외부 GPU 서버를 가리키지 않거나, AICompanion 의 backend 가 mock 모드. 다음 둘 다 확인:
- `.env` 의 `LLM_BASE_URL` 정확한지
- `docker-compose.yaml` 의 `aicompanion` 서비스 환경변수에서 `LLM_BACKEND=ollama` 로 설정 (default 는 `mock`)

### Q7. attacker 컨테이너에서 msf 가 없음
첫 빌드 시 `BUILD_MSF=0` 이거나 다운로드 실패. 다음 명령으로 재빌드:
```bash
docker compose build --build-arg BUILD_MSF=1 300b-attacker
docker compose up -d --force-recreate 300b-attacker
```

### Q8. 학생 데이터를 백업하고 싶음
bastion KG 와 cti 수집 데이터는 docker volume 에 있음:
```bash
docker run --rm -v 300b_300b-bastion-data:/src -v $(pwd):/dst alpine tar czf /dst/bastion-backup.tar.gz -C /src .
docker run --rm -v 300b_300b-cti-data:/src -v $(pwd):/dst alpine tar czf /dst/cti-backup.tar.gz -C /src .
```

---

## 10. 비밀번호·키 변경

### 10-1. SSH 계정 (모든 컨테이너 일괄)

`.env` 편집:
```dotenv
SSH_USER=mystudent
SSH_PASS=MyStr0ngPass!
```

적용:
```bash
docker compose up -d --force-recreate 300b-secu 300b-web 300b-siem 300b-bastion 300b-attacker
```

> ⚠️ 컨테이너 재생성 시 **컨테이너 내부 작업 데이터는 휘발됩니다** (홈 디렉토리, /tmp). 중요한 결과물은 사전에 호스트로 scp 백업.

### 10-2. Wazuh admin 비밀번호

```bash
docker exec -it wazuh-indexer bash
cd /usr/share/wazuh-indexer/plugins/opensearch-security/tools
./wazuh-passwords-tool.sh -a -au admin -ac SecretPassword -an admin -anp 'NewPass123!'
exit
docker compose restart wazuh-indexer wazuh-dashboard
```

### 10-3. Bastion API Key

`.env` 편집:
```dotenv
API_KEY=my-organization-key-2026
JWT_SECRET=my-jwt-secret
```

적용:
```bash
docker compose up -d --force-recreate 300b-bastion
```

### 10-4. DVWA admin

DVWA 내부 SQLite 또는 MySQL 직접. 학습 목적엔 default 유지를 권장.

---

## 11. 고급 — 네트워크 / 볼륨 / 로그

### 11-1. 컨테이너 네트워크 토폴로지

```
┌────────── Docker 호스트 (VM) ──────────┐
│                                         │
│  ┌── 300b-edu (172.30.30.0/24) ──┐     │
│  │  300b-attacker  ◄───┐         │     │
│  │  300b-web       ◄───┤ 학습 트래픽│  │
│  │  300b-secu      ◄───┤         │     │
│  │  juiceshop      ◄───┤         │     │
│  │  dvwa           ◄───┤         │     │
│  │  neobank/govportal/...        │     │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌── 300b-mgmt (172.30.40.0/24) ──┐    │
│  │  300b-bastion  ─── KG / API     │    │
│  │  300b-siem    ─── 로그 수집     │    │
│  │  wazuh-{indexer,manager,dashboard}│  │
│  │  300b-secu (양다리: edu+mgmt)   │    │
│  └─────────────────────────────────┘   │
└────────────────────────────────────────┘
```

### 11-2. 컨테이너 간 통신 확인

```bash
docker exec 300b-attacker ping -c1 neobank
docker exec 300b-attacker curl -s http://juiceshop:3000/ | head -1
docker exec 300b-bastion curl -sk -u admin:SecretPassword https://wazuh.indexer:9200/_cluster/health
```

### 11-3. 데이터 볼륨

| 볼륨 | 내용 | 영속성 |
|------|------|--------|
| `300b_300b-bastion-data` | bastion KG / evidence sqlite | ✅ 유지 |
| `300b_300b-bastion-playbooks` | 학생이 만든 playbook YAML | ✅ 유지 |
| `300b_300b-cti-data` | CVE / 뉴스 수집 결과 | ✅ 유지 |
| `300b_wazuh-indexer-data` | Wazuh 인덱스 (모든 보안 이벤트) | ✅ 유지 |
| `300b_wazuh-manager-{etc,logs,queue,var}` | Wazuh manager 상태 | ✅ 유지 |

`bash 300b.sh down` 은 **컨테이너만 정지** (볼륨 유지). `bash 300b.sh destroy` 는 **모든 데이터 삭제**.

### 11-4. 로그 위치

- 컨테이너 로그: `docker logs -f <컨테이너명>` 또는 `bash 300b.sh logs <서비스명>`
- Wazuh 보안 이벤트: Wazuh Dashboard → Security events
- Apache + ModSecurity (300b-web): `docker exec 300b-web tail -f /var/log/apache2/error.log`
- Suricata IDS (300b-secu): `docker exec 300b-secu tail -f /var/log/suricata/eve.json`
- bastion 자가 KG 로그: `docker exec 300b-bastion ls /opt/app/data`

### 11-5. 외부 LLM 연결 확인

```bash
docker exec 300b-bastion bash -c 'curl -s ${LLM_BASE_URL}/api/tags | head'
```
`models` 배열이 보이면 OK. 빈 응답이면 학교 GPU 서버 / 방화벽 점검.

---

## 12. 라이선스 / 윤리

- 본 환경의 취약 웹 사이트는 **모두 의도적으로 취약**합니다 — 외부 인터넷에 노출 금지.
- 공격 도구는 **본인이 소유하거나 명시적으로 허가된 시스템에만** 사용. 무단 침투는 형법 제 314조 위반.
- 실습 결과는 본인 학습 목적 외에 무단 공유·게시 금지.

---

## 도움말 / 문의

- README: [README.md](./README.md)
- GitHub Issues: https://github.com/mrgrit/300b/issues
- 강의 담당자: 강의 자료 참고

**행운을 빕니다 🛡️**
