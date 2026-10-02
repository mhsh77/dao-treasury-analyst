"""Local analytical store (DuckDB).

Raw amounts are stored as exact decimal strings (``raw_amount``). Spam tokens can carry
uint256 values far beyond DuckDB's 128-bit HUGEINT, and every downstream sum is done on
Python ints, so no figure is ever rounded through a float.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import duckdb

from dao_analyst.config import Label, TokenConfig
from dao_analyst.data.normalize import Transfer
from dao_analyst.data.providers.base import DailyPrice

SCHEMA = """
CREATE TABLE IF NOT EXISTS transfers (
    transfer_id    VARCHAR PRIMARY KEY,
    chain_id       INTEGER NOT NULL,
    block_number   BIGINT NOT NULL,
    block_time     TIMESTAMPTZ NOT NULL,
    tx_hash        VARCHAR NOT NULL,
    kind           VARCHAR NOT NULL,
    from_address   VARCHAR NOT NULL,
    to_address     VARCHAR NOT NULL,
    token_address  VARCHAR NOT NULL,
    symbol         VARCHAR NOT NULL,
    decimals       INTEGER,
    raw_amount     VARCHAR NOT NULL,
    token_verified BOOLEAN NOT NULL,
    direction      VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (
    token_address VARCHAR PRIMARY KEY,
    symbol        VARCHAR NOT NULL,
    decimals      INTEGER NOT NULL,
    price_id      VARCHAR,
    source        VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS labels (
    address  VARCHAR PRIMARY KEY,
    name     VARCHAR NOT NULL,
    category VARCHAR NOT NULL,
    source   VARCHAR NOT NULL,
    note     VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS prices (
    price_id VARCHAR NOT NULL,
    day      DATE NOT NULL,
    usd      DOUBLE NOT NULL,
    source   VARCHAR NOT NULL,
    PRIMARY KEY (price_id, day)
);
CREATE TABLE IF NOT EXISTS snapshot_meta (
    key   VARCHAR PRIMARY KEY,
    value VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS balance_checks (
    address       VARCHAR NOT NULL,
    token_address VARCHAR NOT NULL,
    block_number  BIGINT NOT NULL,
    onchain_raw   VARCHAR NOT NULL,
    computed_raw  VARCHAR NOT NULL,
    PRIMARY KEY (address, token_address, block_number)
);
"""

TABLES = ("transfers", "tokens", "labels", "prices", "snapshot_meta", "balance_checks")


def _executemany(
    con: duckdb.DuckDBPyConnection, sql: str, rows: list[tuple[object, ...]], chunk: int = 500
) -> None:
    """Multi-row INSERT in chunks; DuckDB's executemany is slow and rejects empty lists."""
    if not rows:
        return
    head, _, values = sql.partition(" VALUES ")
    for i in range(0, len(rows), chunk):
        part = rows[i : i + chunk]
        con.execute(
            f"{head} VALUES " + ", ".join([values] * len(part)), [v for row in part for v in row]
        )


def connect(path: Path | str, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    if isinstance(path, Path):
        path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path), read_only=read_only)
    if not read_only:
        con.execute(SCHEMA)
    return con


def reset(con: duckdb.DuckDBPyConnection) -> None:
    for table in TABLES:
        con.execute(f"DELETE FROM {table}")


def insert_transfers(con: duckdb.DuckDBPyConnection, transfers: Sequence[Transfer]) -> None:
    _executemany(
        con,
        "INSERT INTO transfers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                t.transfer_id,
                t.chain_id,
                t.block_number,
                t.block_time,
                t.tx_hash,
                t.kind.value,
                t.from_address,
                t.to_address,
                t.token_address,
                t.symbol,
                t.decimals,
                str(t.raw_amount),
                t.token_verified,
                t.direction.value,
            )
            for t in transfers
        ],
    )


def insert_tokens(
    con: duckdb.DuckDBPyConnection, tokens: Iterable[TokenConfig], native: TokenConfig
) -> None:
    _executemany(
        con,
        "INSERT INTO tokens VALUES (?, ?, ?, ?, ?)",
        [(t.address, t.symbol, t.decimals, t.price_id, t.source) for t in [native, *tokens]],
    )


def insert_labels(con: duckdb.DuckDBPyConnection, labels: Iterable[Label]) -> None:
    _executemany(
        con,
        "INSERT INTO labels VALUES (?, ?, ?, ?, ?)",
        [(lb.address, lb.name, lb.category, lb.source, lb.note) for lb in labels],
    )


def insert_prices(con: duckdb.DuckDBPyConnection, prices: Iterable[DailyPrice]) -> None:
    _executemany(
        con,
        "INSERT INTO prices VALUES (?, ?, ?, ?)",
        [(p.price_id, p.day, p.usd, p.source) for p in prices],
    )


def set_meta(con: duckdb.DuckDBPyConnection, values: dict[str, str]) -> None:
    _executemany(con, "INSERT OR REPLACE INTO snapshot_meta VALUES (?, ?)", list(values.items()))


def insert_balance_check(
    con: duckdb.DuckDBPyConnection,
    address: str,
    token: str,
    block: int,
    onchain: int,
    computed: int,
) -> None:
    con.execute(
        "INSERT OR REPLACE INTO balance_checks VALUES (?, ?, ?, ?, ?)",
        (address, token, block, str(onchain), str(computed)),
    )
