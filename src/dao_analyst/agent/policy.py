"""Code-level guardrails applied before the model sees a question.

These are deliberately conservative (few false positives); the model's own refusal behavior
is the second layer. The eval measures both together.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ADDRESS = re.compile(r"\b0x[0-9a-fA-F]{40}\b(?![0-9a-fA-F])")
ADVICE_PATTERNS = [
    r"\bshould (i|we|you|the dao|they|uniswap)\b.{0,60}\b(buy|sell|hold|invest|swap|stake|"
    r"diversif\w*|dump|short|long)\b",
    r"\b(price|token) (prediction|forecast|target)s?\b",
    r"\b(predict|forecast)\w*\b.{0,40}\b(price|value|uni|eth|token|market)\b",
    r"\bwill\b.{0,40}\b(price|uni|eth|token)\b.{0,40}\b(go up|go down|rise|fall|increase|"
    r"decrease|drop|pump|moon|reach|hit)\b",
    r"\b(investment|financial|trading) advice\b",
    r"\b(good|bad|smart) (investment|buy|time to buy|time to sell)\b",
    r"\bworth (buying|investing)\b",
    r"\b(buy|sell) signal\b",
]
ADVICE = [re.compile(p, re.IGNORECASE) for p in ADVICE_PATTERNS]


@dataclass(frozen=True)
class PolicyDecision:
    reason: str  # machine-readable: non_allowlisted_address | advice_or_prediction
    message: str


class Policy:
    def __init__(self, allowlisted: set[str], treasury_names: list[str]) -> None:
        self._allowed = {a.lower() for a in allowlisted}
        self._names = treasury_names

    def check(self, question: str) -> PolicyDecision | None:
        outside = [a for a in ADDRESS.findall(question) if a.lower() not in self._allowed]
        if outside:
            return PolicyDecision(
                "non_allowlisted_address",
                f"I can't analyze {outside[0]}. I only report on the configured treasury "
                f"({'; '.join(self._names)}) and hand-verified institutional counterparties. "
                "Looking up other addresses could mean profiling private individuals, so it is "
                "outside this tool's scope.",
            )
        if any(p.search(question) for p in ADVICE):
            return PolicyDecision(
                "advice_or_prediction",
                "I can't give investment advice, price predictions or trading recommendations. "
                "I only report verified facts about the treasury's on-chain activity, for "
                "example holdings, flows and transactions up to the snapshot.",
            )
        return None
