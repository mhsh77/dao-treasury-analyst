"""A small LLM client interface plus an OpenAI-compatible implementation.

One adapter covers every provider that speaks the OpenAI chat-completions protocol with
tool calling (Groq, Gemini's OpenAI endpoint, OpenRouter, a local vLLM...). The agent only
sees ``LLMClient``, so swapping providers never touches agent logic.

``CassetteLLM`` records every request/response pair to disk and can replay them, which is
what lets anyone re-run the eval offline without an API key.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx
import structlog

log = structlog.get_logger(__name__)

Message = dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text as produced by the model


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class LLMResponse:
    message: Message  # assistant message to append to the history as-is
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    latency_s: float = 0.0


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    model: str

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse: ...


def parse_response(data: dict[str, Any], latency: float) -> LLMResponse:
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError) as exc:
        raise LLMError(f"malformed response: {json.dumps(data)[:500]}") from exc
    # Keep only fields every provider accepts back; Gemini's thought signatures live inside
    # tool_calls[].extra_content and must be echoed unchanged.
    clean: Message = {"role": "assistant", "content": msg.get("content")}
    calls = []
    if msg.get("tool_calls"):
        clean["tool_calls"] = msg["tool_calls"]
        for tc in msg["tool_calls"]:
            fn = tc.get("function", {})
            calls.append(
                ToolCall(tc.get("id", ""), fn.get("name", ""), fn.get("arguments") or "{}")
            )
    usage = data.get("usage") or {}
    return LLMResponse(
        message=clean,
        content=msg.get("content"),
        tool_calls=calls,
        usage=Usage(int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)),
        latency_s=latency,
    )


class OpenAICompatClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.0,
        timeout_s: float = 120.0,
        max_retries: int = 6,
        sleep: Callable[[float], None] = time.sleep,
        client: httpx.Client | None = None,
        extra_body: dict[str, Any] | None = None,
        min_interval_s: float = 0.0,
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._temperature = temperature
        self._max_retries = max_retries
        self._sleep = sleep
        self._client = client or httpx.Client(timeout=timeout_s)
        self._extra = extra_body or {}
        self._min_interval = min_interval_s  # client-side pacing for free-tier RPM limits
        self._last_call = 0.0

    def request_body(
        self, messages: list[Message], tools: list[dict[str, Any]] | None, tool_choice: str | None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self._temperature,
            **self._extra,
        }
        if tools:
            body["tools"] = tools
            if tool_choice:
                body["tool_choice"] = tool_choice
        return body

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        body = self.request_body(messages, tools, tool_choice)
        delay = 5.0
        for attempt in range(self._max_retries + 1):
            wait = self._min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                self._sleep(wait)
            self._last_call = time.monotonic()
            start = time.monotonic()
            try:
                resp = self._client.post(self._url, headers=self._headers, json=body)
            except httpx.TransportError as exc:
                if attempt == self._max_retries:
                    raise LLMError(f"transport error: {exc}") from exc
                self._sleep(delay)
                delay = min(delay * 2, 120)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == self._max_retries:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                wait = _retry_after(resp) or delay
                log.warning("llm.retry", status=resp.status_code, wait_s=wait, attempt=attempt)
                self._sleep(wait)
                delay = min(delay * 2, 120)
                continue
            if resp.status_code >= 400:
                raise LLMError(f"HTTP {resp.status_code}: {resp.text[:500]}")
            return parse_response(resp.json(), time.monotonic() - start)
        raise AssertionError("unreachable")


def _retry_after(resp: httpx.Response) -> float | None:
    value = resp.headers.get("retry-after")
    try:
        return min(float(value), 300.0) if value else None
    except ValueError:
        return None


class CassetteMissingError(LookupError):
    pass


class CassetteLLM:
    """Wraps a client to record calls, or replays recorded calls with no client at all."""

    def __init__(self, path: Path, *, model: str, inner: LLMClient | None = None) -> None:
        self.model = model
        self._path = path
        self._inner = inner
        self._entries: dict[str, dict[str, Any]] = {}
        if path.exists():
            with gzip.open(path, "rt", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    self._entries[entry["key"]] = entry

    @staticmethod
    def key(
        model: str,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | None,
    ) -> str:
        canonical = json.dumps(
            {"model": model, "messages": messages, "tools": tools, "tool_choice": tool_choice},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        k = self.key(self.model, messages, tools, tool_choice)
        if k in self._entries:
            e = self._entries[k]
            resp = parse_response(e["response"], e["latency_s"])
            return resp
        if self._inner is None:
            raise CassetteMissingError(
                f"no recorded LLM response for this request (key {k[:12]}); "
                "the prompt or code changed since the cassette was recorded"
            )
        resp = self._inner.chat(messages, tools, tool_choice)
        raw = {
            "choices": [{"message": resp.message}],
            "usage": {
                "prompt_tokens": resp.usage.input_tokens,
                "completion_tokens": resp.usage.output_tokens,
            },
        }
        entry = {"key": k, "model": self.model, "response": raw, "latency_s": resp.latency_s}
        self._entries[k] = entry
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(self._path, "at", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        return resp


PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
}
