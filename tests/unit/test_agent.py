"""Agent loop tests with a scripted LLM (no network)."""

from __future__ import annotations

import json
from typing import Any

from dao_analyst.agent.agent import Agent, AgentConfig, Outcome
from dao_analyst.agent.policy import Policy
from dao_analyst.agent.registry import ToolRegistry
from dao_analyst.llm.client import LLMResponse, ToolCall, Usage
from tests.unit.test_tools import FOUNDATION, GRANTEE, STRANGER, T, h, make


class ScriptedLLM:
    model = "scripted"

    def __init__(self, steps: list[list[tuple[str, dict[str, Any]]]]) -> None:
        self.steps = steps
        self.seen: list[list[dict[str, Any]]] = []

    def chat(self, messages, tools=None, tool_choice=None) -> LLMResponse:  # type: ignore[no-untyped-def]
        self.seen.append(list(messages))
        calls = self.steps.pop(0)
        tcs = [ToolCall(f"id{i}", name, json.dumps(args)) for i, (name, args) in enumerate(calls)]
        msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": t.id,
                    "type": "function",
                    "function": {"name": t.name, "arguments": t.arguments},
                }
                for t in tcs
            ],
        }
        return LLMResponse(message=msg, content=None, tool_calls=tcs, usage=Usage(10, 5))


def agent(llm: ScriptedLLM, **cfg: Any) -> Agent:
    reg = ToolRegistry(make())
    policy = Policy({T, GRANTEE, FOUNDATION}, ["Test treasury"])
    return Agent(llm, reg, policy, AgentConfig(**cfg))


def submit(
    status: str = "answer",
    text: str = "It holds {c1}.",
    claims: list[dict] | None = None,
    missing: str | None = None,
) -> tuple[str, dict[str, Any]]:
    return (
        "submit_answer",
        {"status": status, "text": text, "claims": claims or [], "missing": missing},
    )


UNI_600 = {
    "id": "c1",
    "value": "600",
    "unit": "UNI",
    "description": "UNI balance",
    "source_call_ids": ["c1"],
}
UNI_WRONG = {**UNI_600, "value": "700"}


def test_verified_answer_is_rendered_with_links_and_caveats() -> None:
    llm = ScriptedLLM(
        [
            [("get_balance_summary", {"as_of": "2024-06-30"})],
            [
                submit(
                    claims=[{**UNI_600, "value": "3000.00", "unit": "USD", "tx_hashes": [h(1)]}],
                    text="Worth {c1}.",
                )
            ],
        ]
    )
    res = agent(llm).answer("What is the treasury worth?")
    assert res.outcome is Outcome.ANSWER
    assert "Worth $3,000.00." in res.text
    assert f"https://etherscan.io/tx/{h(1)}" in res.text
    assert "pinned price snapshot" in res.text
    assert res.tool_calls[0]["tool"] == "get_balance_summary"
    assert res.verification[0]["ok"]


def test_failed_verification_gets_one_retry_with_feedback() -> None:
    llm = ScriptedLLM(
        [
            [("get_balance_summary", {})],
            [submit(claims=[UNI_WRONG])],
            [submit(claims=[UNI_600])],
        ]
    )
    res = agent(llm).answer("UNI balance?")
    assert res.outcome is Outcome.ANSWER and "600 UNI" in res.text
    feedback = llm.seen[2][-1]
    assert feedback["role"] == "tool" and "Verification failed" in feedback["content"]
    assert [v["ok"] for v in res.verification] == [False, True]


def test_second_failure_returns_only_verified_claims() -> None:
    usd_ok = {
        "id": "c2",
        "value": "6997.00",
        "unit": "USD",
        "description": "total value",
        "source_call_ids": ["c1"],
    }
    bad = [UNI_WRONG, usd_ok]
    llm = ScriptedLLM(
        [
            [("get_balance_summary", {})],
            [submit(claims=bad, text="{c1} worth {c2}")],
            [submit(claims=bad, text="{c1} worth {c2}")],
        ]
    )
    res = agent(llm).answer("Balance?")
    assert res.outcome is Outcome.PARTIAL
    assert "$6,997.00" in res.text and "700" not in res.text
    assert "could not verify: UNI balance" in res.text
    assert [c["id"] for c in res.unverified_claims] == ["c1"]


def test_without_verifier_wrong_numbers_pass_through() -> None:
    llm = ScriptedLLM([[("get_balance_summary", {})], [submit(claims=[UNI_WRONG])]])
    res = agent(llm, name="tools_no_verifier", use_verifier=False).answer("Balance?")
    assert res.outcome is Outcome.ANSWER and "700 UNI" in res.text


def test_incomplete_data_forces_abstention() -> None:
    llm = ScriptedLLM(
        [
            [("list_transfers", {"date_range": {"start": "2024-06-01", "end": "2024-12-31"}})],
            [
                submit(
                    claims=[
                        {
                            "id": "c1",
                            "value": "1",
                            "unit": "count",
                            "description": "n",
                            "source_call_ids": ["c1"],
                        }
                    ],
                    text="There were {c1} transfers.",
                )
            ],
        ]
    )
    res = agent(llm).answer("How many transfers in H2 2024?")
    assert res.outcome is Outcome.ABSTAIN and "after the snapshot end" in res.text


def test_model_abstention_and_refusal_pass_through() -> None:
    llm = ScriptedLLM([[submit("abstain", "No data.", missing="data for 2027")]])
    assert agent(llm).answer("2027 flows?").outcome is Outcome.ABSTAIN
    llm = ScriptedLLM([[submit("refuse", "No.", missing="that is investment advice")]])
    res = agent(llm).answer("Is the treasury well managed?")
    assert res.outcome is Outcome.REFUSE and "investment advice" in res.text


def test_guardrails_refuse_before_calling_the_model() -> None:
    llm = ScriptedLLM([])
    a = agent(llm)
    res = a.answer(f"What did {STRANGER} receive?")
    assert res.outcome is Outcome.REFUSE and res.refusal_reason == "non_allowlisted_address"
    res = a.answer("Should the DAO sell its UNI now?")
    assert res.outcome is Outcome.REFUSE and res.refusal_reason == "advice_or_prediction"
    assert llm.seen == []


def test_allowlisted_addresses_pass_guardrails() -> None:
    llm = ScriptedLLM([[submit("abstain", "n/a", missing="x")]])
    assert agent(llm).answer(f"What did {GRANTEE} receive?").outcome is Outcome.ABSTAIN


def test_tool_errors_are_returned_to_the_model() -> None:
    llm = ScriptedLLM(
        [
            [("list_transfers", {"counterparty": STRANGER[:10] + "0" * 32})],
            [submit("abstain", "n/a", missing="x")],
        ]
    )
    agent(llm).answer("q")
    tool_msg = llm.seen[1][-1]
    assert tool_msg["role"] == "tool" and "invalid call" in tool_msg["content"]


def test_step_limit_ends_with_error() -> None:
    llm = ScriptedLLM([[("describe_snapshot", {})]] * 3)
    res = agent(llm, max_rounds=3).answer("q")
    assert res.outcome is Outcome.ERROR
