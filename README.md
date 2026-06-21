# 足球赔率套利检测器

实时抓取 Polymarket、Kalshi、Smarkets 和竞彩胜平负赔率，按手续费后有效赔率计算足球套利机会。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env`。Kalshi 需要 API Key：

```text
KALSHI_API_KEY=你的 Kalshi API Key
```

未配置 `KALSHI_API_KEY` 时程序会跳过 Kalshi，不影响其他平台。

## 运行

单次扫描：

```powershell
python -m arbitrage.main --once
```

定时扫描：

```powershell
python -m arbitrage.main
```

只看未来五天 Smarkets 世界杯赛事：

```powershell
$env:MAX_KICKOFF_HOURS="120"
$env:SMARKETS_EVENT_SLUG_FILTER="world-cup"
python -m arbitrage.main --once
```

日志会写入 `logs/arbitrage_YYYYMMDD.jsonl` 和 `logs/odds_raw_YYYYMMDD.jsonl`。

## Polymarket 中文赔率网站

启动本地 Web 页面：

```powershell
$env:MAX_KICKOFF_HOURS="120"
$env:WEB_REFRESH_SECONDS="300"
python -m uvicorn arbitrage.web:app --host 0.0.0.0 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

页面只展示未来 5 天的 Polymarket 世界杯单场赔率，并与 **体育彩票** 对比胜平负、让球（主让/客让）等盘口。页面使用中文队名，并在队名旁展示国旗。后台每 5 分钟自动抓取更新一次，页面也会自动刷新。

阿里云 ECS 上同样运行上面的 `uvicorn` 命令，再用安全组放行 `8000` 端口，或用 `nginx` 把公网 `80` 端口反向代理到 `127.0.0.1:8000`。

## 注意

预测市场常见的“赢/不赢”二元市场与竞彩/Smarkets 的胜平负三向市场不是同一个结算结构。本项目会分别计算二向套利和三向套利，避免把“不赢”误当成“客胜”。

