from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    refresh_interval_seconds: int = int(os.getenv("REFRESH_INTERVAL_SECONDS", "60"))
    arbitrage_threshold: float = float(os.getenv("ARBITRAGE_THRESHOLD", "1.0"))
    min_kickoff_hours: int = int(os.getenv("MIN_KICKOFF_HOURS", "1"))
    max_kickoff_hours: int = int(os.getenv("MAX_KICKOFF_HOURS", "72"))
    fuzzy_match_threshold: int = int(os.getenv("FUZZY_MATCH_THRESHOLD", "85"))
    team_match_time_window_minutes: int = int(
        os.getenv("TEAM_MATCH_TIME_WINDOW_MINUTES", "30")
    )
    kalshi_api_key: str = os.getenv("KALSHI_API_KEY", "")
    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "15"))
    logs_dir: str = os.getenv("LOGS_DIR", "logs")
    stake_amount: float = float(os.getenv("STAKE_AMOUNT", "100"))
    smarkets_event_slug_filter: str = os.getenv("SMARKETS_EVENT_SLUG_FILTER", "")
    smarkets_event_delay_seconds: float = float(
        os.getenv("SMARKETS_EVENT_DELAY_SECONDS", "1.0")
    )
    http_proxy: str = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or ""


settings = Settings()

