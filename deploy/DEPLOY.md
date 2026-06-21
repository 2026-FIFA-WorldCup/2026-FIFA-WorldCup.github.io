# 阿里云公网部署指南

## 你需要准备什么

| 项目 | 说明 |
|------|------|
| 阿里云 ECS | 建议 2核2G，Ubuntu 22.04，**大陆节点需 ICP 备案** |
| 域名 | 已在阿里云购买，需完成实名 |
| 备案（大陆 ECS） | 域名解析到大陆服务器前必须备案，约 1～2 周 |
| 安全组 | 放行 22（SSH）、80、443 |

> **香港/海外 ECS** 可免备案，但国内访问 Polymarket 更可能需要代理。

---

## 第一步：域名解析

1. 登录 [阿里云 DNS 控制台](https://dns.console.aliyun.com/)
2. 添加 **A 记录**：`@` → ECS 公网 IP
3. 可选：添加 `www` → 同一 IP

---

## 第二步：服务器初始化

SSH 登录 ECS 后执行：

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip nginx git

sudo mkdir -p /opt/fifa
sudo chown $USER:$USER /opt/fifa
```

上传代码（任选一种）：

```bash
# 方式 A：git
cd /opt/fifa && git clone <你的仓库地址> .

# 方式 B：本机 scp
# scp -r D:\DESKTOP\fifa\* root@<ECS_IP>:/opt/fifa/
```

安装依赖：

```bash
cd /opt/fifa
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp deploy/env.production.example .env
# 编辑 .env，如需 Polymarket 配置 HTTPS_PROXY
nano .env
```

---

## 第三步：systemd 常驻服务

```bash
sudo cp deploy/fifa-web.service.example /etc/systemd/system/fifa-web.service
# 确认 WorkingDirectory、User 路径正确
sudo systemctl daemon-reload
sudo systemctl enable --now fifa-web
sudo systemctl status fifa-web
```

本地验证：

```bash
curl http://127.0.0.1:8000/api/odds
```

---

## 第四步：Nginx + 域名

```bash
sudo cp deploy/nginx-site.conf.example /etc/nginx/sites-available/fifa
sudo nano /etc/nginx/sites-available/fifa   # 改 your-domain.com
sudo ln -sf /etc/nginx/sites-available/fifa /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

浏览器访问：`http://你的域名`

---

## 第五步：HTTPS（推荐）

**阿里云免费证书：**

1. 控制台 → SSL 证书 → 免费证书 → 申请
2. 域名验证通过后下载 Nginx 格式证书
3. 上传到服务器 `/etc/nginx/ssl/`
4. 修改 nginx 配置启用 `443 ssl`（见 `nginx-site.conf.example` 注释）
5. `sudo nginx -t && sudo systemctl reload nginx`

---

## 国内访问注意

| 数据源 | 国内 ECS |
|--------|----------|
| 体育彩票 | 通常正常 |
| Polymarket | 常被墙，需在 `.env` 配置 `HTTPS_PROXY` |
| 国旗 CDN | 依赖 `flagcdn.com`，慢时可换 `FLAG_CDN_BASE` |

测试 Polymarket 连通：

```bash
curl -I https://gamma-api.polymarket.com/events?limit=1
```

若失败，配置本机或服务器上的 HTTP 代理后再写入 `.env`：

```text
HTTPS_PROXY=http://127.0.0.1:7890
```

修改后：`sudo systemctl restart fifa-web`

---

## 日常运维

```bash
# 查看日志
sudo journalctl -u fifa-web -f

# 手动触发刷新
curl -X POST http://127.0.0.1:8000/api/refresh

# 更新代码后
cd /opt/fifa && git pull
source .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart fifa-web
```

---

## 最小检查清单

- [ ] 域名已备案（大陆 ECS）
- [ ] DNS A 记录指向 ECS
- [ ] 安全组 80/443 已开
- [ ] `fifa-web` 服务 running
- [ ] Nginx 反代正常
- [ ] HTTPS 已配置
- [ ] Polymarket 代理已测（如需）
