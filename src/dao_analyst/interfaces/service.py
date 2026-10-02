"""Transport-agnostic question service shared by the Telegram bot and the CLI.

Holds the policies that belong to an interface rather than to the agent: per-user rate
limits, a global concurrency cap (free-tier model quotas), message length limits and
structured request logging.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

import structlog

from dao_analyst.agent.agent import AgentResult, Outcome

log = structlog.get_logger(__name__)

MAX_QUESTION_CHARS = 500
TELEGRAM_LIMIT = 4096


class RateLimiter:
    """Sliding-window limit per user: at most ``max_requests`` per ``window_s`` seconds."""

    def __init__(
        self, max_requests: int, window_s: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.max_requests = max_requests
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, user: str) -> tuple[bool, float]:
        """Returns (allowed, seconds until the next request would be allowed)."""
        now = self._clock()
        with self._lock:
            hits = self._hits[user]
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return False, self.window_s - (now - hits[0])
            hits.append(now)
            return True, 0.0


@dataclass
class Reply:
    text: str
    outcome: str


class QuestionService:
    def __init__(
        self, answer: Callable[[str], AgentResult], limiter: RateLimiter, max_concurrent: int = 2
    ) -> None:
        self._answer = answer
        self._limiter = limiter
        self._slots = threading.BoundedSemaphore(max_concurrent)

    def ask(self, user: str, question: str) -> Reply:
        question = question.strip()
        if not question:
            return Reply("Please send a question about the treasury.", "empty")
        if len(question) > MAX_QUESTION_CHARS:
            return Reply(
                f"Please keep questions under {MAX_QUESTION_CHARS} characters.", "too_long"
            )
        allowed, retry_in = self._limiter.allow(user)
        if not allowed:
            return Reply(
                f"You're asking too quickly. Please try again in "
                f"{max(1, round(retry_in))} seconds.",
                "rate_limited",
            )
        if not self._slots.acquire(timeout=60):
            return Reply("The analyst is busy right now. Please try again in a minute.", "busy")
        try:
            start = time.monotonic()
            result = self._answer(question)
        finally:
            self._slots.release()
        log.info(
            "service.ask",
            user=user,
            outcome=result.outcome.value,
            tool_calls=len(result.tool_calls),
            latency_s=round(time.monotonic() - start, 2),
            verified_claims=len(result.claims),
        )
        return Reply(format_reply(result), result.outcome.value)


def format_reply(result: AgentResult) -> str:
    prefix = {
        Outcome.PARTIAL: "Partially verified answer.\n\n",
        Outcome.ABSTAIN: "",
        Outcome.REFUSE: "",
        Outcome.ERROR: "",
    }.get(result.outcome, "")
    text = prefix + result.text
    if result.outcome is Outcome.ANSWER and not result.claims:
        text += "\n\n(No figures in this answer.)"
    if len(text) > TELEGRAM_LIMIT:
        text = text[: TELEGRAM_LIMIT - 20].rsplit("\n", 1)[0] + "\n...(truncated)"
    return text
