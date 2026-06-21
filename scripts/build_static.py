from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT))

from arbitrage.web import _match_to_dict, cache, refresh_cache, render_html  # noqa: E402


async def main() -> None:
    os.environ["STATIC_SITE"] = "1"
    await refresh_cache()
    DOCS.mkdir(exist_ok=True)

    html = render_html(cache)
    (DOCS / "index.html").write_text(html, encoding="utf-8")

    payload = {
        "updated_at": cache["updated_at"],
        "error": cache["error"],
        "refresh_seconds": cache["refresh_seconds"],
        "matches": [_match_to_dict(match) for match in cache["matches"]],
    }
    (DOCS / "odds.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Built {DOCS / 'index.html'} ({len(cache['matches'])} matches)")


if __name__ == "__main__":
    asyncio.run(main())
