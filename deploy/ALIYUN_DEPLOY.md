# AITradingHelper 生产发布手册

## 强制规则

生产服务器只有约 2 GB 内存，不允许在服务器运行：

- `docker build`、`docker compose build`、`docker-compose build`
- `npm install`、`npm ci`、`next build`
- `docker compose up --build`

正式发布统一使用 [`prebuilt_deploy.py`](./prebuilt_deploy.py)。它在本地构建两个带 Git SHA 的不可变镜像，或接收 GitHub Actions 已构建的压缩包，然后通过 SSH 上传。服务器只执行 `docker load`、`docker compose up --no-build`、健康检查和必要的自动回滚。

旧的 `remote_deploy.py` 仅保留用于追溯旧部署记录，已废弃，不得再用于生产发布。

## 路径与数据安全

- 生产目录固定为 `/opt/trade-review-agent`。
- `.env`、`work/`、`outputs/` 保留在宿主机，不打进镜像，也不会被发布脚本删除。
- API 密钥和 SSH 密码不得写入仓库、命令参数或日志。
- 当前和上一个发布镜像会保留，可用于回滚。

## 方案 A：有 Docker 的电脑直接发布

先提交全部改动，工作区必须干净。PowerShell 示例：

```powershell
$lines = Get-Content -LiteralPath "$env:USERPROFILE\Desktop\ssh.txt"
$env:DEPLOY_USER = $lines[0].Trim()
$env:DEPLOY_PASSWORD = $lines[1].Trim()
python deploy/prebuilt_deploy.py
Remove-Item Env:DEPLOY_PASSWORD
```

也可以让脚本直接读取本地凭据文件（第一行用户名、第二行密码）：

```powershell
$env:DEPLOY_SSH_FILE = "$env:USERPROFILE\Desktop\ssh.txt"
python deploy/prebuilt_deploy.py
```

凭据文件不会上传或写入仓库。

## 方案 B：本机没有 Docker（推荐当前环境）

推送 `main` 后，GitHub Actions 的 `Build prebuilt production images` 会为该提交生成工作流 Artifact，以及公共仓库的预发布 Release asset `aitrading-<完整SHA>.tar.gz` 和 SHA-256 文件。

从 GitHub Release 复制压缩包直链，然后执行：

```powershell
$env:DEPLOY_SSH_FILE = "$env:USERPROFILE\Desktop\ssh.txt"
python deploy/prebuilt_deploy.py `
  --tag <完整git-sha> `
  --release-url "https://github.com/wantedfast/AITradingHelper/releases/download/deploy-<完整git-sha>/aitrading-<完整git-sha>.tar.gz" `
  --sha256 <sha256值>
```

如果已经下载到本机：

```powershell
python deploy/prebuilt_deploy.py --archive C:\path\aitrading-<sha>.tar.gz --tag <完整git-sha>
```

使用 `--archive` 或 `--release-url` 时不需要本机安装 Docker。

## 发布与回滚流程

服务器端 [`remote_release.sh`](./remote_release.sh) 固定执行：

1. 获取排他发布锁，检查 `.env`、Docker、Compose 和磁盘空间。
2. 如果相同 Git SHA 已在线且前后端健康，直接成功返回，不重复重建容器。
3. 记录正在运行的 API、前端镜像。
4. `docker load` 加载不可变 Git SHA 镜像。
5. 使用 [`docker-compose.release.yml`](../docker-compose.release.yml) 执行 `up -d --no-build`。
6. 最多等待 120 秒，同时检查后端 `/api/health` 与前端首页。
7. 健康检查失败时自动切回发布前的两个镜像，并再次检查。
8. 成功后更新 current/previous 状态，并运行安全清理。

本地编排器通过独立的 systemd transient unit 执行远端切换。SSH、Codex
终端或操作者电脑意外断开时，服务器端发布仍会继续完成健康检查或自动回滚，
不会停在“旧容器已停止、新容器尚未启动”的中间状态。

同时兼容 Docker Compose v2（`docker compose`）与 v1（`docker-compose`）。

## 清理策略

[`remote_cleanup.sh`](./remote_cleanup.sh) 每日 03:17 运行，并在每次成功发布后运行一次：

- 保留当前和上一个版本的两个镜像；
- 只删除本项目带 `com.aitrading.managed=true` 标签的更旧镜像；
- 只清理停止超过 7 天的容器；
- 不删除卷、运行中容器、网络或全局构建缓存；
- 禁止 `docker image prune -af` 和 `docker builder prune`。

首次成功切换时，发布脚本会精准移除 root crontab 中原有的 `/usr/bin/docker image prune -af` 行，并保留其他 cron 项。仍需人工检查 `/etc/cron.d` 和 systemd timers 中是否存在另一份历史无差别清理任务，避免两套策略同时运行。

## 发布后检查

```bash
curl -fsS http://127.0.0.1:8600/api/health
curl -fsSI http://127.0.0.1:3000/ | head -n 1
docker ps --filter name=trade-review
cat /opt/trade-review-agent/.deploy/current-release
cat /opt/trade-review-agent/.deploy/previous-release
```

不要手工用 `latest` 覆盖镜像。每次发布必须对应一个可追踪的 Git SHA。
