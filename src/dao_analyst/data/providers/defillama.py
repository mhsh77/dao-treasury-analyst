"""DefiLlama historical prices (no API key). One price per UTC day.

Definition used everywhere: the daily price for day D is DefiLlama's price nearest to
D 00:00 UTC, searched within +/- SEARCH_WIDTH. Days with no point in that window have no
price, and anything that needs one reports token amounts only.

We use ``/batchHistorical`` with explicit midnight timestamps rather than ``/chart``: the
chart endpoint skips days irregularly, which left ~14% of days unpriced.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from dao_analyst.data.fetch import JsonFetcher
from dao_analyst.data.providers.base import DailyPrice

NAMESPACE = "defillama"
SEARCH_WIDTH = "6h"
SOURCE = f"DefiLlama coins API, price nearest 00:00 UTC (+/-{SEARCH_WIDTH}), pinned snapshot"
DAYS_PER_REQUEST = 150


def midnight(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())


class DefiLlamaPriceProvider:
    def __init__(self, fetcher: JsonFetcher, base_url: str = "https://coins.llama.fi") -> None:
        self._fetcher = fetcher
        self._base_url = base_url

    def daily_prices(self, price_id: str, start: date, end: date) -> list[DailyPrice]:
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        out: list[DailyPrice] = []
        for i in range(0, len(days), DAYS_PER_REQUEST):
            chunk = days[i : i + DAYS_PER_REQUEST]
            data = self._fetcher.get(
                NAMESPACE,
                f"{self._base_url}/batchHistorical",
                {
                    "coins": json.dumps({price_id: [midnight(d) for d in chunk]}),
                    "searchWidth": SEARCH_WIDTH,
                },
                {},
            )
            points = data.get("coins", {}).get(price_id, {}).get("prices", [])
            for day in chunk:
                target = midnight(day)
                best = min(points, key=lambda p: abs(int(p["timestamp"]) - target), default=None)
                if best is not None and abs(int(best["timestamp"]) - target) <= 6 * 3600:
                    out.append(DailyPrice(price_id, day, float(best["price"]), SOURCE))
        return out
