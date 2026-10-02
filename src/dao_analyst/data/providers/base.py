"""Provider interfaces. The rest of the pipeline depends only on these protocols.

Raw records are returned as the provider's own field names wrapped in small typed models,
so normalization has a single, provider-agnostic input shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RawNativeTx:
    """A top-level transaction (sent from an EOA)."""

    block_number: int
    timestamp: int
    tx_hash: str
    from_address: str
    to_address: str | None
    value_wei: int
    gas_used: int
    gas_price_wei: int
    is_error: bool


@dataclass(frozen=True, slots=True)
class RawInternalTx:
    """A value-carrying call inside a transaction (contract-to-contract or contract-to-EOA)."""

    block_number: int
    timestamp: int
    tx_hash: str
    trace_id: str
    from_address: str
    to_address: str | None
    value_wei: int
    is_error: bool


@dataclass(frozen=True, slots=True)
class RawTokenTransfer:
    """An ERC-20 Transfer event as reported by the provider."""

    block_number: int
    timestamp: int
    tx_hash: str
    log_index: int | None
    token_address: str
    token_symbol: str
    token_decimals: int | None
    from_address: str
    to_address: str
    raw_amount: int


class ChainDataProvider(Protocol):
    """Historical activity for one address on one EVM chain."""

    chain_id: int

    def native_txs(self, address: str, start_block: int, end_block: int) -> list[RawNativeTx]: ...

    def internal_txs(
        self, address: str, start_block: int, end_block: int
    ) -> list[RawInternalTx]: ...

    def token_transfers(
        self, address: str, start_block: int, end_block: int
    ) -> list[RawTokenTransfer]: ...

    def block_at_or_before(self, timestamp: int) -> int: ...


class BalanceProvider(Protocol):
    """Point-in-time balances, used to cross-check balances rebuilt from transfers."""

    def native_balance(self, address: str, block: int) -> int: ...

    def token_balance(self, token: str, address: str, block: int) -> int: ...


@dataclass(frozen=True, slots=True)
class DailyPrice:
    price_id: str
    day: date
    usd: float
    source: str


class PriceProvider(Protocol):
    def daily_prices(self, price_id: str, start: date, end: date) -> list[DailyPrice]: ...
