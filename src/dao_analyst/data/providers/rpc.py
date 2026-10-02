"""JSON-RPC balance provider (needs an archive node for historical blocks)."""

from __future__ import annotations

from typing import Any

from dao_analyst.data.fetch import JsonFetcher

NAMESPACE = "rpc"
# Public stand-in for the RPC URL in recorded fixtures; the real URL embeds an API key.
PUBLIC_URL = "rpc://chain/{chain_id}"
BALANCE_OF_SELECTOR = "0x70a08231"


class RpcError(RuntimeError):
    pass


class RpcBalanceProvider:
    def __init__(self, fetcher: JsonFetcher, *, chain_id: int, rpc_url: str | None) -> None:
        self._fetcher = fetcher
        self._rpc_url = rpc_url
        self._public_url = PUBLIC_URL.format(chain_id=chain_id)

    def _call(self, method: str, params: list[Any]) -> str:
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        data = self._fetcher.post(NAMESPACE, self._public_url, body, self._rpc_url)
        if "error" in data:
            raise RpcError(f"{method}: {data['error']}")
        result = data["result"]
        if not isinstance(result, str):
            raise RpcError(f"{method}: unexpected result {result!r}")
        return result

    def native_balance(self, address: str, block: int) -> int:
        return int(self._call("eth_getBalance", [address, hex(block)]), 16)

    def token_balance(self, token: str, address: str, block: int) -> int:
        data = BALANCE_OF_SELECTOR + address.lower().removeprefix("0x").rjust(64, "0")
        result = self._call("eth_call", [{"to": token, "data": data}, hex(block)])
        return int(result, 16) if result not in ("0x", "") else 0
