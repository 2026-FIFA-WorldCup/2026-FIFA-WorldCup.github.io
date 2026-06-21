# 体育彩票 + GitHub Pages 方案对比

GitHub Actions 在美国运行，**无法直连**体育彩票 API（WAF 567）。  
Polymarket 可在 GitHub 上自动更新；**体彩必须走国内网络**。

---

## 方案 A：本地定时 push 缓存（推荐，已实现）

**原理：** 你电脑在国内 → 定时抓体彩 → 更新 `data/sporttery_cache.json` → `git push` → GitHub 自动部署。

**一键同步：**

```powershell
cd D:\DESKTOP\fifa
.\scripts\sync_sporttery_to_github.ps1
```

**Windows 定时任务：**

1. `Win+R` → `taskschd.msc`
2. 创建基本任务 → 每 30 分钟或每小时
3. 操作：启动程序  
   - 程序：`powershell.exe`  
   - 参数：`-ExecutionPolicy Bypass -File "D:\DESKTOP\fifa\scripts\sync_sporttery_to_github.ps1"`

**优点：** 免费、简单、GitHub Pages 继续用  
**缺点：** 电脑要开机且联网（定时任务才会跑）

---

## 方案 B：GitHub Self-hosted Runner（本机当 CI）

**原理：** 在你电脑上装 GitHub Runner，工作流在**国内 IP** 执行，可直接抓体彩并 push。

仓库已有：`.github/workflows/update-sporttery-cache.yml`（`runs-on: self-hosted`）

**安装步骤：**

1. GitHub 仓库 → **Settings → Actions → Runners → New self-hosted runner**
2. 按页面命令在 Windows 上安装并 `./run.cmd`
3. 工作流每 30 分钟自动更新缓存并 push

**优点：** 全自动，不用手写定时 push  
**缺点：** 电脑需长期开机；Runner 进程要一直跑

---

## 方案 C：阿里云 ECS（国内服务器）

**原理：** 在国内 ECS 跑 `sync_sporttery_to_github.ps1` 或 cron + Python，定时 push。

**优点：** 7×24 稳定，不依赖个人电脑  
**缺点：** 需买 ECS（最便宜约几十元/月）；域名需备案（若用大陆节点）

---

## 方案 D：GitHub Actions + 国内 HTTP 代理

在仓库 **Settings → Secrets** 添加：

```text
HTTPS_PROXY = http://你的国内代理:端口
```

`pages.yml` 已支持该变量（仅 Polymarket 走代理；体彩仍建议用缓存）。

**优点：** 全在 GitHub 云端  
**缺点：** 需稳定国内代理，配置稍麻烦

---

## 当前网站数据流

```
Polymarket  ──► GitHub Actions（美国）──► 自动每 15 分钟
体育彩票    ──► 国内网络（本机/ECS）──► data/sporttery_cache.json ──► git push
                                              │
                                              ▼
                              https://2026-fifa-worldcup.github.io/
```

---

## 建议

| 你的情况 | 推荐 |
|---------|------|
| 个人用、电脑常开 | **方案 A** 定时任务 |
| 想完全自动化、电脑常开 | **方案 B** Self-hosted Runner |
| 要 7×24、愿意花一点钱 | **方案 C** 阿里云 cron |
| 有代理 | **方案 D** |

**不是「GitHub 就没法显示体彩」**——是「体彩不能在美国服务器上抓」，用国内缓存同步即可正常显示。
