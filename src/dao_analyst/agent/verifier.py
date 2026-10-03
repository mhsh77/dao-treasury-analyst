"""Claim verifier: checks every number in a final answer against stored tool results.

A claim is verified only if all of these hold:
1. every cited call id exists and the call succeeded;
2. its value equals a number in one of the cited results with a compatible unit, either
   exactly or as that number rounded to the claim's own decimal places (so "272134858.48"
   is accepted for 272134858.47907041001, but "272000000" is not);
3. every tx hash it lists appears in the cited results.
The prose is checked too: digits may appear only in claim placeholders, dates, quarters,
hex strings, or numbers copied from the question. Numbers the model computed itself are
unverifiable by design and therefore rejected.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from dao_analyst.agent.answer import Claim, FinalAnswer
from dao_analyst.agent.registry import ToolCallRecord

COUNT_KEYS = {"tx_count", "total_matching", "returned", "rank"}
BLOCK_KEYS = {"block_number", "snapshot_end_block"}
UNIT_ALIASES = {
    "$": "USD",
    "usd": "USD",
    "dollars": "USD",
    "us dollars": "USD",
    "count": "count",
    "transfers": "count",
    "transactions": "count",
    "tx": "count",
    "txs": "count",
    "counterparties": "count",
    "number": "count",
    "%": "percent",
    "percent": "percent",
    "pct": "percent",
    "block": "block",
    "blocks": "block",
}


@dataclass(frozen=True)
class Fact:
    value: Decimal
    unit: str
    path: str
    signed: bool = True  # False: magnitude may be stated without its sign (differences)


@dataclass
class ClaimCheck:
    claim_id: str
    verified: bool
    reason: str
    matched: str | None = None


@dataclass
class VerificationReport:
    claim_checks: list[ClaimCheck] = field(default_factory=list)
    prose_issues: list[str] = field(default_factory=list)
    incomplete_sources: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.verified for c in self.claim_checks) and not self.prose_issues

    @property
    def support_rate(self) -> float | None:
        if not self.claim_checks:
            return None
        return sum(c.verified for c in self.claim_checks) / len(self.claim_checks)

    def feedback(self) -> str:
        lines = [f"- claim {c.claim_id}: {c.reason}" for c in self.claim_checks if not c.verified]
        lines += [f"- text: {p}" for p in self.prose_issues]
        return (
            "Verification failed. Fix these problems and call submit_answer again. Every "
            "number must be copied exactly from a cited tool result (call a tool if you need "
            "a number you do not have; never compute it yourself):\n" + "\n".join(lines)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "support_rate": self.support_rate,
            "claims": [c.__dict__ for c in self.claim_checks],
            "prose_issues": self.prose_issues,
            "incomplete_sources": self.incomplete_sources,
        }


def normalize_unit(unit: str) -> str:
    u = unit.strip()
    return UNIT_ALIASES.get(u.lower(), u.upper())


def to_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        text = value.strip().replace(",", "").lstrip("$").rstrip("%")
        if not re.fullmatch(r"-?\d+(\.\d+)?", text):
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    return None


def extract_facts(node: Any, path: str = "", context_unit: str | None = None) -> Iterator[Fact]:
    """Every human-meaningful number in a tool result, with its unit."""
    if isinstance(node, dict):
        if {"token", "amount", "usd"} <= node.keys():  # Money
            if (v := to_decimal(node["amount"])) is not None:
                yield Fact(v, node["token"].upper(), f"{path}.amount")
            if (u := to_decimal(node["usd"])) is not None:
                yield Fact(u, "USD", f"{path}.usd")
            return
        if {"period", "value", "unit"} <= node.keys():  # PeriodValue
            unit = normalize_unit(node["unit"]) if node["unit"] else "count"
            if (v := to_decimal(node["value"])) is not None:
                yield Fact(v, unit, f"{path}.value")
            if (c := to_decimal(node.get("tx_count"))) is not None:
                yield Fact(c, "count", f"{path}.tx_count")
            return
        diff_unit = None
        if isinstance(node.get("period_a"), dict):
            diff_unit = normalize_unit(node["period_a"].get("unit") or "count")
        for key, value in node.items():
            p = f"{path}.{key}" if path else key
            if key == "total_usd" and (v := to_decimal(value)) is not None:
                yield Fact(v, "USD", p)
            elif key in COUNT_KEYS and (v := to_decimal(value)) is not None:
                yield Fact(v, "count", p)
            elif key in BLOCK_KEYS and (v := to_decimal(value)) is not None:
                yield Fact(v, "block", p)
            elif key == "difference" and (v := to_decimal(value)) is not None:
                yield Fact(v, diff_unit or "count", p, signed=False)
            elif key == "pct_change" and (v := to_decimal(value)) is not None:
                yield Fact(v, "percent", p, signed=False)
            elif key == "block_range" and isinstance(value, list):
                for i, b in enumerate(value):
                    if (v := to_decimal(b)) is not None:
                        yield Fact(v, "block", f"{p}[{i}]")
            elif isinstance(value, list):
                if key not in {"tx_hashes", "incomplete_reasons", "notes"}:
                    yield Fact(Decimal(len(value)), "count", f"len({p})")
                for i, item in enumerate(value):
                    yield from extract_facts(item, f"{p}[{i}]", context_unit)
            elif isinstance(value, dict):
                yield from extract_facts(value, p, context_unit)


def collect_hashes(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for v in node.values():
            found |= collect_hashes(v)
    elif isinstance(node, list):
        for v in node:
            found |= collect_hashes(v)
    elif isinstance(node, str) and re.fullmatch(r"0x[0-9a-f]{64}", node.lower()):
        found.add(node.lower())
    return found


def value_matches(claim: Decimal, fact: Fact) -> bool:
    candidates = [fact.value] if fact.signed else [fact.value, abs(fact.value)]
    for f in candidates:
        if claim == f:
            return True
        exponent = claim.as_tuple().exponent
        places = -exponent if isinstance(exponent, int) and exponent < 0 else 0
        f_exp = f.normalize().as_tuple().exponent
        f_places = -f_exp if isinstance(f_exp, int) and f_exp < 0 else 0
        if places < f_places and f.quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP) == claim:
            return True
    return False


ALLOWED_IN_PROSE = [
    r"\{c\w*\}",  # claim placeholders
    r"0x[0-9a-fA-F]+",  # addresses and hashes
    r"\b\d{4}-\d{2}-\d{2}(T[\d:+.Z-]*)?",  # ISO dates / timestamps
    r"\b\d{4}-\d{2}\b",  # year-month
    r"\bQ[1-4]\b",
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?\b",
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\b",
    r"\b\d{2}:\d{2}(?::\d{2})?\b",  # times of day
    r"\b(19|20)\d{2}\b",  # years
]


NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


def prose_numbers(text: str, question: str) -> list[str]:
    stripped = text
    for pattern in ALLOWED_IN_PROSE:
        stripped = re.sub(pattern, " ", stripped)
    allowed = set(NUMBER.findall(question))
    return [n for n in NUMBER.findall(stripped) if n not in allowed]


def verify_claim(claim: Claim, calls: dict[str, ToolCallRecord]) -> ClaimCheck:
    value = to_decimal(claim.value)
    if value is None:
        return ClaimCheck(claim.id, False, f"value {claim.value!r} is not a plain number")
    if not claim.source_call_ids:
        return ClaimCheck(claim.id, False, "no source_call_ids: cite the tool call it came from")
    results = []
    for cid in claim.source_call_ids:
        rec = calls.get(cid)
        if rec is None:
            return ClaimCheck(claim.id, False, f"cites unknown call id {cid!r}")
        if not rec.ok or rec.result is None:
            return ClaimCheck(claim.id, False, f"cites failed call {cid}")
        results.append((cid, rec.result.model_dump(mode="json")))
    unit = normalize_unit(claim.unit)
    match = None
    for cid, result in results:
        for fact in extract_facts(result):
            if fact.unit == unit and value_matches(value, fact):
                match = f"{cid}:{fact.path}"
                break
        if match:
            break
    if match is None:
        return ClaimCheck(
            claim.id,
            False,
            f"{claim.value} {claim.unit} does not appear in cited results "
            f"{', '.join(claim.source_call_ids)}",
        )
    known = set().union(*(collect_hashes(r) for _, r in results))
    unknown = [h for h in claim.tx_hashes if h.lower() not in known]
    if unknown:
        return ClaimCheck(
            claim.id, False, f"tx hashes not in cited results: {', '.join(unknown[:3])}"
        )
    return ClaimCheck(claim.id, True, "matches tool output", match)


def verify(answer: FinalAnswer, calls: list[ToolCallRecord], question: str) -> VerificationReport:
    by_id = {c.call_id: c for c in calls}
    report = VerificationReport()
    ids = [c.id for c in answer.claims]
    if len(ids) != len(set(ids)):
        report.prose_issues.append("claim ids must be unique")
    for claim in answer.claims:
        report.claim_checks.append(verify_claim(claim, by_id))
        for cid in claim.source_call_ids:
            rec = by_id.get(cid)
            if rec and rec.result is not None and not rec.result.data_complete:
                for reason in rec.result.incomplete_reasons:
                    if reason not in report.incomplete_sources:
                        report.incomplete_sources.append(reason)
    placeholders = set(re.findall(r"\{(c\w*)\}", answer.text))
    missing = placeholders - set(ids)
    if missing:
        report.prose_issues.append(f"text references undefined claims: {sorted(missing)}")
    stray = prose_numbers(answer.text, question)
    for extra in answer.caveats:
        stray += prose_numbers(extra, question)
    if stray:
        report.prose_issues.append(
            f"numbers written directly in the text: {stray[:5]}; put them in claims and "
            "reference them as {id}"
        )
    return report
