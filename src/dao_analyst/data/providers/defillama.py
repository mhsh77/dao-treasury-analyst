"""DefiLlama historical prices (no API key). One price per UTC day.

The chart endpoint returns at most 500 points per request, so long windows are chunked.
DefiLlama's daily points are not exactly at midnight; we bucket each point by its UTC date
and keep the earliest point of each day.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from dao_analyst.data.fetch import JsonFetcher
from dao_analyst.data.providers.base import DailyPrice

NAMESPACE = "defillama"
SOURCE = "DefiLlama coins API (daily, pinned snapshot)"
MAX_SPAN_DAYS = 400


class DefiLlamaPriceProvider:
    def __init__(self, fetcher: JsonFetcher, base_url: str = "https://coins.llama.fi") -> None:
        self._fetcher = fetcher
        self._base_url = base_url

    def daily_prices(self, price_id: str, start: date, end: date) -> list[DailyPrice]:
        by_day: dict[date, tuple[int, float]] = {}
        chunk_start = start
        while chunk_start <= end:
            span = min(MAX_SPAN_DAYS, (end - chunk_start).days + 1)
            ts = int(
                datetime(
                    chunk_start.year, chunk_start.month, chunk_start.day, tzinfo=UTC
                ).timestamp()
            )
            data = self._fetcher.get(
                NAMESPACE,
                f"{self._base_url}/chart/{price_id}",
                {"start": ts, "span": span, "period": "1d"},
                {},
            )
            points = data.get("coins", {}).get(price_id, {}).get("prices", [])
            for p in points:
                t = int(p["timestamp"])
                day = datetime.fromtimestamp(t, tz=UTC).date()
                if start <= day <= end and (day not in by_day or t < by_day[day][0]):
                    by_day[day] = (t, float(p["price"]))
            chunk_start += timedelta(days=span)
        return [DailyPrice(price_id, d, by_day[d][1], SOURCE) for d in sorted(by_day)]
