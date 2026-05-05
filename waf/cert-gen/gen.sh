#!/usr/bin/env bash
# 자체 CA + 9 server cert 생성 — waf entrypoint 가 ENABLE_TLS=true 일 때 1회 실행.
# AWS ACM (사설 CA) 시뮬레이션. 학생이 root CA 를 PC 에 import 하면 브라우저 경고 없음.
set -euo pipefail

CERT_DIR="${CERT_DIR:-/etc/ssl/300b}"
mkdir -p "${CERT_DIR}"
cd "${CERT_DIR}"

if [ -f ca.pem ]; then
    echo "[cert-gen] CA + 인증서 이미 존재 — skip."
    exit 0
fi

DOMAIN_BASE="${DOMAIN_BASE:-300b.lab}"
HOSTS=( landing juice dvwa neobank govportal mediforum admin ai wazuh bastion )

# Root CA
openssl genrsa -out ca.key 4096 2>/dev/null
openssl req -x509 -new -key ca.key -sha256 -days 3650 \
    -subj "/C=KR/ST=Seoul/O=300B Lab/CN=300B Self-Signed Root CA" \
    -out ca.pem 2>/dev/null

# 각 호스트 server cert
for h in "${HOSTS[@]}"; do
    if [ "$h" = "landing" ]; then
        SAN="DNS:${DOMAIN_BASE},DNS:localhost,DNS:300b,IP:127.0.0.1"
    else
        SAN="DNS:${h}.${DOMAIN_BASE},DNS:${h}"
    fi

    openssl genrsa -out "${h}.key" 2048 2>/dev/null
    openssl req -new -key "${h}.key" \
        -subj "/C=KR/ST=Seoul/O=300B Lab/CN=${h}.${DOMAIN_BASE}" \
        -out "${h}.csr" 2>/dev/null

    cat > "${h}.ext" <<EOF
subjectAltName=${SAN}
extendedKeyUsage=serverAuth
EOF

    openssl x509 -req -in "${h}.csr" -CA ca.pem -CAkey ca.key -CAcreateserial \
        -out "${h}.crt" -days 1825 -sha256 -extfile "${h}.ext" 2>/dev/null

    rm -f "${h}.csr" "${h}.ext"
done

# www 디렉토리에 ca.pem 복사 — landing page 에서 다운로드 링크 제공.
mkdir -p /var/www/landing
cp ca.pem /var/www/landing/300b-ca.crt 2>/dev/null || true

chmod 644 *.crt *.pem
chmod 600 *.key
echo "[cert-gen] 완료 — ${CERT_DIR} 에 root CA + ${#HOSTS[@]} 개 server cert."
ls "${CERT_DIR}"
