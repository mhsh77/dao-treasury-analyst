from __future__ import annotations

from typing import Any

import pytest

from dao_analyst.data.providers.etherscan import EtherscanError, EtherscanProvider, PaginationError
from tests.conftest import TREASURY, FakeFetcher


def token_row(block: int, n: int) -> dict[str, str]:
    return {
        "blockNumber": str(block),
        "timeStamp": "1700000000",
        "hash": f"0x{block:x}{n:04x}",
        "contractAddress": "0x" + "11" * 20,
        "tokenSymbol": "TKN",
        "tokenDecimal": "18",
        "from": "0x" + "22" * 20,
        "to": TREASURY,
        "value": str(n + 1),
    }


class Chain:
    """A fake Etherscan account endpoint over a fixed list of rows, sorted by block."""

    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows

    def __call__(self, namespace: str, url: str, params: dict[str, Any]) -> dict[str, Any]:
        lo, hi = int(params["startblock"]), int(params["endblock"])
        hits = [r for r in self.rows if lo <= int(r["blockNumber"]) <= hi][: int(params["offset"])]
        if not hits:
            return {"status": "0", "message": "No transactions found", "result": []}
        return {"status": "1", "message": "OK", "result": hits}


def provider(handler: Any, page_size: int) -> tuple[EtherscanProvider, FakeFetcher]:
    f = FakeFetcher(handler)
    return EtherscanProvider(
        f, chain_id=1, api_key="SECRET", page_size=page_size, sleep=lambda s: None
    ), f


def test_sliding_window_reads_every_row_exactly_once() -> None:
    # Blocks with 1..4 rows each; page size 5 forces cuts in the middle of blocks.
    rows = [token_row(b, i) for b in range(10, 20) for i in range(b % 4 + 1)]
    p, f = provider(Chain(rows), page_size=5)
    got = p.token_transfers(TREASURY, 0, 100)
    assert [(t.block_number, t.raw_amount) for t in got] == [
        (int(r["blockNumber"]), int(r["value"])) for r in rows
    ]
    assert len(f.calls) > 2  # the test really paginated


def test_exactly_full_last_page_triggers_one_more_query() -> None:
    rows = [token_row(10, 0), token_row(11, 0), token_row(12, 0)]
    p, f = provider(Chain(rows), page_size=3)
    assert len(p.token_transfers(TREASURY, 0, 100)) == 3
    assert [c[1]["startblock"] for c in f.calls] == [0, 12]


def test_block_denser_than_a_page_is_an_explicit_error() -> None:
    rows = [token_row(10, i) for i in range(6)]
    p, _ = provider(Chain(rows), page_size=5)
    with pytest.raises(PaginationError):
        p.token_transfers(TREASURY, 10, 100)


def test_no_transactions_found_is_an_empty_list() -> None:
    p, _ = provider(Chain([]), page_size=5)
    assert p.native_txs(TREASURY, 0, 100) == []


def test_rate_limit_responses_are_retried() -> None:
    responses = iter(
        [
            {
                "status": "0",
                "message": "NOTOK",
                "result": "Max calls per sec rate limit reached",
            },
            {"status": "1", "message": "OK", "result": "123"},
        ]
    )
    p, f = provider(lambda *a: next(responses), page_size=5)
    assert p.block_at_or_before(1_700_000_000) == 123
    assert len(f.calls) == 2


def test_other_api_errors_raise() -> None:
    p, _ = provider(lambda *a: {"status": "0", "message": "NOTOK", "result": "Invalid API Key"}, 5)
    with pytest.raises(EtherscanError, match="Invalid API Key"):
        p.native_txs(TREASURY, 0, 1)


def test_api_key_is_passed_as_secret_not_as_request_param() -> None:
    p, f = provider(Chain([]), page_size=5)
    p.native_txs(TREASURY, 0, 1)
    _, params, secret = f.calls[0]
    assert "apikey" not in params and secret == {"apikey": "SECRET"}


def test_failed_internal_and_native_flags_are_parsed() -> None:
    row = {
        "blockNumber": "5",
        "timeStamp": "1",
        "hash": "0xAB",
        "traceId": "0_1",
        "from": "0xA",
        "to": "",
        "contractAddress": "0xC",
        "value": "7",
        "isError": "1",
    }
    p, _ = provider(lambda *a: {"status": "1", "message": "OK", "result": [row]}, 5)
    (tx,) = p.internal_txs(TREASURY, 0, 10)
    assert tx.is_error and tx.to_address == "0xc" and tx.tx_hash == "0xab"
