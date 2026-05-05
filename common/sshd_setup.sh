#!/usr/bin/env bash
# 모든 코어 컨테이너에서 공통으로 호출되는 sshd 부트스트랩.
# - openssh-server 설치는 각 Dockerfile 에서 수행.
# - 이 스크립트는 entrypoint 시점에 호출되어 사용자/암호/호스트키를 보장.
set -euo pipefail

SSH_USER="${SSH_USER:-ccc}"
SSH_PASS="${SSH_PASS:-ccc}"

mkdir -p /var/run/sshd /run/sshd

# 호스트키 — 컨테이너 첫 부팅 시 1회만 생성.
if ! ls /etc/ssh/ssh_host_*_key >/dev/null 2>&1; then
    ssh-keygen -A
fi

# 사용자 보장 (uid 1000 충돌 회피).
if ! id "$SSH_USER" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "$SSH_USER"
    usermod -aG sudo "$SSH_USER" 2>/dev/null || true
    echo "$SSH_USER ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/99-ccc
    chmod 440 /etc/sudoers.d/99-ccc
fi
echo "${SSH_USER}:${SSH_PASS}" | chpasswd

# root 도 학습용으로 동일 암호 (학생이 sudo 막힐 때 백도어용).
echo "root:${SSH_PASS}" | chpasswd

# sshd 설정 — 학습용이라 비밀번호 로그인 허용.
sed -ri 's/^#?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -ri 's/^#?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
grep -q '^UsePAM' /etc/ssh/sshd_config || echo 'UsePAM yes' >> /etc/ssh/sshd_config
