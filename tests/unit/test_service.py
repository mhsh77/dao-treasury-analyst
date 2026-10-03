from __future__ import annotations

from dao_analyst.agent.agent import AgentResult, Outcome
from dao_analyst.interfaces.service import (
    MAX_QUESTION_CHARS,
    TELEGRAM_LIMIT,
    QuestionService,
    RateLimiter,
    format_reply,
)
from dao_analyst.interfaces.telegram_bot import user_key


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def result(
    outcome: Outcome = Outcome.ANSWER, text: str = "ok", claims: list[dict] | None = None
) -> AgentResult:
    return AgentResult(
        question="q",
        config="full",
        outcome=outcome,
        text=text,
        claims=claims if claims is not None else [{"id": "c1"}],
    )


def test_rate_limiter_sliding_window() -> None:
    clock = Clock()
    rl = RateLimiter(2, 60, clock)
    assert rl.allow("a")[0] and rl.allow("a")[0]
    ok, wait = rl.allow("a")
    assert not ok and wait == 60
    assert rl.allow("b")[0]  # per user
    clock.t = 61
    assert rl.allow("a")[0]


def test_service_validates_limits_and_answers() -> None:
    calls = []
    svc = QuestionService(lambda q: calls.append(q) or result(), RateLimiter(1, 60, Clock()))
    assert svc.ask("u", "  ").outcome == "empty"
    assert svc.ask("u", "x" * (MAX_QUESTION_CHARS + 1)).outcome == "too_long"
    assert svc.ask("u", "UNI balance?").outcome == "answer"
    assert svc.ask("u", "again?").outcome == "rate_limited"
    assert calls == ["UNI balance?"]


def test_reply_formatting() -> None:
    assert format_reply(result(Outcome.PARTIAL)).startswith("Partially verified")
    assert "No figures" in format_reply(result(claims=[]))
    long = format_reply(result(text="line\n" * 2000))
    assert len(long) <= TELEGRAM_LIMIT and long.endswith("(truncated)")


def test_user_key_is_pseudonymous_and_stable() -> None:
    assert user_key(12345) == user_key(12345) != "12345"


def test_telegram_app_registers_handlers_without_network() -> None:
    from dao_analyst.interfaces.telegram_bot import build_app

    svc = QuestionService(lambda q: result(), RateLimiter(1, 60))
    app = build_app("123456:TEST-TOKEN", svc, "intro")
    names = {type(h).__name__ for group in app.handlers.values() for h in group}
    assert names == {"CommandHandler", "MessageHandler"}
