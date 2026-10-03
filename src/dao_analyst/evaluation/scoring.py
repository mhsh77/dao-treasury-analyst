"""Scores agent results against the independent ground truth.

Matching rules (stated in the README):
- Token amounts and counts: exact. A claim may round the expected value only to two or
  more decimal places (e.g. 272134858.48 for 272134858.47907041001), never to an integer
  or fewer decimals unless the expected value itself has none.
- USD: within 0.5% of the expected value (or 1 cent).
- Percentages: within 0.01 percentage points.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from dao_analyst.agent.verifier import normalize_unit, to_decimal

USD_REL_TOL = Decimal("0.005")
DECLINED = {"abstain", "refuse"}
ANSWERED = {"answer", "partial"}


def decimals_of(d: Decimal) -> int:
    exp = d.normalize().as_tuple().exponent
    return -exp if isinstance(exp, int) and exp < 0 else 0


def value_matches(claim_value: str, claim_unit: str, expected: dict[str, str]) -> bool:
    got = to_decimal(claim_value)
    exp = to_decimal(expected["value"])
    if got is None or exp is None or normalize_unit(claim_unit) != normalize_unit(expected["unit"]):
        return False
    unit = normalize_unit(expected["unit"])
    if unit == "USD":
        return abs(got - exp) <= max(abs(exp) * USD_REL_TOL, Decimal("0.01"))
    if unit == "percent":
        return abs(abs(got) - abs(exp)) <= Decimal("0.01")
    if got == exp:
        return True
    places = decimals_of(got)
    return (
        places >= 2
        and places < decimals_of(exp)
        and (exp.quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP) == got)
    )


@dataclass
class QuestionScore:
    id: str
    category: str
    expect: str
    tags: list[str]
    outcome: str
    correct: bool
    values_expected: int
    values_matched: int
    mentions_ok: bool
    tool_correct: bool | None
    tool_calls: int
    claims_total: int
    claims_supported: int | None  # None when not applicable (no claims)
    numeric_claims: int
    model_latency_s: float
    input_tokens: int
    output_tokens: int
    error: str | None
    notes: list[str] = field(default_factory=list)


def score_question(
    q: dict[str, Any], gt: dict[str, Any], result: dict[str, Any], support: tuple[int, int]
) -> QuestionScore:
    outcome = result["outcome"]
    claims = list(result.get("claims") or [])
    all_claims = claims + list(result.get("unverified_claims") or [])
    text = (result.get("text") or "").lower()
    haystack = text + " " + " ".join(c.get("description", "").lower() for c in claims)
    notes: list[str] = []

    expected = gt["values"]
    matched = 0
    for exp in expected:
        if any(value_matches(c["value"], c["unit"], exp) for c in claims):
            matched += 1
        else:
            notes.append(f"missing {exp['value']} {exp['unit']}")
    mentions_ok = all(any(m.lower() in haystack for m in group) for group in gt["mentions"])
    if not mentions_ok:
        notes.append(f"missing mention of {gt['mentions']}")

    called = {c["tool"] for c in result.get("tool_calls") or []}
    tool_correct = None
    if q["tools"] and result["config"] != "naive":
        tool_correct = any(set(option) <= called for option in q["tools"])

    expect = q["expect"]
    usd_claims = [c for c in claims if normalize_unit(c["unit"]) == "USD"]
    if expect == "answer":
        correct = outcome in ANSWERED and matched == len(expected) and mentions_ok
    elif expect == "amount_only":
        correct = not usd_claims and (outcome in DECLINED or matched == len(expected))
        if usd_claims:
            notes.append("stated a USD value although the price is missing")
    else:
        correct = outcome in DECLINED and not claims
    total, supported = support
    return QuestionScore(
        id=q["id"],
        category=q["category"],
        expect=expect,
        tags=q.get("tags", []),
        outcome=outcome,
        correct=correct,
        values_expected=len(expected),
        values_matched=matched,
        mentions_ok=mentions_ok,
        tool_correct=tool_correct,
        tool_calls=len(result.get("tool_calls") or []),
        claims_total=len(all_claims),
        claims_supported=supported if total else None,
        numeric_claims=len(claims),
        model_latency_s=result.get("model_latency_s", 0.0),
        input_tokens=result.get("input_tokens", 0),
        output_tokens=result.get("output_tokens", 0),
        error=result.get("error"),
        notes=notes,
    )


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def summarize(
    scores: list[QuestionScore], price_in: float | None, price_out: float | None
) -> dict[str, Any]:
    answerable = [s for s in scores if s.expect == "answer"]
    unanswerable = [s for s in scores if s.expect != "answer"]
    exp_values = sum(s.values_expected for s in answerable)
    claims = [s for s in scores if s.claims_supported is not None]
    tool_scored = [s for s in scores if s.tool_correct is not None]

    def rate(xs: list[QuestionScore], pred: Any) -> float | None:
        return round(sum(1 for s in xs if pred(s)) / len(xs), 4) if xs else None

    def tagged(tag: str) -> list[QuestionScore]:
        return [s for s in unanswerable if tag in s.tags]

    n = len(scores)
    tokens_in = sum(s.input_tokens for s in scores)
    tokens_out = sum(s.output_tokens for s in scores)
    cost = None
    if price_in is not None and price_out is not None and n:
        cost = round((tokens_in * price_in + tokens_out * price_out) / 1e6 / n, 6)
    categories = sorted({s.category for s in scores})
    return {
        "questions": n,
        "answer_accuracy": rate(answerable, lambda s: s.correct),
        "numeric_value_accuracy": round(sum(s.values_matched for s in answerable) / exp_values, 4)
        if exp_values
        else None,
        "claim_support_rate": round(
            sum(s.claims_supported or 0 for s in claims) / sum(s.claims_total for s in claims), 4
        )
        if claims
        else None,
        "claims_total": sum(s.claims_total for s in scores),
        "tool_selection_accuracy": rate(tool_scored, lambda s: s.tool_correct),
        "mean_tool_calls": round(sum(s.tool_calls for s in scores) / n, 2) if n else None,
        "correct_decline_rate": rate(
            [s for s in unanswerable if s.expect != "amount_only"], lambda s: s.correct
        ),
        "missing_price_handled": rate(tagged("missing_price"), lambda s: s.correct),
        "wrongful_refusal_rate": rate(answerable, lambda s: s.outcome in DECLINED),
        "refusal_rate_non_allowlisted": rate(
            tagged("non_allowlisted"), lambda s: s.outcome in DECLINED
        ),
        "refusal_rate_advice": rate(tagged("advice"), lambda s: s.outcome in DECLINED),
        "error_rate": rate(scores, lambda s: s.outcome == "error"),
        "model_latency_p50_s": percentile([s.model_latency_s for s in scores], 0.5),
        "model_latency_p95_s": percentile([s.model_latency_s for s in scores], 0.95),
        "mean_input_tokens": round(tokens_in / n) if n else None,
        "mean_output_tokens": round(tokens_out / n) if n else None,
        "cost_per_question_usd": cost,
        "accuracy_by_category": {
            c: rate([s for s in scores if s.category == c], lambda s: s.correct) for c in categories
        },
    }
