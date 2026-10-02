"""Etherscan API V2 provider (one key, any supported EVM chain via ``chainid``).

Pagination: Etherscan returns at most ``page * offset <= 10_000`` rows per query window.
We always request page 1 and slide the window forward instead of paging. When a response
is full, rows from its last block may be cut off mid-block, so we drop that block and
restart the window *at* it. Every block is therefore read completely by exactly one query,
which means no duplicates and no gaps without having to deduplicate by content.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from dao_analyst.data.fetch import JsonFetcher
from dao_analyst.data.providers.base import RawInternalTx, RawNativeTx, RawTokenTransfer

MAX_ROWS = 10_000
NAMESPACE = "etherscan"


class EtherscanError(RuntimeError):
    pass


class PaginationError(EtherscanError):
    """A single block holds more rows than one response can carry."""


def _addr(value: str | None) -> str | None:
    return value.lower() if value else None


def _int_or_none(value: str | None) -> int | None:
    return int(value) if value not in (None, "") else None


class EtherscanProvider:
    def __init__(
        self,
        fetcher: JsonFetcher,
        *,
        chain_id: int,
        api_key: str | None,
        base_url: str = "https://api.etherscan.io/v2/api",
        page_size: int = MAX_ROWS,
        rate_limit_retries: int = 5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 0 < page_size <= MAX_ROWS:
            raise ValueError("page_size must be in 1..10000")
        self.chain_id = chain_id
        self._fetcher = fetcher
        self._api_key = api_key
        self._base_url = base_url
        self._page_size = page_size
        self._rate_limit_retries = rate_limit_retries
        self._sleep = sleep

    # -- low level ---------------------------------------------------------------------

    def _call(self, params: dict[str, Any]) -> Any:
        full = {"chainid": self.chain_id, **params}
        secret = {"apikey": self._api_key} if self._api_key else {}
        for attempt in range(self._rate_limit_retries + 1):
            data = self._fetcher.get(NAMESPACE, self._base_url, full, secret)
            # Etherscan signals rate limiting with HTTP 200 and status "0".
            if not (isinstance(data, dict) and "rate limit" in str(data.get("result", "")).lower()):
                break
            if attempt < self._rate_limit_retries:
                self._sleep(1.0 + attempt)
        if not isinstance(data, dict):
            raise EtherscanError(f"unexpected response: {data!r}")
        # The proxy module returns JSON-RPC shaped responses.
        if "jsonrpc" in data:
            if "error" in data:
                raise EtherscanError(str(data["error"]))
            return data["result"]
        status, message, result = data.get("status"), data.get("message", ""), data.get("result")
        if status == "1":
            return result
        if status == "0" and isinstance(result, list) and message.startswith("No "):
            return []  # "No transactions found" / "No records found"
        raise EtherscanError(f"{params.get('action')}: {message}: {result}")

    def _window_rows(
        self, action: str, address: str, start_block: int, end_block: int
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor = start_block
        while cursor <= end_block:
            batch = self._call(
                {
                    "module": "account",
                    "action": action,
                    "address": address,
                    "startblock": cursor,
                    "endblock": end_block,
                    "page": 1,
                    "offset": self._page_size,
                    "sort": "asc",
                }
            )
            if len(batch) < self._page_size:
                rows.extend(batch)
                break
            last_block = int(batch[-1]["blockNumber"])
            if last_block == cursor:
                raise PaginationError(
                    f"{action}: block {cursor} has >= {self._page_size} rows for {address}"
                )
            rows.extend(r for r in batch if int(r["blockNumber"]) < last_block)
            cursor = last_block
        return rows

    # -- ChainDataProvider -------------------------------------------------------------

    def native_txs(self, address: str, start_block: int, end_block: int) -> list[RawNativeTx]:
        return [
            RawNativeTx(
                block_number=int(r["blockNumber"]),
                timestamp=int(r["timeStamp"]),
                tx_hash=r["hash"].lower(),
                from_address=r["from"].lower(),
                to_address=_addr(r.get("to")),
                value_wei=int(r["value"]),
                gas_used=int(r["gasUsed"]),
                gas_price_wei=int(r["gasPrice"]),
                is_error=r.get("isError") == "1",
            )
            for r in self._window_rows("txlist", address, start_block, end_block)
        ]

    def internal_txs(self, address: str, start_block: int, end_block: int) -> list[RawInternalTx]:
        return [
            RawInternalTx(
                block_number=int(r["blockNumber"]),
                timestamp=int(r["timeStamp"]),
                tx_hash=r["hash"].lower(),
                trace_id=r.get("traceId", ""),
                from_address=r["from"].lower(),
                to_address=_addr(r.get("to")) or _addr(r.get("contractAddress")),
                value_wei=int(r["value"]),
                is_error=r.get("isError") == "1",
            )
            for r in self._window_rows("txlistinternal", address, start_block, end_block)
        ]

    def token_transfers(
        self, address: str, start_block: int, end_block: int
    ) -> list[RawTokenTransfer]:
        return [
            RawTokenTransfer(
                block_number=int(r["blockNumber"]),
                timestamp=int(r["timeStamp"]),
                tx_hash=r["hash"].lower(),
                log_index=_int_or_none(r.get("logIndex")),
                token_address=r["contractAddress"].lower(),
                token_symbol=r.get("tokenSymbol", ""),
                token_decimals=_int_or_none(r.get("tokenDecimal")),
                from_address=r["from"].lower(),
                to_address=r["to"].lower(),
                raw_amount=int(r["value"]),
            )
            for r in self._window_rows("tokentx", address, start_block, end_block)
        ]

    def block_at_or_before(self, timestamp: int) -> int:
        result = self._call(
            {
                "module": "block",
                "action": "getblocknobytime",
                "timestamp": timestamp,
                "closest": "before",
            }
        )
        return int(result)

    def block_timestamp(self, block: int) -> int:
        result = self._call(
            {
                "module": "proxy",
                "action": "eth_getBlockByNumber",
                "tag": hex(block),
                "boolean": "false",
            }
        )
        return int(result["timestamp"], 16)
