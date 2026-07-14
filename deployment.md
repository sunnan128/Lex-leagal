# 部署方案

LexAI 法律智能检索系统的多种部署方式，满足从个人使用到企业级访问的不同需求。

---

## 方案对比

| 方案 | 成本 | 复杂度 | 同事访问 | 你关机还能用 | 适用场景 |
|------|------|--------|---------|------------|---------|
| 本地运行 | 0 | 0 | ❌ 仅本机 | ❌ | 个人测试 |
| 内网共享 | 0 | 低 | ✅ 同办公室 | ❌ | 小团队内网 |
| Tailscale 组网 | 免费 | 低 | ✅ 任何地方 | ❌ | 远程办公 |
| 云服务器 | ~50~80元/月 | 中 | ✅ 任何地方 | ✅ **不受影响** | 正式上线 |
| 内网穿透 | ~0~30元/月 | 中 | ✅ 任何地方 | ❌ | 临时方案 |

---

## 方案一：内网共享（零成本）

### 原理

后端绑定 `0.0.0.0`，公司局域网内的其他设备直接访问你的 IP 地址。

### 实施步骤

**① 查看本机局域网 IP**

```bash
ipconfig | findstr "IPv4"
```

输出类似：
```
IPv4 地址 . . . . . . . . . : 192.168.40.43  ← 这个就是
```

**② 防火墙放行端口**

以管理员身份运行 PowerShell：

```powershell
New-NetFirewallRule -DisplayName "LexAI-API" -Direction Inbound -Protocol TCP -LocalPort 8002 -Action Allow
New-NetFirewallRule -DisplayName "LexAI-Frontend" -Direction Inbound -Protocol TCP -LocalPort 8501 -Action Allow
```

**③ 启动后端**

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**④ 告诉同事**

浏览器打开 `http://192.168.40.43:8501` 即可使用。

### 局限

- 你的电脑关机/休眠 → 服务停用
- 你带电脑回家 → 同事无法连接
- 仅限于同一局域网

---

## 方案二：Tailscale 组网（零成本，远程可用）

### 原理

Tailscale 基于 WireGuard 协议创建虚拟局域网，你和同事的设备加入同一个网络后，无论在哪都能像在内网一样互相访问。

### 实施步骤

**① 注册 Tailscale**

打开 https://tailscale.com，用公司邮箱注册（免费版支持 3 人，个人邮件最高 100 台设备）。

**② 你的电脑和同事都安装 Tailscale 客户端**

