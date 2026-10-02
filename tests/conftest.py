from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from dao_analyst.config import (
    ChainConfig,
    DaoConfig,
    DaoInfo,
    SnapshotConfig,
    TokenConfig,
    TreasuryAddress,
)

TREASURY = "0x" + "aa" * 20
TREASURY_2 = "0x" + "ab" * 20
ALICE = "0x" + "01" * 20
BOB = "0x" + "02" * 20
UNI = "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
FAKE_UNI = "0x" + "fe" * 20


@pytest.fixture
def cfg() -> DaoConfig:
    return DaoConfig(
        dao=DaoInfo(id="test", name="Test DAO"),
        chain=ChainConfig(
            chain_id=1,
            name="Ethereum",
            explorer_tx_url="https://etherscan.io/tx/{tx_hash}",
            explorer_address_url="https://etherscan.io/address/{address}",
        ),
        treasury_addresses=[
            TreasuryAddress(address=TREASURY, name="Treasury", source="test"),
            TreasuryAddress(address=TREASURY_2, name="Treasury 2", source="test"),
        ],
        snapshot=SnapshotConfig(start_block=0, end_timestamp=datetime(2026, 6, 30, tzinfo=UTC)),
        tokens=[
            TokenConfig(
                address=UNI, symbol="UNI", decimals=18, price_id="coingecko:uniswap", source="test"
            ),
            TokenConfig(
                address=USDC,
                symbol="USDC",
                decimals=6,
                price_id="coingecko:usd-coin",
                source="test",
            ),
        ],
    )


class FakeFetcher:
    """Implements JsonFetcher with a handler function and records every call."""

    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.calls: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    def get(
        self, namespace: str, url: str, params: dict[str, Any], secret_params: dict[str, str]
    ) -> Any:
        self.calls.append((namespace, dict(params), dict(secret_params)))
        return self.handler(namespace, url, params)

    def post(self, namespace: str, url: str, body: Any, secret_url: str | None) -> Any:
        self.calls.append((namespace, {"body": body}, {"url": secret_url or ""}))
        return self.handler(namespace, url, body)
