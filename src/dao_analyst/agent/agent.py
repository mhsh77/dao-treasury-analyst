"""The agent loop: tools -> structured answer -> claim verification -> rendered reply.

Three configurations share this code so the eval compares like with like:
- full: tools + claim verifier + abstention enforcement + guardrails
- tools_no_verifier: same, but the final answer is accepted unchecked
- naive (``NaiveAgent``): raw transfers in the prompt, no tools, no verifier
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import structlog
from pydantic import ValidationError

from dao_analyst.agent.answer import AnswerStatus, Claim, FinalAnswer
from dao_analyst.agent.policy import Policy
from dao_analyst.agent.prompts import naive_prompt, tool_agent_prompt
from dao_analyst.agent.registry import ToolRegistry, inline_schema
from dao_analyst.agent.render import fill_placeholders, render
from dao_analyst.agent.verifier import VerificationReport, normalize_unit, verify
from dao_analyst.llm.client import LLMClient, LLMError, Message

log = structlog.get_logger(__name__)

SUBMIT = "submit_answer"
SUBMIT_SCHEMA = {
    "type": "function",
    "function": {
        "name": SUBMIT,
        "description": "Submit the final answer with every number as a cited claim.",
        "parameters": inline_schema(FinalAnswer),
    },
}


class Outcome(StrEnum):
    ANSWER = "answer"
    PARTIAL = "partial"  # verification failed twice; only verified claims are kept
    ABSTAIN = "abstain"
    REFUSE = "refuse"
    ERROR = "error"


@dataclass
class AgentConfig:
    name: str = "full"
    use_verifier: bool = True
    enforce_abstention: bool = True
    guardrails: bool = True
    max_rounds: int = 8
    max_verify_retries: int = 1


@dataclass
class AgentResult:
    question: str
    config: str
    outcome: Outcome
    text: str
    claims: list[dict[str, Any]] = field(default_factory=list)
    unverified_claims: list[dict[str, Any]] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    missing: str | None = None
    refusal_reason: str | None = None
    verification: list[dict[str, Any]] = field(default_factory=list)  # one per attempt
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["outcome"] = self.outcome.value
        return d


class AuditLog:
    """Append-only JSONL audit trail of questions, tool calls and verification outcomes."""

    def __init__(self, path: Path | None) -> None:
        self.path = path

    def write(self, result: AgentResult) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps({"ts": time.time(), **result.to_dict()}, default=str) + "\n")


def _usage(result: AgentResult, resp: Any) -> None:
    result.llm_calls += 1
    result.input_tokens += resp.usage.input_tokens
    result.output_tokens += resp.usage.output_tokens


def _parse_final(raw: str) -> FinalAnswer:
    data = json.loads(raw or "{}")
    return FinalAnswer.model_validate(data)


def _price_caveat(claims: list[Claim], price_source: str) -> list[str]:
    if any(normalize_unit(c.unit) == "USD" for c in claims):
        return [f"USD figures use the pinned price snapshot ({price_source}), not live prices."]
    return []


class Agent:
    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        policy: Policy,
        config: AgentConfig | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.policy = policy
        self.config = config or AgentConfig()
        self.audit = audit or AuditLog(None)
        data = registry.tools.data
        self.system_prompt = tool_agent_prompt(data, registry.tools.dao_name)
        self.tx_url = data.explorer_tx_url
        self.price_source = data.price_source

    def answer(self, question: str) -> AgentResult:
        start = time.monotonic()
        result = AgentResult(
            question=question, config=self.config.name, outcome=Outcome.ERROR, text=""
        )
        try:
            self._run(question, result)
        except LLMError as exc:
            result.outcome = Outcome.ERROR
            result.error = str(exc)
            result.text = "Sorry, the language model is unavailable right now. Please retry."
        result.latency_s = time.monotonic() - start
        result.tool_calls = [r.audit() for r in self.registry.log]
        self.audit.write(result)
        log.info(
            "agent.answer",
            config=self.config.name,
            outcome=result.outcome.value,
            tool_calls=len(result.tool_calls),
            latency_s=round(result.latency_s, 2),
        )
        return result

    def _run(self, question: str, result: AgentResult) -> None:
        self.registry.reset()
        if self.config.guardrails and (decision := self.policy.check(question)):
            result.outcome = Outcome.REFUSE
            result.refusal_reason = decision.reason
            result.missing = decision.message
            result.text = decision.message
            return
        messages: list[Message] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": question},
        ]
        tools = [*self.registry.schemas, SUBMIT_SCHEMA]
        retries_left = self.config.max_verify_retries
        nudged = False
        for _ in range(self.config.max_rounds):
            resp = self.llm.chat(messages, tools, tool_choice="required")
            _usage(result, resp)
            messages.append(resp.message)
            if not resp.tool_calls:
                if nudged:
                    break
                nudged = True
                messages.append(
                    {"role": "user", "content": "Call submit_answer with your final answer."}
                )
                continue
            final_call = None
            for call in resp.tool_calls:
                if call.name == SUBMIT:
                    final_call = call
                    continue
                record = self.registry.execute(call.name, call.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(record.for_llm()),
                    }
                )
            if final_call is None:
                continue
            try:
                final = _parse_final(final_call.arguments)
            except (json.JSONDecodeError, ValidationError) as exc:
                feedback = f"submit_answer arguments were invalid: {exc}"
                messages.append(
                    {"role": "tool", "tool_call_id": final_call.id, "content": feedback}
                )
                continue
            if not self.config.use_verifier:
                self._finish(final, None, result)
                return
            report = verify(final, self.registry.log, question)
            result.verification.append(report.as_dict())
            incomplete = self.config.enforce_abstention and report.incomplete_sources
            if report.ok or retries_left == 0 or incomplete:
                self._finish(final, report, result)
                return
            retries_left -= 1
            messages.append(
                {"role": "tool", "tool_call_id": final_call.id, "content": report.feedback()}
            )
        result.outcome = Outcome.ERROR
        result.error = "no final answer within the step limit"
        result.text = "I couldn't complete this question within the step limit."

    def _finish(
        self, final: FinalAnswer, report: VerificationReport | None, result: AgentResult
    ) -> None:
        result.caveats = list(final.caveats)
        result.missing = final.missing
        if final.status is AnswerStatus.REFUSE:
            result.outcome = Outcome.REFUSE
            result.refusal_reason = "model"
            result.text = final.missing or fill_placeholders(final.text, final.claims)
            return
        if final.status is AnswerStatus.ABSTAIN:
            result.outcome = Outcome.ABSTAIN
            reason = final.missing or "the snapshot does not contain the data needed"
            result.text = f"I can't answer this from the pinned snapshot: {reason}"
            return
        if report is not None and self.config.enforce_abstention and report.incomplete_sources:
            result.outcome = Outcome.ABSTAIN
            result.missing = "; ".join(report.incomplete_sources)
            result.text = f"I can't answer this from the pinned snapshot: {result.missing}"
            result.unverified_claims = [c.model_dump() for c in final.claims]
            return
        claims = list(final.claims)
        if report is not None and not report.ok:
            ok_ids = {c.claim_id for c in report.claim_checks if c.verified}
            verified = [c for c in claims if c.id in ok_ids]
            failed = [c for c in claims if c.id not in ok_ids]
            result.outcome = Outcome.PARTIAL
            result.claims = [c.model_dump() for c in verified]
            result.unverified_claims = [c.model_dump() for c in failed]
            lines = ["I could only verify part of this answer against the tool outputs."]
            lines += [f"- {c.description}: {{{c.id}}}" for c in verified]
            if failed:
                lines.append(
                    "I could not verify: " + "; ".join(c.description for c in failed) + "."
                )
            caveats = _price_caveat(verified, self.price_source)
            result.text = render("\n".join(lines), verified, caveats, self.tx_url)
            return
        result.outcome = Outcome.ANSWER
        result.claims = [c.model_dump() for c in claims]
        caveats = [*final.caveats, *_price_caveat(claims, self.price_source)]
        result.text = render(final.text, claims, caveats, self.tx_url)


class NaiveAgent:
    """Baseline: all raw transfers in the context window, no tools, no verification."""

    def __init__(
        self, llm: LLMClient, registry: ToolRegistry, audit: AuditLog | None = None
    ) -> None:
        self.llm = llm
        data = registry.tools.data
        self.system_prompt = naive_prompt(data, registry.tools.dao_name)
        self.tx_url = data.explorer_tx_url
        self.audit = audit or AuditLog(None)

    def answer(self, question: str) -> AgentResult:
        start = time.monotonic()
        result = AgentResult(question=question, config="naive", outcome=Outcome.ERROR, text="")
        messages: list[Message] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": question},
        ]
        try:
            for _ in range(2):
                resp = self.llm.chat(messages, [SUBMIT_SCHEMA], tool_choice="required")
                _usage(result, resp)
                call = next((c for c in resp.tool_calls if c.name == SUBMIT), None)
                if call is None:
                    messages += [
                        resp.message,
                        {"role": "user", "content": "Call submit_answer with your final answer."},
                    ]
                    continue
                try:
                    final = _parse_final(call.arguments)
                except (json.JSONDecodeError, ValidationError) as exc:
                    result.error = f"invalid final answer: {exc}"
                    break
                result.caveats = list(final.caveats)
                result.missing = final.missing
                result.claims = [c.model_dump() for c in final.claims]
                result.outcome = {
                    AnswerStatus.ANSWER: Outcome.ANSWER,
                    AnswerStatus.ABSTAIN: Outcome.ABSTAIN,
                    AnswerStatus.REFUSE: Outcome.REFUSE,
                }[final.status]
                result.text = render(final.text, final.claims, final.caveats, self.tx_url)
                break
        except LLMError as exc:
            result.error = str(exc)
        result.latency_s = time.monotonic() - start
        self.audit.write(result)
        return result
