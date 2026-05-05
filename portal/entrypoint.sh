#!/usr/bin/env bash
set -euo pipefail

/usr/local/bin/sshd_setup.sh

# sshd 백그라운드, FastAPI 포어그라운드.
/usr/sbin/sshd -e
echo "[portal] uvicorn :8005"
cd /opt/portal
exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8005 --workers 1
