from __future__ import annotations

from datetime import datetime

from rich.console import Console
from rich.table import Table

from arbitrage.models import ArbitrageOpportunity, BestOutcome


console = Console()


def print_scan_summary(scanned_matches: int, opportunities: list[ArbitrageOpportunity]) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not opportunities:
        console.print(f"[{timestamp}] 扫描完成 - {scanned_matches} 场比赛，无套利机会")
        return

    console.print(
        f"[{timestamp}] 扫描完成 - {scanned_matches} 场比赛，发现 "
        f"{len(opportunities)} 个套利机会"
    )
    for opportunity in opportunities:
        print_opportunity(opportunity)


def print_opportunity(opportunity: ArbitrageOpportunity) -> None:
    title = (
        f"套利机会 | 利润率 {opportunity.profit_margin:.2f}% | "
        f"{'三向' if opportunity.market_type == 'three_way' else '二向'}"
    )
    table = Table(title=title, show_lines=True)
    table.add_column("结果")
    table.add_column("原始赔率", justify="right")
    table.add_column("手续费后", justify="right")
    table.add_column("平台")
    table.add_column("投入时下注", justify="right")
    table.add_column("下单链接")

    rows = [("主胜", opportunity.best_home)]
    if opportunity.best_draw:
        rows.append(("平局", opportunity.best_draw))
    if opportunity.best_away:
        rows.append(("客胜", opportunity.best_away))
    if opportunity.best_not_home:
        rows.append(("主队不赢", opportunity.best_not_home))

    for label, outcome in rows:
        table.add_row(
            label,
            f"{outcome.raw_odds:.3f}",
            f"{outcome.effective_odds:.3f}",
            outcome.platform,
            f"{outcome.stake:.2f}",
            outcome.source_url or "-",
        )

    kickoff = opportunity.kickoff_time.strftime("%Y-%m-%d %H:%M UTC")
    console.print(f"\n[bold]{opportunity.home_team} vs {opportunity.away_team}[/bold] | {kickoff}")
    console.print(table)
    console.print(
        f"套利指数：{opportunity.arbitrage_index:.4f} | "
        f"投入总额保证回报：{opportunity.guaranteed_return:.2f}\n"
    )
    _print_order_links(rows)


def _print_order_links(rows: list[tuple[str, BestOutcome]]) -> None:
    seen: set[tuple[str, str]] = set()
    print("下单链接：")
    for label, outcome in rows:
        if not outcome.source_url:
            continue
        key = (outcome.platform, outcome.source_url)
        if key in seen:
            continue
        seen.add(key)
        print(f"- {label} / {outcome.platform}: {outcome.source_url}")
    print()

