from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from dao_analyst.data.fetch import (
    FetchError,
    FixtureMissingError,
    FixtureStore,
    HttpFetcher,
    ReplayFetcher,
)


def client(handler) -> httpx.Client:  # type: ignore[no-untyped-def]
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_record_then_replay_round_trip_without_secrets(tmp_path: Path) -> None:
    store = FixtureStore(tmp_path)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"status": "1", "result": [1, 2]})

    live = HttpFetcher(store=store, client=client(handler))
    params = {"module": "account", "address": "0xabc"}
    assert live.get("etherscan", "https://x/api", params, {"apikey": "KEY"}) == {
        "status": "1",
        "result": [1, 2],
    }
    assert "apikey=KEY" in seen["url"]

    files = list(tmp_path.rglob("*.json.gz"))
    assert len(files) == 1
    assert b"KEY" not in files[0].read_bytes()  # gz content checked below too
    import gzip

    assert "KEY" not in gzip.decompress(files[0].read_bytes()).decode()

    replay = ReplayFetcher(store)
    assert replay.get("etherscan", "https://x/api", params, {"apikey": "OTHER"})["result"] == [1, 2]


def test_replay_of_unrecorded_request_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(FixtureMissingError):
        ReplayFetcher(FixtureStore(tmp_path)).get("etherscan", "u", {"a": 1}, {})


def test_post_records_under_public_url(tmp_path: Path) -> None:
    store = FixtureStore(tmp_path)
    live = HttpFetcher(
        store=store,
        client=client(lambda r: httpx.Response(200, json={"jsonrpc": "2.0", "result": "0x1"})),
    )
    body = {"method": "eth_getBalance", "params": ["0xabc", "0x10"]}
    live.post("rpc", "rpc://chain/1", body, "https://node.example/v2/SECRETKEY")
    import gzip

    (f,) = tmp_path.rglob("*.json.gz")
    assert "SECRETKEY" not in gzip.decompress(f.read_bytes()).decode()
    assert ReplayFetcher(store).post("rpc", "rpc://chain/1", body, None)["result"] == "0x1"


def test_recording_is_byte_for_byte_deterministic(tmp_path: Path) -> None:
    store = FixtureStore(tmp_path)
    store.write("ns", "k", {"a": 1}, {"b": 2})
    first = store.path("ns", "k").read_bytes()
    store.write("ns", "k", {"a": 1}, {"b": 2})
    assert store.path("ns", "k").read_bytes() == first


def test_server_errors_are_retried_then_raise(tmp_path: Path) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    live = HttpFetcher(client=client(handler), max_retries=2, sleep=lambda s: None)
    with pytest.raises(FetchError):
        live.get("ns", "https://x", {}, {})
    assert len(calls) == 3