- Windows: [tailscale.com/download](https://tailscale.com/download)
- 安装后登录同一账号，会自动分配一个 `100.x.x.x` 的虚拟 IP

**③ 防火墙放行端口**（同上方案一步骤②）

**④ 启动服务**

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8002 --reload
python -m streamlit run frontend/app.py --server.port 8501 --server.headless true
```

**⑤ 同事访问**

在 Tailscale 中查看你设备的虚拟 IP（例如 `100.85.23.17`），然后：
`http://100.85.23.17:8501`

### 局限

- 你的电脑仍需开机
- 免费版有设备数量限制

---

## 方案三：云服务器部署（推荐，真正 7×24）

### 架构图

```
                         ┌──────────────────┐
                         │   Cloud Server   │
                         │  (Ubuntu 22.04)  │
                         │                  │
 用户 ──HTTPS──→ Nginx ──→  Frontend:8501  │
  (任何地方)      :443   │      │           │
                         │      ↓          │
                         │  Backend:8002   │
                         │      │          │
                         │  ChromaDB(磁盘)  │
                         └──────────────────┘
```

### 3.1 购买云服务器

推荐配置：

| 云厂商 | 配置 | 价格 | 备注 |
|--------|------|------|------|
| 腾讯云轻量 | 2核2G·50GB SSD | ~50元/月 | 性价比最高 |
| 阿里云 ECS | 2核2G·40GB | ~60元/月 | 稳定 |
| 华为云 HECS | 2核2G·40GB | ~50元/月 | 新用户优惠多 |

系统选择 **Ubuntu 22.04**。

### 3.2 一键部署脚本

登录云服务器后，依次执行：

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Python 和依赖
sudo apt install -y python3 python3-pip python3-venv nginx git

# 克隆项目（或在本地打包上传）
git clone https://github.com/your-org/legal-qa-system.git
cd legal-qa-system

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 配置环境变量
cat > .env << 'EOF'
OPENAI_API_KEY=sk-你的key
OPENAI_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5
EOF

# 下载嵌入模型（首次需要联网）
python download_model.py
```

### 3.3 配置 Nginx 反向代理

```bash
sudo tee /etc/nginx/sites-available/legal-qa << 'EOF'
server {
    listen 80;
    server_name your-domain.com;  # 换成你的域名

    # 前端
    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    # 后端 API
    location /api/ {
        rewrite ^/api/(.*) /$1 break;
        proxy_pass http://127.0.0.1:8002;
        proxy_set_header Host $host;
    }
}
EOF

# 启用配置
sudo ln -s /etc/nginx/sites-available/legal-qa /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 3.4 配置 HTTPS（免费证书）

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

证书自动续期（certbot 已内置定时任务）。

### 3.5 配置 systemd 开机自启

```bash
sudo tee /etc/systemd/system/legal-qa-backend.service << 'EOF'
[Unit]
Description=LexAI Backend
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/legal-qa-system
ExecStart=/home/ubuntu/legal-qa-system/venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8002
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/legal-qa-frontend.service << 'EOF'
[Unit]
Description=LexAI Frontend
After=legal-qa-backend.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/legal-qa-system
ExecStart=/home/ubuntu/legal-qa-system/venv/bin/streamlit run frontend/app.py --server.port 8501 --server.headless true --server.address 127.0.0.1
Restart=always
RestartSec=5

[Environment]="STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable legal-qa-backend legal-qa-frontend
sudo systemctl start legal-qa-backend legal-qa-frontend
```

### 3.6 添加访问认证（可选）

Nginx 配置基本认证，防止未授权访问：

```bash
# 创建密码文件
sudo apt install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd admin  # 会提示输入密码

# Nginx 配置增加 auth 指令
sudo tee /etc/nginx/sites-available/legal-qa << 'EOF'
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # 基本认证
    auth_basic "LexAI - 请输入账号密码";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    location /api/ {
        rewrite ^/api/(.*) /$1 break;
        proxy_pass http://127.0.0.1:8002;
        proxy_set_header Host $host;
    }
}
EOF

sudo nginx -t && sudo systemctl reload nginx
```

---

## 方案四：Docker 部署（云服务器进阶）

如果希望环境完全隔离，用 Docker 部署：

### 安装 Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
```

### 使用现有 docker-compose

```bash
cd legal-qa-system

# 编辑 .env 填入你的 API key
# 然后启动
sudo docker-compose up -d
```

### 配合 Nginx 反向代理

同上方案三，Nginx 代理到 Docker 容器的端口。

---

## 数据迁移

如果你已经在本地跑了一段时间，有积累的文档数据，迁移到云服务器：

```bash
# 本地打包数据
cd legal-qa-system
tar czf data_backup.tar.gz backend/data/

# 传到云服务器
scp data_backup.tar.gz ubuntu@your-server-ip:~

# 云服务器解压
cd legal-qa-system
tar xzf ~/data_backup.tar.gz
```

---

## 成本估算

| 项目 | 月费用 | 年费用 |
|------|--------|--------|
| 云服务器（2核2G） | ~50元 | ~600元 |
| 域名（.com/.cn） | 一次性 | ~50元/年 |
| DeepSeek API | 按量 | 少量文档≈0元 |
| **合计** | **~50元** | **~650元** |

---

## 面试话术参考

> **面试官问：这个项目怎么部署的？**
>
> "我出了三套方案。小团队内网直接用局域网 IP 共享就行，零成本。如果需要远程访问，可以用 Tailscale 组网，免费版支持 3 人。正式上线的话，我推荐腾讯云轻量服务器，2核2G配 Nginx 反向代理 + HTTPS，加上 systemd 守护进程保证开机自启和崩溃恢复。整套部署脚本我都写好了，从买服务器到上线大概半小时就能搞定。"
>
> **面试官问：多人同时用会有问题吗？**
>
> "目前的设计是单机部署，Streamlit 本身不支持真正的多用户并行，但小团队（5~10 人）同时使用基本没问题。如果要支持更大的并发，可以把后端拆成独立的 FastAPI 服务 + 前端用 Vue/React 重写，再加一层 Redis 缓存和负载均衡。"

---

## 安全注意事项

1. **API Key 保护**：`.env` 文件不要提交到 Git，已在 `.gitignore` 中排除
2. **HTTPS 必开**：暴露到公网必须配 HTTPS，防止 API Key 和文档内容被截获
3. **访问认证**：Nginx 基本认证是最低要求，生产环境建议用 OAuth2 / LDAP
4. **数据备份**：`backend/data/` 目录定期备份，包含向量库和原始文档
5. **防火墙**：云服务器安全组只开放 80/443 端口，内部服务绑定 `127.0.0.1`
