from __future__ import annotations

import os
import shlex
import sys
import time

import paramiko


HOST = os.environ.get("DEPLOY_HOST", "123.56.166.126")
PORT = int(os.environ.get("DEPLOY_PORT", "22"))
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ["DEPLOY_PASSWORD"]
REMOTE_DIR = os.environ.get("DEPLOY_REMOTE_DIR", "/opt/trade-review-agent")
REPO_URL = os.environ.get("DEPLOY_REPO_URL", "https://github.com/wantedfast/AITradingHelper.git")
BRANCH = os.environ.get("DEPLOY_BRANCH", "main")

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
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20)

    repo_url = shlex.quote(REPO_URL)
    branch = shlex.quote(BRANCH)
    remote_dir = shlex.quote(REMOTE_DIR)
    deploy = f"""
set -e
export DEBIAN_FRONTEND=noninteractive
mkdir -p {remote_dir}
cd {remote_dir}

if ! command -v git >/dev/null 2>&1; then
  apt-get update
  apt-get install -y git
fi

if [ ! -d .git ]; then
  find . -mindepth 1 -maxdepth 1 ! -name '.env' ! -name 'work' ! -name 'outputs' -exec rm -rf {{}} +
  git init
  git remote add origin {repo_url}
fi

git remote set-url origin {repo_url}
git fetch origin {branch}
git checkout -B {branch} origin/{branch}
git reset --hard origin/{branch}
git clean -fd -e .env -e work/ -e outputs/

mkdir -p work outputs
if [ ! -f .env ]; then
  echo 'ERROR: .env is missing on server; refusing to start deployment.' >&2
  exit 2
fi
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
git rev-parse HEAD
for attempt in $(seq 1 60); do
  if curl -fsS --max-time 5 http://127.0.0.1:8600/api/health >/dev/null; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    echo 'ERROR: backend health check did not pass after deployment.' >&2
    $COMPOSE -f docker-compose.prod.yml ps >&2 || true
    $COMPOSE -f docker-compose.prod.yml logs --tail=120 trade-review-api >&2 || true
    exit 3
  fi
  sleep 2
done
"""
    run(ssh, "bash -lc " + shlex.quote(deploy), timeout=None)
    run(ssh, "curl -fsSI --max-time 10 http://127.0.0.1/ | head -n 1")
    run(ssh, "curl -fsS --max-time 10 http://127.0.0.1/api/health")
    ssh.close()


if __name__ == "__main__":
    main()
