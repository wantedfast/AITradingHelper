from __future__ import annotations

import os
import sys

import paramiko

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(
    os.environ.get("DEPLOY_HOST", "123.56.166.126"),
    port=int(os.environ.get("DEPLOY_PORT", "22")),
    username=os.environ.get("DEPLOY_USER", "root"),
    password=os.environ["DEPLOY_PASSWORD"],
    timeout=20,
)
command = os.environ.get("REMOTE_COMMAND") or " ".join(sys.argv[1:])
stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
stdin.close()
out = stdout.read().decode("utf-8", errors="replace")
err = stderr.read().decode("utf-8", errors="replace")
code = stdout.channel.recv_exit_status()
if out:
    print(out, end="")
if err:
    print(err, end="", file=sys.stderr)
ssh.close()
raise SystemExit(code)
