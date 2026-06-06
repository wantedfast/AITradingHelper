from __future__ import annotations

import os
import shlex
import sys
import time
from pathlib import Path

import paramiko


HOST = os.environ.get("DEPLOY_HOST", "123.56.166.126")
PORT = int(os.environ.get("DEPLOY_PORT", "22"))
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ["DEPLOY_PASSWORD"]
LOCAL_PACKAGE = Path(os.environ["DEPLOY_PACKAGE"]).resolve()
LOCAL_ENV = Path(os.environ["DEPLOY_ENV"]).resolve()
REMOTE_DIR = os.environ.get("DEPLOY_REMOTE_DIR", "/opt/trade-review-agent")
REMOTE_PACKAGE = "/tmp/trade-review-agent-deploy.tar.gz"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def run(ssh: paramiko.SSHClient, command: str, timeout: int | None = None) -> None:
    print(f"\n$ {command}")
    stdin, stdout, stderr = ssh.exec_command(command, get_pty=True, timeout=timeout)
    stdin.close()
    while not stdout.channel.exit_status_ready():
        out = stdout.channel.recv(4096) if stdout.channel.recv_ready() else b""
        err = stderr.channel.recv(4096) if stderr.channel.recv_stderr_ready() else b""
        if out:
            sys.stdout.write(out.decode("utf-8", errors="replace"))
            sys.stdout.flush()
        if err:
            sys.stderr.write(err.decode("utf-8", errors="replace"))
            sys.stderr.flush()
        time.sleep(0.2)
    out = stdout.read()
    err = stderr.read()
    if out:
        sys.stdout.write(out.decode("utf-8", errors="replace"))
    if err:
        sys.stderr.write(err.decode("utf-8", errors="replace"))
    code = stdout.channel.recv_exit_status()
    if code != 0:
        raise RuntimeError(f"command failed with exit code {code}: {command}")


def main() -> None:
    if not LOCAL_PACKAGE.exists():
        raise FileNotFoundError(LOCAL_PACKAGE)
    if not LOCAL_ENV.exists():
        raise FileNotFoundError(LOCAL_ENV)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20)
    sftp = ssh.open_sftp()

    run(ssh, f"mkdir -p {shlex.quote(REMOTE_DIR)}")
    print(f"upload {LOCAL_PACKAGE} -> {REMOTE_PACKAGE}")
    sftp.put(str(LOCAL_PACKAGE), REMOTE_PACKAGE)
    print(f"upload {LOCAL_ENV.name} -> {REMOTE_DIR}/.env")
    sftp.put(str(LOCAL_ENV), f"{REMOTE_DIR}/.env")
    sftp.close()

    deploy = f"""
set -e
export DEBIAN_FRONTEND=noninteractive
mkdir -p {shlex.quote(REMOTE_DIR)}
tar -xzf {shlex.quote(REMOTE_PACKAGE)} -C {shlex.quote(REMOTE_DIR)}
cd {shlex.quote(REMOTE_DIR)}
mkdir -p work outputs
chmod 600 .env
if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y docker.io docker-compose
  systemctl enable --now docker || service docker start || true
fi
if docker compose version >/dev/null 2>&1; then
  COMPOSE='docker compose'
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE='docker-compose'
else
  apt-get update
  apt-get install -y docker-compose
  COMPOSE='docker-compose'
fi
docker rm -f trade-review-frontend trade-review-api trade-review-agent trade-review-streamlit 2>/dev/null || true
rm -rf outputs/streamlit_reports
rm -f docker-compose.yml docker-compose.v2.yml frontend-v2.tar.gz frontend-v2.tar.gz.b64
$COMPOSE -f docker-compose.prod.yml up -d --build
cat >/etc/nginx/sites-available/trade-review-agent <<'NGINX'
server {{
    listen 80;
    server_name _;
    client_max_body_size 100M;

    location /api/ {{
        proxy_pass http://127.0.0.1:8600/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }}

    location / {{
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }}
}}
NGINX
ln -sf /etc/nginx/sites-available/trade-review-agent /etc/nginx/sites-enabled/trade-review-agent
nginx -t
systemctl reload nginx || service nginx reload
$COMPOSE -f docker-compose.prod.yml ps
"""
    run(ssh, "bash -lc " + shlex.quote(deploy), timeout=None)
    run(ssh, "curl -I --max-time 10 http://127.0.0.1/ | head -n 1")
    run(ssh, "curl -s --max-time 10 http://127.0.0.1/api/health")
    ssh.close()


if __name__ == "__main__":
    main()
