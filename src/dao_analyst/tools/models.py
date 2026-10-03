"""Typed arguments and results for the analytics tools.

Every result carries the evidence behind its numbers (tx hashes and the block range it
covers) and an explicit ``data_complete`` flag with human-readable reasons when false.
Token amounts are exact decimal strings; USD values are strings rounded to cents and are
always tied to the pinned price snapshot.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class FlowDirection(StrEnum):
    IN = "in"
    OUT = "out"
    ANY = "any"


class DateRange(BaseModel):
    """Inclusive UTC calendar-day range."""

    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> DateRange:
        if self.start > self.end:
            raise ValueError("date_range.start must be on or before date_range.end")
        return self


class Evidence(BaseModel):
    block_range: tuple[int, int] = Field(description="First and last block the result covers")
    tx_hashes: list[str] = Field(default_factory=list)
    tx_count: int = 0


class Money(BaseModel):
    """A token amount, optionally valued in USD with the pinned price snapshot."""

    token: str
    token_address: str
    amount: str = Field(description="Exact token amount as a decimal string")
    raw_amount: str
    decimals: int | None = Field(description="None for unverified tokens with unknown decimals")
    usd: str | None = Field(default=None, description="USD value rounded to cents, if priced")
    usd_missing_reason: str | None = None


class ToolResult(BaseModel):
    tool: str
    data_complete: bool = True
    incomplete_reasons: list[str] = Field(default_factory=list)
    evidence: Evidence
    price_note: str | None = None
    notes: list[str] = Field(default_factory=list)

    def mark_incomplete(self, reason: str) -> None:
        self.data_complete = False
        if reason not in self.incomplete_reasons:
            self.incomplete_reasons.append(reason)

    def for_llm(self, max_hashes: int = 10) -> dict[str, Any]:
        """Compact JSON for the model's context. The full result is kept for verification."""
        data = self.model_dump(mode="json")
        ev = data["evidence"]
        if len(ev["tx_hashes"]) > max_hashes:
            ev["tx_hashes"] = ev["tx_hashes"][:max_hashes]
            ev["tx_hashes_truncated"] = True
        return data


# --- per-tool payloads ------------------------------------------------------------------


class BalanceSummary(ToolResult):
    as_of_date: date
    holdings: list[Money]
    total_usd: str | None = None


class TransferRow(BaseModel):
    tx_hash: str
    tx_url: str
    block_number: int
    timestamp: str
    direction: str
    kind: str
    counterparty: str
    counterparty_label: str | None
    value: Money
    token_verified: bool


class TransferList(ToolResult):
    total_matching: int
    returned: int
    transfers: list[TransferRow]


class FlowGroup(BaseModel):
    key: str
    label: str | None = None
    direction: str
    amounts: list[Money]
    total_usd: str | None = None
    tx_count: int
    tx_hashes: list[str]


class FlowAggregate(ToolResult):
    group_by: str
    groups: list[FlowGroup]


class Counterparty(BaseModel):
    rank: int
    address: str
    label: str | None
    category: str | None
    amounts: list[Money]
    total_usd: str | None
    tx_count: int
    tx_hashes: list[str]


class CounterpartyRanking(ToolResult):
    ranked_by: str
    direction: str
    counterparties: list[Counterparty]


class TxTransfer(BaseModel):
    kind: str
    direction: str
    from_address: str
    from_label: str | None
    to_address: str
    to_label: str | None
    value: Money
    token_verified: bool


class TransactionDetail(ToolResult):
    tx_hash: str
    found: bool
    tx_url: str | None = None
    block_number: int | None = None
    timestamp: str | None = None
    transfers: list[TxTransfer] = Field(default_factory=list)


class PeriodValue(BaseModel):
    period: DateRange
    value: str | None
    unit: str
    tx_count: int


class PeriodComparison(ToolResult):
    metric: str
    token: str | None
    period_a: PeriodValue
    period_b: PeriodValue
    difference: str | None = Field(description="period_b minus period_a")
    pct_change: str | None = Field(description="Percent change from A to B, 2 decimals")


class SnapshotInfo(ToolResult):
    dao: str
    chain: str
    treasury_addresses: list[dict[str, str]]
    snapshot_end_block: int
    snapshot_end_utc: str
    first_activity_utc: str | None
    verified_tokens: list[str]
    price_source: str
