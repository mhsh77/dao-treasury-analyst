from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from dao_analyst.agent.registry import SPECS, tool_schemas
from dao_analyst.llm.client import (
    CassetteLLM,
    CassetteMissingError,
    LLMError,
    OpenAICompatClient,
)

OK = {
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": None,
                "reasoning": "hidden",
                "tool_calls": [
                    {
                        "id": "t1",
                        "type": "function",
                        "extra_content": {"google": {"sig": "abc"}},
                        "function": {"name": "f", "arguments": "{}"},
                    }
                ],
            }
        }
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 3},
}


def client(handler, sleeps: list[float] | None = None) -> OpenAICompatClient:  # type: ignore[no-untyped-def]
    return OpenAICompatClient(
        base_url="https://llm.example/v1",
        api_key="K",
        model="m",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
        max_retries=2,
    )


def test_parses_tool_calls_and_keeps_provider_extras() -> None:
    resp = client(lambda r: httpx.Response(200, json=OK)).chat([{"role": "user", "content": "x"}])
    assert resp.tool_calls[0].name == "f" and resp.usage.input_tokens == 11
    assert resp.message["tool_calls"][0]["extra_content"] == {"google": {"sig": "abc"}}
    assert "reasoning" not in resp.message  # not echoed back to providers


def test_rate_limits_are_retried_honoring_retry_after() -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"retry-after": "7"}),
            httpx.Response(503),
            httpx.Response(200, json=OK),
        ]
    )
    sleeps: list[float] = []
    client(lambda r: next(responses), sleeps).chat([])
    assert sleeps == [7.0, 10.0]


def test_client_errors_are_not_retried() -> None:
    with pytest.raises(LLMError, match="400"):
        client(lambda r: httpx.Response(400, text="bad")).chat([])


def test_cassette_records_then_replays_offline(tmp_path: Path) -> None:
    path = tmp_path / "c.jsonl.gz"
    calls = []

    def handler(r: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=OK)

    rec = CassetteLLM(path, model="m", inner=client(handler))
    msgs = [{"role": "user", "content": "hello"}]
    rec.chat(msgs)
    rec.chat(msgs)  # served from the cassette
    assert len(calls) == 1
    replay = CassetteLLM(path, model="m")
    assert replay.chat(msgs).tool_calls[0].name == "f"
    with pytest.raises(CassetteMissingError):
        replay.chat([{"role": "user", "content": "different"}])


def test_tool_schemas_have_no_refs_or_titles() -> None:
    text = str(tool_schemas(SPECS))
    assert "$ref" not in text and "'title'" not in text and "$defs" not in text
