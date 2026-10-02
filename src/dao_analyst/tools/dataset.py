"""In-memory, read-only view of the local store that the analytics tools compute over.

The dataset is small (hundreds of transfers), so tools work on Python objects with exact
integer arithmetic. DuckDB is only the storage format. The independent ground-truth script
in ``eval/`` queries DuckDB with plain SQL instead, so the two paths do not share logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from dao_analyst.config import NATIVE_TOKEN
from dao_analyst.store import db


@dataclass(frozen=True, slots=True)
class Row:
    transfer_id: str
    block_number: int
    block_time: datetime
    tx_hash: str
    kind: str
    from_address: str
    to_address: str
    token_address: str
    symbol: str
    decimals: int | None
    raw_amount: int
    token_verified: bool
    direction: str  # in | out | self

    @property
    def counterparty(self) -> str:
        return self.from_address if self.direction == "in" else self.to_address


@dataclass(frozen=True, slots=True)
class TokenInfo:
    address: str
    symbol: str
    decimals: int
    price_id: str | None


@dataclass(frozen=True, slots=True)
class LabelInfo:
    address: str
    name: str
    category: str
    source: str


@dataclass(frozen=True, slots=True)
class BalanceCheck:
    address: str
    token_address: str
    block_number: int
    onchain_raw: int
    computed_raw: int

    @property
    def matches(self) -> bool:
        return self.onchain_raw == self.computed_raw


@dataclass
class Dataset:
    rows: list[Row]
    tokens: dict[str, TokenInfo]  # verified tokens (incl. native) by address
    labels: dict[str, LabelInfo]
    prices: dict[tuple[str, date], Decimal]  # (price_id, day) -> USD
    price_source: str
    start_block: int
    end_block: int
    end_time: datetime
    treasury: frozenset[str]
    balance_checks: list[BalanceCheck]  # rebuilt vs on-chain balances at the end block
    explorer_tx_url: str
    chain_name: str

    @property
    def end_date(self) -> date:
        return self.end_time.date()

    def tx_url(self, tx_hash: str) -> str:
        return self.explorer_tx_url.format(tx_hash=tx_hash)

    def token_by_symbol(self, symbol: str) -> TokenInfo | None:
        s = symbol.strip().lower()
        return next((t for t in self.tokens.values() if t.symbol.lower() == s), None)

    def price(self, token: TokenInfo, day: date) -> Decimal | None:
        if token.price_id is None:
            return None
        return self.prices.get((token.price_id, day))

    @property
    def native(self) -> TokenInfo:
        return self.tokens[NATIVE_TOKEN]


def load_dataset(
    path: Path, treasury: frozenset[str], explorer_tx_url: str, chain_name: str
) -> Dataset:
    con = db.connect(path, read_only=True)
    try:
        rows = [
            Row(
                r[0],
                r[1],
                datetime.fromtimestamp(r[2], tz=UTC),
                r[3],
                r[4],
                r[5],
                r[6],
                r[7],
                r[8],
                r[9],
                int(r[10]),
                r[11],
                r[12],
            )
            for r in con.execute(
                "SELECT transfer_id, block_number, CAST(epoch(block_time) AS BIGINT), tx_hash, "
                "kind, from_address, to_address, token_address, symbol, decimals, raw_amount, "
                "token_verified, direction FROM transfers "
                "ORDER BY block_number, tx_hash, transfer_id"
            ).fetchall()
        ]
        tokens = {
            r[0]: TokenInfo(r[0], r[1], r[2], r[3])
            for r in con.execute(
                "SELECT token_address, symbol, decimals, price_id FROM tokens"
            ).fetchall()
        }
        labels = {
            r[0]: LabelInfo(r[0], r[1], r[2], r[3])
            for r in con.execute("SELECT address, name, category, source FROM labels").fetchall()
        }
        prices = {
            (r[0], r[1]): Decimal(repr(r[2]))
            for r in con.execute("SELECT price_id, day, usd FROM prices").fetchall()
        }
        meta = dict(con.execute("SELECT key, value FROM snapshot_meta").fetchall())
        checks = [
            BalanceCheck(r[0], r[1], r[2], int(r[3]), int(r[4]))
            for r in con.execute(
                "SELECT address, token_address, block_number, onchain_raw, computed_raw "
                "FROM balance_checks"
            ).fetchall()
        ]
    finally:
        con.close()
    return Dataset(
        rows=rows,
        tokens=tokens,
        labels=labels,
        prices=prices,
        price_source=meta.get("price_source", ""),
        start_block=int(meta["start_block"]),
        end_block=int(meta["end_block"]),
        end_time=datetime.fromtimestamp(int(meta["end_block_timestamp"]), tz=UTC),
        treasury=treasury,
        balance_checks=checks,
        explorer_tx_url=explorer_tx_url,
        chain_name=chain_name,
    )
