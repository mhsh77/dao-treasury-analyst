from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

from dao_analyst.data.providers.defillama import DefiLlamaPriceProvider
from dao_analyst.data.providers.rpc import RpcBalanceProvider
from tests.conftest import TREASURY, UNI, FakeFetcher


def ts(d: date, hour: int = 0) -> int:
    return int(datetime(d.year, d.month, d.day, hour, tzinfo=UTC).timestamp())


def test_prices_use_point_nearest_midnight_and_chunk_requests() -> None:
    def handler(ns: str, url: str, params: dict[str, Any]) -> dict[str, Any]:
        assert url.endswith("/batchHistorical")
        stamps = json.loads(params["coins"])["coingecko:uniswap"]
        points = []
        for i, t in enumerate(stamps):
            if i % 10 == 9:
                continue  # a day DefiLlama has no data for
            points.append({"timestamp": t - 1, "price": 1.0 + i})  # 23:59:59 the day before
            points.append({"timestamp": t + 5 * 3600, "price": 99.0})  # farther from midnight
        return {"coins": {"coingecko:uniswap": {"prices": points}}}

    f = FakeFetcher(handler)
    prices = DefiLlamaPriceProvider(f).daily_prices(
        "coingecko:uniswap", date(2024, 1, 1), date(2024, 12, 31)
    )
    assert len(f.calls) == 3  # 366 days in chunks of 150
    by_day = {p.day: p.usd for p in prices}
    assert by_day[date(2024, 1, 1)] == 1.0  # nearest point wins, credited to the asked day
    assert date(2024, 1, 10) not in by_day  # missing stays missing, no interpolation
    assert len(prices) == 366 - (15 + 15 + 6)  # every 10th day of each chunk is missing


def test_points_outside_search_width_are_ignored() -> None:
    f = FakeFetcher(
        lambda ns, url, params: {
            "coins": {"x": {"prices": [{"timestamp": ts(date(2024, 1, 1), 7), "price": 5.0}]}}
        }
    )
    assert DefiLlamaPriceProvider(f).daily_prices("x", date(2024, 1, 1), date(2024, 1, 1)) == []


def test_balance_of_call_encoding() -> None:
    f = FakeFetcher(lambda ns, url, body: {"jsonrpc": "2.0", "id": 1, "result": hex(12345)})
    rpc = RpcBalanceProvider(f, chain_id=1, rpc_url="https://node/KEY")
    assert rpc.token_balance(UNI, TREASURY, 100) == 12345
    body = f.calls[0][1]["body"]
    assert body["method"] == "eth_call"
    assert body["params"][0]["data"] == "0x70a08231" + "00" * 12 + TREASURY[2:]
    assert body["params"][1] == hex(100)
