from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from arbitrage.config import settings
from arbitrage.models import ArbitrageOpportunity, OddsEntry


def write_scan_logs(
    entries: list[OddsEntry], opportunities: list[ArbitrageOpportunity]
) -> None:
    logs_dir = Path(settings.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    date_part = datetime.now().strftime("%Y%m%d")

    raw_path = logs_dir / f"odds_raw_{date_part}.jsonl"
    with raw_path.open("a", encoding="utf-8") as file:
        for entry in entries:
            file.write(json.dumps(entry.to_json_dict(), ensure_ascii=False) + "\n")

    if not opportunities:
        return

    arbitrage_path = logs_dir / f"arbitrage_{date_part}.jsonl"
    with arbitrage_path.open("a", encoding="utf-8") as file:
        for opportunity in opportunities:
            file.write(json.dumps(opportunity.to_json_dict(), ensure_ascii=False) + "\n")

