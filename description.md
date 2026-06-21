# 足球赔率套利检测器 — 开发需求文档

> 本文档供 Cursor AI 直接生成代码使用，请严格按照规格实现。

---

## 项目概述

实时抓取四个平台的足球赔率，跨平台对比，自动计算是否存在无风险套利机会（Arbitrage）并发出提醒。

**目标平台：**
1. [Polymarket](https://polymarket.com) — 预测市场，API 可用
2. [Kalshi](https://kalshi.com) — 预测市场，API 可用
3. [Smarkets](https://smarkets.com/sport/football/) — 预测市场，API 可用
4. [足球胜平负](https://m.sporttery.cn/mjc/jsq/zqspf/) — 竞彩官网，需爬虫

---

## 套利逻辑说明

### 什么是无风险套利

对于一场比赛的胜/平/负三种结果，分别在不同平台选取最高赔率，计算：

```
套利指数 = 1/最高赔率(胜) + 1/最高赔率(平) + 1/最高赔率(负)
```

- 套利指数 **< 1.0** → 存在无风险套利，利润空间 = `(1 - 套利指数) × 100%`
- 套利指数 **≥ 1.0** → 无套利机会

### 最优下注比例计算

当套利成立时，各结果的最优投注比例为：

```
投注比例(结果X) = (1 / 最高赔率X) / 套利指数
```

例：投入总资金 $1000，按比例分配到三个结果，无论哪个结果发生都保证盈利。

---

## 数据获取方案

### 1. Polymarket

- **方式：** 官方 REST API（无需登录）
- **端点：** `https://gamma-api.polymarket.com/markets`
- **过滤条件：** `category=Sports`, `tag=Soccer`
- **赔率字段：** `outcomePrices`（数组，顺序对应 outcomes）
- **赔率格式：** 概率值（0~1），需转换为欧赔：`欧赔 = 1 / 概率`
- **比赛匹配字段：** `question` 字段包含球队名称

**示例请求：**
```
GET https://gamma-api.polymarket.com/markets?category=Sports&tag=Soccer&active=true&limit=100
```

**示例响应字段：**
```json
{
  "question": "Will Spain beat Saudi Arabia?",
  "outcomePrices": ["0.90", "0.10"],
  "outcomes": ["Yes", "No"],
  "endDate": "2026-06-22T00:00:00Z"
}
```

---

### 2. Kalshi

- **方式：** 官方 REST API（部分端点需要 API Key，足球赔率端点公开可用）
- **文档：** `https://trading-api.kalshi.com/docs`
- **端点：** `https://trading-api.kalshi.com/trade-api/v2/markets`
- **过滤条件：** `category=Sports`，关键字过滤 `soccer` 或 `football`
- **赔率字段：** `yes_ask` / `no_ask`（概率值 0~1），转换欧赔：`欧赔 = 1 / yes_ask`
- **认证：** 请求头加 `Authorization: Bearer <KALSHI_API_KEY>`，Key 从环境变量 `KALSHI_API_KEY` 读取；若无 Key 则跳过该平台并打印警告

**示例请求：**
```
GET https://trading-api.kalshi.com/trade-api/v2/markets?category=Sports&limit=100
Headers: Authorization: Bearer <KALSHI_API_KEY>
```

**示例响应字段：**
```json
{
  "title": "Spain to win vs Saudi Arabia",
  "yes_ask": 0.88,
  "no_ask": 0.12,
  "close_time": "2026-06-22T00:00:00Z"
}
```

---

### 3. Smarkets

- **方式：** 官方 REST API（公开，无需登录）
- **文档：** `https://api.smarkets.com/`
- **端点流程：**
  1. 获取足球赛事列表：`GET https://api.smarkets.com/v3/events/?type=football_match&state=upcoming&limit=100`
  2. 对每个 event，获取市场：`GET https://api.smarkets.com/v3/events/{event_id}/markets/`
  3. 获取赔率（报价）：`GET https://api.smarkets.com/v3/markets/{market_id}/quotes/`
- **赔率格式：** Smarkets 返回的是**百分比概率**（0~100），转换欧赔：`欧赔 = 100 / 概率`
- **市场类型过滤：** 只取 `market_type = "winner"` 的胜平负市场
- **合约名称映射：** `Home Win` → 主胜，`Draw` → 平，`Away Win` → 客胜

**示例请求：**
```
GET https://api.smarkets.com/v3/events/?type=football_match&state=upcoming&limit=100
GET https://api.smarkets.com/v3/markets/{market_id}/quotes/
```

---

### 4. 足球胜平负（竞彩）

- **方式：** requests + BeautifulSoup（移动端页面较简单）
- **目标 URL：** `https://m.sporttery.cn/mjc/jsq/zqspf/`
- **备用 API（优先尝试）：** 抓包查看是否有 XHR 接口，如有则直接请求 JSON
- **需要抓取的字段：**
  - 主队名（中文）、客队名（中文）
  - 开赛时间
  - 胜赔率、平赔率、负赔率
- **注意：** 竞彩赔率为浮动赔率，抓取时记录时间戳

---

## 球队名称匹配

四个平台的球队名称不同（英文/中文/缩写），需要统一映射。

**实现方式：**
1. 维护一个 `team_aliases.json` 映射表
2. 使用 `rapidfuzz` 库做模糊匹配（相似度阈值 > 85%）
3. 按开赛时间窗口匹配（±30分钟内视为同一场比赛）

**映射表示例：**
```json
{
  "spain": ["西班牙", "ESP", "Spain", "España"],
  "saudi_arabia": ["沙特", "KSA", "Saudi Arabia", "Saudi"],
  "brazil": ["巴西", "BRA", "Brazil"],
  "argentina": ["阿根廷", "ARG", "Argentina"]
}
```

---

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│                  调度器 (Scheduler)                   │
│              每 60 秒触发一次全量抓取                  │
└──────────┬──────────┬─────────────┬─────────────────┘
           │          │             │           │
    ┌──────▼──┐ ┌─────▼────┐ ┌─────▼────┐ ┌───▼──────────┐
    │Polymarket│ │  Kalshi  │ │ Smarkets │ │  竞彩官网    │
    │ fetcher  │ │ fetcher  │ │ fetcher  │ │  scraper     │
    └──────┬───┘ └─────┬────┘ └─────┬────┘ └───┬──────────┘
           │           │            │           │
           └───────────┴────────────┴───────────┘
                              │
                    ┌─────────▼────────┐
                    │   数据标准化      │
                    │   球队名匹配      │
                    └─────────┬────────┘
                              │
                    ┌─────────▼────────┐
                    │   套利计算引擎    │
                    └─────────┬────────┘
                              │
                    ┌─────────▼────────┐
                    │    结果输出       │
                    │ 终端 + 日志文件   │
                    └──────────────────┘
```

---

## 数据结构定义

### 标准化赔率对象
```python
@dataclass
class OddsEntry:
    platform: str          # "polymarket" | "kalshi" | "smarkets" | "sporttery"
    match_id: str          # 内部生成的唯一ID
    home_team: str         # 标准化主队名
    away_team: str         # 标准化客队名
    kickoff_time: datetime # 开赛时间 UTC
    odds_home: float       # 主队赢欧赔
    odds_draw: float       # 平局欧赔（若平台不提供则为 None）
    odds_away: float       # 客队赢欧赔
    fetched_at: datetime   # 抓取时间
```

### 套利机会对象
```python
@dataclass
class ArbitrageOpportunity:
    match_id: str
    home_team: str
    away_team: str
    kickoff_time: datetime

    best_odds_home: float
    best_odds_home_platform: str

    best_odds_draw: float
    best_odds_draw_platform: str

    best_odds_away: float
    best_odds_away_platform: str

    arbitrage_index: float      # < 1.0 表示有套利
    profit_margin: float        # (1 - arbitrage_index) * 100，单位 %

    # 投入 100 元时各结果的最优分配
    stake_home: float
    stake_draw: float
    stake_away: float
    guaranteed_return: float    # 保证回报（元）
```

---

## 输出格式

### 终端实时输出

**无套利时：**
```
[2026-06-21 14:32:01] 扫描完成 — 23 场比赛，无套利机会
```

**发现套利时：**
```
╔══════════════════════════════════════════════════════════╗
║  🎯 套利机会！利润率 2.3%                                  ║
╠══════════════════════════════════════════════════════════╣
║  比赛：西班牙 vs 沙特  |  开赛：2026-06-22 00:00 UTC      ║
╠══════════════════════════════════════════════════════════╣
║  结果    最高赔率  平台           投入$100时下注            ║
║  主胜    1.62     Kalshi         $38.2                   ║
║  平局    5.10     Polymarket     $12.4                   ║
║  客胜    4.20     竞彩           $49.4                   ║
╠══════════════════════════════════════════════════════════╣
║  套利指数：0.977   保证利润：$2.3（投入$100）              ║
╚══════════════════════════════════════════════════════════╝
```

### 日志文件

- 路径：`./logs/arbitrage_YYYYMMDD.jsonl`
- 格式：每行一个 JSON，记录每次发现的套利机会
- 同时保存所有平台原始赔率到 `./logs/odds_raw_YYYYMMDD.jsonl`

---

## 技术栈

| 用途 | 库 |
|---|---|
| HTTP 请求 | `httpx`（异步） |
| HTML 解析 | `beautifulsoup4` + `lxml` |
| 模糊字符串匹配 | `rapidfuzz` |
| 异步调度 | `asyncio` + `apscheduler` |
| 数据验证 | `pydantic` |
| 日志 | `loguru` |
| 终端美化 | `rich` |

---

## 项目结构

```
arbitrage/
├── main.py                  # 入口，启动调度器
├── config.py                # 配置（刷新间隔、阈值、API Key等）
├── fetchers/
│   ├── polymarket.py        # Polymarket API 抓取
│   ├── kalshi.py            # Kalshi API 抓取
│   ├── smarkets.py          # Smarkets API 抓取
│   └── sporttery.py         # 竞彩爬虫
├── core/
│   ├── normalizer.py        # 赔率标准化、球队名匹配
│   ├── calculator.py        # 套利计算引擎
│   └── matcher.py           # 跨平台比赛匹配
├── models.py                # 数据结构定义
├── display.py               # 终端输出格式化
├── team_aliases.json        # 球队名称映射表
├── logs/                    # 自动生成
├── .env                     # API Key 存放（不提交 git）
├── requirements.txt
└── README.md
```

---

## 配置项（config.py）

```python
REFRESH_INTERVAL_SECONDS = 60        # 抓取间隔
ARBITRAGE_THRESHOLD = 1.0            # 套利指数阈值，低于此值报警
MIN_KICKOFF_HOURS = 1                # 忽略1小时内开赛的比赛（来不及下注）
MAX_KICKOFF_HOURS = 72               # 只看72小时内的比赛
FUZZY_MATCH_THRESHOLD = 85           # 球队名模糊匹配阈值（0~100）
TEAM_MATCH_TIME_WINDOW_MINUTES = 30  # 开赛时间误差容忍窗口

# 从 .env 读取
KALSHI_API_KEY = os.getenv("KALSHI_API_KEY", "")  # 没有则跳过 Kalshi
```

---

## 注意事项

1. **Kalshi 需要 API Key**，从 `.env` 文件读取 `KALSHI_API_KEY`；若未配置则跳过该平台并在终端打印警告，不影响其他平台正常运行
2. **Smarkets 和 Polymarket 是预测市场**，赔率波动快，建议抓取后立即计算，不要缓存超过 30 秒
3. **竞彩赔率**是官方彩票赔率，合法但赔率相对较低
4. **平局赔率**：Kalshi 和 Polymarket 的足球市场通常只有「主队赢/不赢」两种结果，不单独列出平局；遇到此类市场，`odds_draw` 设为 `None`，套利计算时跳过该结果维度，改为只计算胜/负两向套利
5. 套利机会出现时间极短，建议发现后立即推送系统通知（macOS 用 `osascript`，Linux 用 `notify-send`）
6. 本工具仅用于信息参考，实际下注请遵守当地法律法规

---

## 手续费处理（重要）

> 竞彩官网赔率直接使用，不扣手续费。其余三个平台需要扣除手续费后才能参与套利计算。

### 各平台手续费结构

#### Polymarket — 动态 Taker Fee（基于概率曲线）

- **计费方式：** 按 taker（市价单）收费，limit 单（maker）免费
- **足球市场费率：** Sports 类，峰值 **0.75%**（发生在概率 50% 时）
- **费用公式：**
  ```
  fee = shares × feeRate × price × (1 - price)
  其中 feeRate = 0.03（Sports 类）
  ```
- **等效赔率换算：** 从 API 拿到概率 p 后，先扣费再转欧赔：
  ```python
  # p 是原始概率（0~1）
  fee_rate = 0.03
  effective_p = p - fee_rate * p * (1 - p)   # 扣除手续费后的有效概率
  effective_odds = 1 / effective_p             # 有效欧赔
  ```
- **注意：** 概率越接近 0 或 1，手续费越低；0.90 概率时实际费率约 0.27%

#### Kalshi — 动态 Taker Fee（同类公式）

- **计费方式：** Taker 收费，maker 免费或极低
- **峰值费率：** 约 **1.75%**（概率 50% 时），Sports 市场一般略低
- **费用公式（通用形式）：**
  ```
  fee = C × price × (1 - price) × feeMultiplier
  其中 feeMultiplier ≈ 0.07（需从 API 响应或官方 fee-schedule 确认具体市场）
  ```
- **等效赔率换算：**
  ```python
  fee_multiplier = 0.07  # 默认值，如 API 返回具体值则优先使用
  effective_p = p - fee_multiplier * p * (1 - p)
  effective_odds = 1 / effective_p
  ```
- **实现建议：** Kalshi API 的 `/markets` 响应中包含 `fee_multiplier` 字段，优先读取该字段；若缺失则使用默认值 0.07

#### Smarkets — 固定佣金（Net Winnings 的 2%）

- **计费方式：** 对**净盈利**收取 **2% 佣金**（亏损不收）
- **公式：**
  ```
  commission = (stake × odds - stake) × 0.02
  net_profit  = stake × odds - stake - commission
             = (stake × odds - stake) × 0.98
  ```
- **等效赔率换算：**
  ```python
  raw_odds = ...          # API 返回的原始欧赔
  effective_odds = 1 + (raw_odds - 1) * 0.98   # 扣除 2% 净利佣金后的有效赔率
  ```
- **例：** 原始赔率 5.0 → 有效赔率 = 1 + 4.0 × 0.98 = **4.92**

#### 竞彩官网

- **直接使用赔率，不做任何调整。**

---

### 套利计算时使用有效赔率

所有套利计算一律使用 `effective_odds`，不使用原始赔率：

```python
def compute_arbitrage(best_home, best_draw, best_away):
    """
    传入的已经是各平台扣费后的 effective_odds
    """
    index = 1/best_home + 1/best_draw + 1/best_away
    if index < 1.0:
        profit_margin = (1 - index) * 100
        return ArbitrageOpportunity(arbitrage_index=index, profit_margin=profit_margin, ...)
    return None
```

在终端输出套利机会时，同时显示**原始赔率**和**有效赔率**，方便用户核对：

```
║  结果  原始赔率  手续费后  平台           投入$100时下注  ║
║  主胜  1.65     1.62     Kalshi         $38.2          ║
║  平局  5.20     5.10     Polymarket     $12.4          ║
║  客胜  4.25     4.20     竞彩（无费）   $49.4          ║
```
