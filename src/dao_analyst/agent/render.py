"""Turns a verified FinalAnswer into user-facing text with explorer links and caveats."""

from __future__ import annotations

import re
from decimal import Decimal

from dao_analyst.agent.answer import Claim
from dao_analyst.agent.verifier import normalize_unit, to_decimal


def group_digits(value: str) -> str:
    sign = "-" if value.startswith("-") else ""
    whole, _, frac = value.lstrip("-").partition(".")
    whole = f"{int(whole):,}"
    return sign + whole + (f".{frac}" if frac else "")


def format_claim(claim: Claim) -> str:
    unit = normalize_unit(claim.unit)
    value = to_decimal(claim.value)
    text = group_digits(format(value, "f")) if value is not None else claim.value
    if unit == "USD":
        if value is not None:
            text = group_digits(format(value.quantize(Decimal("0.01")), "f"))
        return f"${text.lstrip('-')}" if not text.startswith("-") else f"-${text[1:]}"
    if unit == "percent":
        return f"{text}%"
    if unit in {"count", "block"}:
        return text
    return f"{text} {claim.unit.upper()}"


PLACEHOLDER = re.compile(r"(\$\s?)?\{(c\w*)\}(\s*%|\s+(?:US\s?dollars|[A-Za-z]{2,10}))?")


def fill_placeholders(text: str, claims: list[Claim]) -> str:
    """Substitutes formatted values, absorbing a unit the model also wrote ("{c1} UNI")."""
    by_id = {c.id: c for c in claims}

    def sub(m: re.Match[str]) -> str:
        claim = by_id.get(m.group(2))
        if claim is None:
            return "[unverified]"
        trailing = m.group(3) or ""
        word = trailing.strip()
        unit = normalize_unit(claim.unit)
        # Counts and percents print without a unit, so their trailing noun must stay.
        if word == "%" and unit == "percent":
            trailing = ""  # "{c1}%": the formatted percent already ends in %
        elif word and unit not in {"count", "percent", "block"} and normalize_unit(word) == unit:
            trailing = ""
        return format_claim(claim) + trailing

    return PLACEHOLDER.sub(sub, text)


def render(
    text: str, claims: list[Claim], caveats: list[str], tx_url: str, max_links: int = 8
) -> str:
    out = [fill_placeholders(text, claims).strip()]
    hashes = list(dict.fromkeys(h.lower() for c in claims for h in c.tx_hashes))
    if hashes:
        out.append("\nSupporting transactions:")
        out += [f"- {tx_url.format(tx_hash=h)}" for h in hashes[:max_links]]
        if len(hashes) > max_links:
            out.append(f"- ...and {len(hashes) - max_links} more")
    if caveats:
        out.append("\nCaveats:")
        out += [f"- {c}" for c in dict.fromkeys(caveats)]
    return "\n".join(out)
