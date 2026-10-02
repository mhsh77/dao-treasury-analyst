from __future__ import annotations

import pytest

from dao_analyst.agent.answer import Claim
from dao_analyst.agent.policy import Policy
from dao_analyst.agent.render import fill_placeholders, render

T = "0x1a9c8182c09f50c8318d769245bea52c32be35bc"
P = Policy({T}, ["Timelock"])


@pytest.mark.parametrize(
    "q",
    [
        "Should we buy more UNI?",
        "Should the DAO diversify into ETH?",
        "What's your price prediction for UNI?",
        "Will the UNI price go up next year?",
        "Forecast the ETH price for 2027",
        "Is UNI a good investment?",
        "Give me some investment advice about the treasury",
    ],
)
def test_advice_and_predictions_are_refused(q: str) -> None:
    d = P.check(q)
    assert d is not None and d.reason == "advice_or_prediction"


@pytest.mark.parametrize(
    "q",
    [
        "What was the UNI balance on 2024-01-01?",
        "How much UNI did the treasury send to the Uniswap Foundation?",
        "Compare outflows in 2024 and 2025",
        f"Show transfers from {T}",
        "What did the treasury hold at the end of the snapshot?",
    ],
)
def test_factual_questions_pass(q: str) -> None:
    assert P.check(q) is None


def test_unknown_address_is_refused_but_tx_hash_is_not() -> None:
    d = P.check("Profile 0x5069a64bc6616dec1584ee0500b7813a9b680f7e please")
    assert d is not None and d.reason == "non_allowlisted_address"
    assert P.check("Explain tx 0x" + "ab" * 32) is None


def c(cid: str, value: str, unit: str, hashes: list[str] | None = None) -> Claim:
    return Claim(
        id=cid,
        value=value,
        unit=unit,
        description="d",
        source_call_ids=["c1"],
        tx_hashes=hashes or [],
    )


def test_render_formats_units_and_links() -> None:
    claims = [
        c("c1", "1234567.5", "UNI", ["0x" + "a" * 64]),
        c("c2", "-300", "USD"),
        c("c3", "12.5", "percent"),
        c("c4", "7", "count"),
    ]
    out = render(
        "{c1}; {c2}; {c3}; {c4} transfers; {c9}",
        claims,
        ["note"],
        "https://etherscan.io/tx/{tx_hash}",
    )
    assert out.startswith("1,234,567.5 UNI; -$300.00; 12.5%; 7 transfers; [unverified]")
    assert "https://etherscan.io/tx/0x" + "a" * 64 in out and "- note" in out


def test_unit_written_after_placeholder_is_not_duplicated() -> None:
    claims = [c("c1", "5", "UNI"), c("c2", "10", "USD")]
    assert fill_placeholders("{c1} UNI or ${c2} USD", claims) == "5 UNI or $10.00"
