from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from dao_analyst.agent.answer import AnswerStatus, Claim, FinalAnswer
from dao_analyst.agent.registry import ToolRegistry
from dao_analyst.agent.verifier import Fact, prose_numbers, value_matches, verify
from tests.unit.test_tools import h, make


@pytest.fixture
def reg() -> ToolRegistry:
    r = ToolRegistry(make())
    r.execute("get_balance_summary", '{"as_of": "2024-06-30"}')  # c1
    r.execute("list_transfers", '{"direction": "out", "token": "UNI"}')  # c2
    r.execute(
        "compare_periods",
        '{"metric": "outflow", "token": "UNI", '
        '"period_a": {"start": "2024-01-01", "end": "2024-03-31"}, '
        '"period_b": {"start": "2024-04-01", "end": "2024-06-30"}}',
    )  # c3
    r.execute("list_transfers", '{"date_range": {"start": "2024-06-01", "end": "2024-12-31"}}')
    return r


def answer(*claims: Claim, text: str = "See {c1}.") -> FinalAnswer:
    return FinalAnswer(status=AnswerStatus.ANSWER, text=text, claims=list(claims))


def claim(
    value: str, unit: str, *calls: str, cid: str = "c1", hashes: list[str] | None = None
) -> Claim:
    return Claim(
        id=cid,
        value=value,
        unit=unit,
        description="x",
        source_call_ids=list(calls),
        tx_hashes=hashes or [],
    )


def test_exact_and_rounded_values_verify(reg: ToolRegistry) -> None:
    for value in ["600", "3000.00", "3000"]:
        unit = "UNI" if value == "600" else "USD"
        rep = verify(answer(claim(value, unit, "c1")), reg.log, "q")
        assert rep.ok, rep.as_dict()


def test_wrong_value_wrong_unit_and_fabricated_numbers_fail(reg: ToolRegistry) -> None:
    assert not verify(answer(claim("601", "UNI", "c1")), reg.log, "q").ok
    assert not verify(answer(claim("600", "USD", "c1")), reg.log, "q").ok  # unit mismatch
    assert not verify(answer(claim("6000", "UNI", "c1")), reg.log, "q").ok  # 10x error


def test_value_from_an_uncited_call_does_not_count(reg: ToolRegistry) -> None:
    # 250 UNI exists in c2 (list_transfers) but not in c1 (balances).
    assert verify(answer(claim("250", "UNI", "c2")), reg.log, "q").ok
    assert not verify(answer(claim("250", "UNI", "c1")), reg.log, "q").ok


def test_unknown_or_missing_call_ids_fail(reg: ToolRegistry) -> None:
    assert not verify(answer(claim("600", "UNI", "c99")), reg.log, "q").ok
    assert not verify(answer(claim("600", "UNI")), reg.log, "q").ok


def test_model_arithmetic_is_rejected(reg: ToolRegistry) -> None:
    # 100 + 250 = 350 is not a value any cited result contains (c2 lists them separately).
    assert not verify(answer(claim("350", "UNI", "c2")), reg.log, "q").ok
    # ...but compare_periods computed it, so citing that verifies.
    assert verify(answer(claim("350", "UNI", "c3")), reg.log, "q").ok


def test_differences_and_percentages(reg: ToolRegistry) -> None:
    assert verify(answer(claim("-300", "UNI", "c3")), reg.log, "q").ok
    assert verify(answer(claim("300", "UNI", "c3")), reg.log, "q").ok  # stated as a decrease
    assert verify(answer(claim("85.71", "percent", "c3")), reg.log, "q").ok
    assert verify(answer(claim("85.7", "%", "c3")), reg.log, "q").ok


def test_tx_hashes_must_come_from_cited_results(reg: ToolRegistry) -> None:
    good = claim("250", "UNI", "c2", hashes=[h(3)])
    bad = claim("250", "UNI", "c2", hashes=["0x" + "9" * 64])
    assert verify(answer(good), reg.log, "q").ok
    assert not verify(answer(bad), reg.log, "q").ok


def test_numbers_in_prose_are_rejected_unless_dates_or_from_question(reg: ToolRegistry) -> None:
    c = claim("600", "UNI", "c1")
    assert not verify(answer(c, text="Holds {c1}, about 600 tokens."), reg.log, "q").ok
    assert verify(
        answer(c, text="On June 30, 2024 (2024-06-30, Q2) it held {c1}."), reg.log, "q"
    ).ok
    assert verify(answer(c, text="Of the top 5, it held {c1}."), reg.log, "top 5 please").ok
    assert not verify(answer(c, text="It held {c2}."), reg.log, "q").ok  # undefined claim


def test_incomplete_sources_are_reported(reg: ToolRegistry) -> None:
    rep = verify(answer(claim("1", "count", "c4", cid="c1")), reg.log, "q")
    assert rep.incomplete_sources and "after the snapshot end" in rep.incomplete_sources[0]


def test_value_matching_rules() -> None:
    f = Fact(Decimal("272134858.47907041001"), "UNI", "p")
    assert value_matches(Decimal("272134858.48"), f)
    assert value_matches(Decimal("272134858"), f)
    assert not value_matches(Decimal("272000000"), f)
    assert not value_matches(Decimal("272134858.4"), Fact(Decimal("272134858.47"), "UNI", "p"))


def test_prose_number_scanner() -> None:
    assert prose_numbers("At 23:59:59 on 1st Jan 2024 and Dec 31, 2025 for 0xabc123", "") == []
    assert prose_numbers("roughly 1,000 UNI", "") == ["1,000"]


def test_date_type_args_do_not_leak(reg: ToolRegistry) -> None:
    assert reg.log[0].result is not None
    assert reg.log[0].result.model_dump()["as_of_date"] == date(2024, 6, 30)
