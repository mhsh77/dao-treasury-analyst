"""JSON fetchers with record/replay.

Every provider talks to the network only through a ``JsonFetcher``. In ``live`` mode the
fetcher calls the real API; in ``record`` mode it also writes each response to disk; in
``replay`` mode it serves those recorded responses and never touches the network. Replay
runs the exact same parsing code as live runs, which is what makes the offline eval honest.

Recorded files never contain secrets: callers pass secrets separately from the request key.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import httpx
import structlog

log = structlog.get_logger(__name__)

JsonValue = Any


class FetchMode(StrEnum):
    LIVE = "live"
    RECORD = "record"
    REPLAY = "replay"


class FixtureMissingError(LookupError):
    """Replay mode was asked for a request that was never recorded."""


class FetchError(RuntimeError):
    pass


class JsonFetcher(Protocol):
    def get(
        self, namespace: str, url: str, params: dict[str, Any], secret_params: dict[str, str]
    ) -> JsonValue: ...

    def post(
        self, namespace: str, url: str, body: JsonValue, secret_url: str | None
    ) -> JsonValue: ...


def request_key(namespace: str, method: str, url: str, payload: JsonValue) -> str:
    canonical = json.dumps(
        {"ns": namespace, "method": method, "url": url, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:24]


class FixtureStore:
    """Gzipped JSON files under ``<root>/<namespace>/<key>.json.gz``."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, namespace: str, key: str) -> Path:
        return self.root / namespace / f"{key}.json.gz"

    def read(self, namespace: str, key: str) -> JsonValue:
        p = self.path(namespace, key)
        if not p.exists():
            raise FixtureMissingError(f"no recorded response {p}")
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)["response"]

    def write(self, namespace: str, key: str, request: JsonValue, response: JsonValue) -> None:
        p = self.path(namespace, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        # mtime=0 keeps the gzip bytes identical across re-recordings of the same data.
        with p.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
            gz.write(
                json.dumps({"request": request, "response": response}, sort_keys=True).encode()
            )


class HttpFetcher:
    """Live HTTP with retries and a simple per-namespace rate limit; optionally records."""

    def __init__(
        self,
        *,
        store: FixtureStore | None = None,
        timeout_s: float = 30.0,
        max_retries: int = 4,
        min_interval_s: dict[str, float] | None = None,
        client: httpx.Client | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self._store = store
        self._client = client or httpx.Client(timeout=timeout_s)
        self._max_retries = max_retries
        self._min_interval = min_interval_s or {}
        self._last_call: dict[str, float] = {}
        self._sleep = sleep

    def _throttle(self, namespace: str) -> None:
        interval = self._min_interval.get(namespace, 0.0)
        elapsed = time.monotonic() - self._last_call.get(namespace, 0.0)
        if elapsed < interval:
            self._sleep(interval - elapsed)
        self._last_call[namespace] = time.monotonic()

    def _send(self, namespace: str, build: Any) -> JsonValue:
        delay = 2.0
        for attempt in range(self._max_retries + 1):
            self._throttle(namespace)
            try:
                resp = build()
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise FetchError(f"HTTP {resp.status_code}")
                resp.raise_for_status()
                return resp.json()
            except (httpx.TransportError, FetchError) as exc:
                if attempt == self._max_retries:
                    raise FetchError(f"{namespace}: giving up after retries: {exc}") from exc
                log.warning("fetch.retry", namespace=namespace, attempt=attempt, error=str(exc))
                self._sleep(delay)
                delay *= 2
        raise AssertionError("unreachable")

    def get(
        self, namespace: str, url: str, params: dict[str, Any], secret_params: dict[str, str]
    ) -> JsonValue:
        data = self._send(
            namespace, lambda: self._client.get(url, params={**params, **secret_params})
        )
        if self._store is not None:
            key = request_key(namespace, "GET", url, params)
            self._store.write(namespace, key, {"url": url, "params": params}, data)
        return data

    def post(self, namespace: str, url: str, body: JsonValue, secret_url: str | None) -> JsonValue:
        data = self._send(namespace, lambda: self._client.post(secret_url or url, json=body))
        if self._store is not None:
            key = request_key(namespace, "POST", url, body)
            self._store.write(namespace, key, {"url": url, "body": body}, data)
        return data


class ReplayFetcher:
    """Serves recorded responses only. Never opens a network connection."""

    def __init__(self, store: FixtureStore) -> None:
        self._store = store

    def get(
        self, namespace: str, url: str, params: dict[str, Any], secret_params: dict[str, str]
    ) -> JsonValue:
        return self._store.read(namespace, request_key(namespace, "GET", url, params))

    def post(self, namespace: str, url: str, body: JsonValue, secret_url: str | None) -> JsonValue:
        return self._store.read(namespace, request_key(namespace, "POST", url, body))
