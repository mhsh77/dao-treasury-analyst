from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from dao_analyst.data.providers.defillama import DefiLlamaPriceProvider
from dao_analyst.data.providers.rpc import RpcBalanceProvider
from tests.conftest import TREASURY, UNI, FakeFetcher


def ts(d: date, hour: int = 0) -> int:
    return int(datetime(d.year, d.month, d.day, hour, tzinfo=UTC).timestamp())


def test_prices_are_chunked_and_bucketed_by_utc_day() -> None:
    def handler(ns: str, url: str, params: dict[str, Any]) -> dict[str, Any]:
        start = params["start"]
        points = [
            {"timestamp": start + i * 86_400 + 3600, "price": 1.0 + i}
            for i in range(params["span"])
        ]
        points.append({"timestamp": start + 7200, "price": 99.0})  # later point, same day
        return {"coins": {"coingecko:uniswap": {"prices": points}}}

    f = FakeFetcher(handler)
    prices = DefiLlamaPriceProvider(f).daily_prices(
        "coingecko:uniswap", date(2024, 1, 1), date(2025, 12, 31)
    )
    assert len(f.calls) == 2  # 731 days > 400-day chunk
    assert len(prices) == 731
    assert prices[0].day == date(2024, 1, 1) and prices[0].usd == 1.0  # earliest point wins


def test_balance_of_call_encoding() -> None:
    f = FakeFetcher(lambda ns, url, body: {"jsonrpc": "2.0", "id": 1, "result": hex(12345)})
    rpc = RpcBalanceProvider(f, chain_id=1, rpc_url="https://node/KEY")
    assert rpc.token_balance(UNI, TREASURY, 100) == 12345
    body = f.calls[0][1]["body"]
    assert body["method"] == "eth_call"
    assert body["params"][0]["data"] == "0x70a08231" + "00" * 12 + TREASURY[2:]
    assert body["params"][1] == hex(100)
