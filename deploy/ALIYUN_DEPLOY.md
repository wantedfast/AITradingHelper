# 阿里云部署说明

这个项目是一个 Python/Streamlit Web 应用，需要能长期运行后端服务。最推荐部署在阿里云 ECS 或轻量应用服务器。

如果你只买了域名或静态网站托管，不能直接运行这个项目；需要再买一台云服务器，或改用支持 Python 容器的平台。

## 1. 服务器准备

推荐配置：

- Ubuntu 22.04
- 2 核 4G 起步
- 系统盘 40G+
- 安全组开放 `80`、`443`，临时调试可开放 `8501`

安装 Docker：

```bash
curl -fsSL https://get.docker.com | bash
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
```

重新登录 SSH 后确认：

```bash
docker --version
docker compose version
```

## 2. 上传项目

在服务器上创建目录：

```bash
mkdir -p /opt/trade-review-agent
cd /opt/trade-review-agent
```

把本项目目录上传到这里。可以用 `scp`、宝塔面板、Xftp，或者 Git 仓库。

项目根目录里应该能看到：

```text
app.py
requirements.txt
Dockerfile
docker-compose.yml
trade_review_agent/
```

## 3. 启动应用

```bash
cd /opt/trade-review-agent
docker compose up -d --build
docker compose logs -f
```

本机测试：

```bash
curl http://127.0.0.1:8501/_stcore/health
```

如果阿里云安全组开放了 `8501`，也可以先访问：

```text
http://你的服务器公网IP:8501
```

## 4. 绑定域名

在阿里云域名 DNS 里添加：

```text
A 记录
主机记录: @ 或 review
记录值: 你的服务器公网 IP
```

如果用 `review.example.com`，主机记录填 `review`。

## 5. Nginx 反向代理

安装 Nginx：

```bash
sudo apt update
sudo apt install -y nginx
```

复制配置：

```bash
sudo cp deploy/nginx-trade-review-agent.conf /etc/nginx/sites-available/trade-review-agent
sudo ln -s /etc/nginx/sites-available/trade-review-agent /etc/nginx/sites-enabled/trade-review-agent
```

编辑域名：

```bash
sudo nano /etc/nginx/sites-available/trade-review-agent
```

把：

```nginx
server_name your-domain.com;
```

改成你的真实域名，例如：

```nginx
server_name review.example.com;
```

检查并重启：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

现在访问：

```text
http://你的域名
```

## 6. HTTPS

安装证书工具：

```bash
sudo apt install -y certbot python3-certbot-nginx
```

签发证书：

```bash
sudo certbot --nginx -d 你的域名
```

之后访问：

```text
https://你的域名
```

## 7. 常用维护命令

查看日志：

```bash
docker compose logs -f
```

重启：

```bash
docker compose restart
```

更新代码后重新构建：

```bash
docker compose up -d --build
```

停止：

```bash
docker compose down
```

## 8. 数据目录

成交记录、截图、缓存和报告会保存在宿主机：

```text
work/
outputs/
```

这两个目录已经在 `docker-compose.yml` 里做了挂载，容器重建后不会丢。
