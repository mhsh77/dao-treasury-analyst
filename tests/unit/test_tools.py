"""Tool tests on a tiny hand-built dataset. Expected values are computed by hand."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from dao_analyst.config import NATIVE_TOKEN
from dao_analyst.tools.analytics import (
    GroupBy,
    Metric,
    SortBy,
    ToolInputError,
    TreasuryTools,
    format_amount,
)
from dao_analyst.tools.dataset import BalanceCheck, Dataset, LabelInfo, Row, TokenInfo
from dao_analyst.tools.models import DateRange, FlowDirection

T = "0x" + "aa" * 20  # treasury
T2 = "0x" + "ab" * 20  # second treasury address
GRANTEE = "0x" + "01" * 20  # labeled grant recipient
FOUNDATION = "0x" + "02" * 20  # labeled foundation
STRANGER = "0x" + "03" * 20  # unlabeled
VESTER = "0x" + "04" * 20  # labeled vesting contract
UNI = "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
SPAM = "0x" + "fe" * 20
E18 = 10**18


def h(n: int) -> str:
    return "0x" + f"{n:064x}"


def row(
    n: int,
    day: date,
    frm: str,
    to: str,
    token: str,
    raw: int,
    *,
    direction: str,
    verified: bool = True,
    symbol: str | None = None,
    decimals: int | None = None,
    kind: str = "erc20",
) -> Row:
    sym = symbol or {UNI: "UNI", USDC: "USDC", NATIVE_TOKEN: "ETH"}.get(token, "SPAM")
    dec = decimals if decimals is not None else {USDC: 6}.get(token, 18)
    return Row(
        f"t{n}",
        1000 + n,
        datetime(day.year, day.month, day.day, 12, tzinfo=UTC),
        h(n),
        kind,
        frm,
        to,
        token,
        sym,
        dec,
        raw,
        verified,
        direction,
    )


def make(checks: list[BalanceCheck] | None = None) -> TreasuryTools:
    rows = [
        row(1, date(2024, 1, 10), VESTER, T, UNI, 1000 * E18, direction="in"),
        row(2, date(2024, 2, 5), T, GRANTEE, UNI, 100 * E18, direction="out"),
        row(3, date(2024, 2, 20), T, FOUNDATION, UNI, 250 * E18, direction="out"),
        row(4, date(2024, 4, 2), T, GRANTEE, USDC, 5_000_000_000, direction="out", decimals=6),
        row(5, date(2024, 4, 3), FOUNDATION, T, USDC, 7_500_000_000, direction="in", decimals=6),
        row(6, date(2024, 5, 1), T, T2, UNI, 10 * E18, direction="self"),
        row(7, date(2024, 5, 2), STRANGER, T, SPAM, 10**30, direction="in", verified=False),
        row(8, date(2024, 6, 1), T, STRANGER, UNI, 50 * E18, direction="out"),
        row(
            9, date(2024, 6, 2), STRANGER, T, NATIVE_TOKEN, E18 // 2, direction="in", kind="native"
        ),
        row(
            10,
            date(2024, 6, 3),
            T,
            "0x" + "00" * 20,
            NATIVE_TOKEN,
            10**15,
            direction="out",
            kind="gas_fee",
        ),
    ]
    tokens = {
        UNI: TokenInfo(UNI, "UNI", 18, "uni"),
        USDC: TokenInfo(USDC, "USDC", 6, "usdc"),
        NATIVE_TOKEN: TokenInfo(NATIVE_TOKEN, "ETH", 18, "eth"),
    }
    labels = {
        GRANTEE: LabelInfo(GRANTEE, "Example Grants Multisig", "grant_recipient", "src"),
        FOUNDATION: LabelInfo(FOUNDATION, "Example Foundation", "foundation", "src"),
        VESTER: LabelInfo(VESTER, "Treasury vester", "vesting", "src"),
    }
    prices = {}
    d = date(2024, 1, 1)
    while d <= date(2024, 6, 30):
        prices[("uni", d)] = Decimal("10") if d < date(2024, 3, 1) else Decimal("5")
        prices[("usdc", d)] = Decimal("1")
        prices[("eth", d)] = Decimal("3000")
        d = date.fromordinal(d.toordinal() + 1)
    del prices[("uni", date(2024, 6, 1))]  # one missing price
    data = Dataset(
        rows=rows,
        tokens=tokens,
        labels=labels,
        prices=prices,
        price_source="test prices",
        start_block=0,
        end_block=2000,
        end_time=datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC),
        treasury=frozenset({T, T2}),
        balance_checks=checks or [],
        explorer_tx_url="https://etherscan.io/tx/{tx_hash}",
        chain_name="Ethereum",
    )
    return TreasuryTools(data, "Test DAO")


def rng(a: date, b: date) -> DateRange:
    return DateRange(start=a, end=b)


# --- formatting ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "dec", "expected"),
    [
        (0, 18, "0"),
        (1, 18, "0.000000000000000001"),
        (12_500_000 * E18 + 1, 18, "12500000.000000000000000001"),
        (135_383_008, 6, "135.383008"),
        (5_000_000_000, 6, "5000"),
        (2**255, None, str(2**255)),
    ],
)
def test_format_amount_is_exact(raw: int, dec: int | None, expected: str) -> None:
    assert format_amount(raw, dec) == expected


# --- balances ----------------------------------------------------------------------------


def test_balance_counts_in_out_gas_and_ignores_internal_moves_and_spam() -> None:
    res = make().get_balance_summary(date(2024, 6, 30))
    by = {m.token: m for m in res.holdings}
    assert by["UNI"].amount == "600"  # 1000 - 100 - 250 - 50; the T->T2 move nets to zero
    assert by["USDC"].amount == "2500"
    assert by["ETH"].amount == "0.499"  # 0.5 in, 0.001 gas
    assert by["UNI"].usd == "3000.00" and by["ETH"].usd == "1497.00"
    assert res.total_usd == "6997.00"
    assert res.data_complete


def test_balance_as_of_is_end_of_day_inclusive() -> None:
    res = make().get_balance_summary(date(2024, 2, 5))
    uni = next(m for m in res.holdings if m.token == "UNI")
    assert uni.amount == "900" and uni.usd == "9000.00"
    assert res.evidence.tx_hashes == [h(1), h(2)]


def test_balance_after_snapshot_is_incomplete() -> None:
    res = make().get_balance_summary(date(2024, 7, 1))
    assert not res.data_complete and "after the snapshot end" in res.incomplete_reasons[0]


def test_balance_with_missing_price_reports_amount_only() -> None:
    res = make().get_balance_summary(date(2024, 6, 1))
    uni = next(m for m in res.holdings if m.token == "UNI")
    assert (
        uni.amount == "600"
        and uni.usd is None
        and "no pinned UNI price" in (uni.usd_missing_reason or "")
    )
    assert res.total_usd is None


def test_balance_mismatch_with_chain_is_flagged() -> None:
    bad = BalanceCheck(T, UNI, 2000, onchain_raw=1, computed_raw=2)
    res = make([bad]).get_balance_summary()
    assert not res.data_complete and "does not match" in res.incomplete_reasons[0]


# --- list_transfers ----------------------------------------------------------------------


def test_list_transfers_filters_and_links() -> None:
    res = make().list_transfers(direction=FlowDirection.OUT, token="uni")
    assert [t.value.amount for t in res.transfers] == ["100", "250", "50"]
    assert res.transfers[0].tx_url == f"https://etherscan.io/tx/{h(2)}"
    assert res.transfers[0].counterparty_label == "Example Grants Multisig"
    assert res.transfers[0].value.usd == "1000.00"  # priced on the transfer day


def test_min_amount_is_in_token_units_and_needs_a_token() -> None:
    tools = make()
    res = tools.list_transfers(token="UNI", min_amount="100", direction=FlowDirection.OUT)
    assert [t.value.amount for t in res.transfers] == ["100", "250"]
    with pytest.raises(ToolInputError):
        tools.list_transfers(min_amount="1")


def test_limit_and_sort() -> None:
    res = make().list_transfers(direction=FlowDirection.OUT, sort=SortBy.AMOUNT_DESC, limit=2)
    # by USD at transfer time: 5000 USDC ($5000) > 250 UNI @10 ($2500) > 100 UNI ($1000)
    assert [t.tx_hash for t in res.transfers] == [h(4), h(3)]
    assert res.total_matching == 5 and res.returned == 2 and res.notes


def test_counterparty_by_label_name_and_unlabeled_address_is_refused() -> None:
    tools = make()
    res = tools.list_transfers(counterparty="foundation")
    assert {t.tx_hash for t in res.transfers} == {h(3), h(5)}
    with pytest.raises(ToolInputError, match="not a labeled"):
        tools.list_transfers(counterparty=STRANGER)


def test_unverified_tokens_only_on_request() -> None:
    tools = make()
    assert all(t.token_verified for t in tools.list_transfers().transfers)
    res = tools.list_transfers(include_unverified=True, direction=FlowDirection.IN)
    spam = [t for t in res.transfers if not t.token_verified]
    assert spam and spam[0].value.usd is None


def test_range_past_snapshot_is_incomplete() -> None:
    res = make().list_transfers(date_range=rng(date(2024, 6, 1), date(2024, 12, 31)))
    assert not res.data_complete


def test_unknown_token_is_an_input_error() -> None:
    with pytest.raises(ToolInputError, match="Verified tokens"):
        make().list_transfers(token="SPAM")


# --- aggregate_flows ---------------------------------------------------------------------


def test_aggregate_by_month_uses_transfer_day_prices() -> None:
    res = make().aggregate_flows(GroupBy.MONTH, FlowDirection.OUT, token="UNI")
    by = {g.key: g for g in res.groups}
    assert by["2024-02"].amounts[0].amount == "350" and by["2024-02"].total_usd == "3500.00"
    assert by["2024-06"].total_usd is None  # 2024-06-01 has no UNI price
    assert "2024-05" not in by  # the internal move is not an outflow


def test_aggregate_by_category_for_grant_questions() -> None:
    res = make().aggregate_flows(
        GroupBy.CATEGORY, FlowDirection.OUT, date_range=rng(date(2024, 1, 1), date(2024, 6, 30))
    )
    grants = next(g for g in res.groups if g.key == "grant_recipient")
    assert sorted((m.token, m.amount) for m in grants.amounts) == [("UNI", "100"), ("USDC", "5000")]
    assert grants.total_usd == "6000.00" and grants.tx_count == 2


def test_aggregate_any_direction_keeps_directions_apart() -> None:
    res = make().aggregate_flows(GroupBy.TOKEN, token="USDC")
    assert {(g.key, g.direction, g.amounts[0].amount) for g in res.groups} == {
        ("USDC", "in", "7500"),
        ("USDC", "out", "5000"),
    }


# --- top_counterparties ------------------------------------------------------------------


def test_top_counterparties_by_usd() -> None:
    res = make().top_counterparties(FlowDirection.OUT, rng(date(2024, 1, 1), date(2024, 5, 31)))
    assert [(c.label, c.total_usd) for c in res.counterparties] == [
        ("Example Grants Multisig", "6000.00"),
        ("Example Foundation", "2500.00"),
    ]


def test_top_counterparties_by_token_amount_and_unpriced_flag() -> None:
    res = make().top_counterparties(FlowDirection.OUT, token="UNI", n=1)
    assert res.counterparties[0].label == "Example Foundation"
    assert res.ranked_by == "UNI amount" and res.data_complete
    res = make().top_counterparties(FlowDirection.OUT)  # stranger's UNI has no price that day
    assert not res.data_complete


def test_ranking_requires_direction() -> None:
    with pytest.raises(ToolInputError):
        make().top_counterparties(FlowDirection.ANY)


# --- get_transaction ---------------------------------------------------------------------


def test_get_transaction_found_and_not_found() -> None:
    tools = make()
    res = tools.get_transaction(h(3).upper().replace("0X", "0x"))
    assert res.found and res.transfers[0].to_label == "Example Foundation"
    missing = tools.get_transaction(h(999))
    assert not missing.found and not missing.data_complete
    with pytest.raises(ToolInputError):
        tools.get_transaction("0x123")


# --- compare_periods ---------------------------------------------------------------------


def test_compare_periods_token_outflow() -> None:
    res = make().compare_periods(
        Metric.OUTFLOW,
        rng(date(2024, 1, 1), date(2024, 3, 31)),
        rng(date(2024, 4, 1), date(2024, 6, 30)),
        token="UNI",
    )
    assert (res.period_a.value, res.period_b.value) == ("350", "50")
    assert res.difference == "-300" and res.pct_change == "-85.71"


def test_compare_periods_zero_base_and_counts() -> None:
    res = make().compare_periods(
        Metric.INFLOW,
        rng(date(2024, 2, 1), date(2024, 2, 29)),
        rng(date(2024, 4, 1), date(2024, 4, 30)),
        token="USDC",
    )
    assert res.period_a.value == "0" and res.pct_change is None and res.notes
    res = make().compare_periods(
        Metric.TRANSFER_COUNT,
        rng(date(2024, 1, 1), date(2024, 3, 31)),
        rng(date(2024, 4, 1), date(2024, 6, 30)),
    )
    assert (res.period_a.value, res.period_b.value) == ("3", "5")


def test_compare_end_balance() -> None:
    res = make().compare_periods(
        Metric.END_BALANCE,
        rng(date(2024, 1, 1), date(2024, 1, 31)),
        rng(date(2024, 2, 1), date(2024, 2, 29)),
        token="UNI",
    )
    assert (res.period_a.value, res.period_b.value, res.difference) == ("1000", "650", "-350")
