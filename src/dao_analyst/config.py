"""DAO configuration: treasury addresses, snapshot window, verified tokens and labels.

Everything here is hand-verified and carries a source URL. Addresses are normalized to
lowercase on load so the rest of the code never has to think about checksum casing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

NATIVE_TOKEN = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"


def _normalize_address(value: str) -> str:
    v = value.strip().lower()
    if not (v.startswith("0x") and len(v) == 42 and all(c in "0123456789abcdef" for c in v[2:])):
        raise ValueError(f"not an EVM address: {value!r}")
    return v


class TreasuryAddress(BaseModel):
    address: str
    name: str
    source: str
    note: str = ""

    _norm = field_validator("address")(_normalize_address)


class TokenConfig(BaseModel):
    address: str
    symbol: str
    decimals: int = Field(ge=0, le=77)
    price_id: str | None = None
    source: str

    _norm = field_validator("address")(_normalize_address)


class ChainConfig(BaseModel):
    chain_id: int
    name: str
    explorer_tx_url: str
    explorer_address_url: str
    native_symbol: str = "ETH"
    native_decimals: int = 18


class SnapshotConfig(BaseModel):
    start_block: int = 0
    end_timestamp: datetime

    @field_validator("end_timestamp")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return v.astimezone(UTC) if v.tzinfo else v.replace(tzinfo=UTC)


class DaoInfo(BaseModel):
    id: str
    name: str


class Label(BaseModel):
    address: str
    name: str
    category: str
    source: str
    note: str = ""

    _norm = field_validator("address")(_normalize_address)


class DaoConfig(BaseModel):
    dao: DaoInfo
    chain: ChainConfig
    treasury_addresses: list[TreasuryAddress]
    snapshot: SnapshotConfig
    tokens: list[TokenConfig]
    native_price_id: str | None = None
    labels_file: Path | None = None

    @property
    def treasury_set(self) -> frozenset[str]:
        return frozenset(t.address for t in self.treasury_addresses)

    @property
    def token_by_address(self) -> dict[str, TokenConfig]:
        return {t.address: t for t in self.tokens}


def load_dao_config(path: Path) -> DaoConfig:
    with path.open() as f:
        return DaoConfig.model_validate(yaml.safe_load(f))


def load_labels(path: Path) -> list[Label]:
    with path.open() as f:
        raw = yaml.safe_load(f) or {}
    labels = [Label.model_validate(item) for item in raw.get("labels", [])]
    seen: set[str] = set()
    for label in labels:
        if label.address in seen:
            raise ValueError(f"duplicate label for {label.address}")
        seen.add(label.address)
    return labels
