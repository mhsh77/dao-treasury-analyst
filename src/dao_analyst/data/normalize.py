"""Turn raw provider records into one flat, typed list of treasury transfers.

Rules (each one is covered by a unit test):
- Failed transactions and failed internal calls move no value and are dropped.
- Zero-amount transfers are dropped (they are a common address-poisoning trick).
- Gas paid by a treasury address is recorded as a ``gas_fee`` outflow, even if the tx failed.
- Tokens are verified by contract address against the config, never by symbol.
- The same transfer reported under several treasury addresses is kept once, while
  genuinely identical transfers inside one transaction are all kept (see ``_with_ids``).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from dao_analyst.config import NATIVE_TOKEN, DaoConfig
from dao_analyst.data.providers.base import RawInternalTx, RawNativeTx, RawTokenTransfer

GAS_SINK = "0x0000000000000000000000000000000000000000"


class Kind(StrEnum):
    NATIVE = "native"
    INTERNAL = "internal"
    ERC20 = "erc20"
    GAS_FEE = "gas_fee"


class Direction(StrEnum):
    IN = "in"
    OUT = "out"
    SELF = "self"  # between two treasury addresses


class DecimalsMismatchError(ValueError):
    """The provider reports different decimals than the hand-verified token config."""


@dataclass(frozen=True, slots=True)
class Transfer:
    transfer_id: str
    chain_id: int
    block_number: int
    block_time: datetime
    tx_hash: str
    kind: Kind
    from_address: str
    to_address: str
    token_address: str
    symbol: str
    decimals: int | None
    raw_amount: int
    token_verified: bool
    direction: Direction


@dataclass(slots=True)
class NormalizationReport:
    kept: int = 0
    dropped_failed: int = 0
    dropped_zero_amount: int = 0
    merged_duplicates: int = 0
    unverified_token_transfers: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Draft:
    content_key: str
    block_number: int
    timestamp: int
    tx_hash: str
    kind: Kind
    from_address: str
    to_address: str
    token_address: str
    symbol: str
    decimals: int | None
    raw_amount: int
    token_verified: bool


def _with_ids(drafts: Sequence[_Draft]) -> list[tuple[str, _Draft]]:
    """Assign ids as ``content_key#occurrence`` within one provider list.

    Two identical transfers in one tx get ``#0`` and ``#1`` and both survive; the same
    transfer seen again in another treasury address's list maps to the same id and merges.
    """
    seen: Counter[str] = Counter()
    out = []
    for d in drafts:
        out.append((f"{d.content_key}#{seen[d.content_key]}", d))
        seen[d.content_key] += 1
    return out


class Normalizer:
    def __init__(self, config: DaoConfig) -> None:
        self._cfg = config
        self._treasury = config.treasury_set
        self._tokens = config.token_by_address
        self.report = NormalizationReport()

    def _direction(self, src: str, dst: str) -> Direction | None:
        s, d = src in self._treasury, dst in self._treasury
        if s and d:
            return Direction.SELF
        if s:
            return Direction.OUT
        if d:
            return Direction.IN
        return None

    def _native_drafts(self, txs: Iterable[RawNativeTx]) -> list[_Draft]:
        chain = self._cfg.chain
        out = []
        for tx in txs:
            if tx.from_address in self._treasury:
                fee = tx.gas_used * tx.gas_price_wei
                if fee > 0:
                    out.append(
                        _Draft(
                            f"{tx.tx_hash}:gas",
                            tx.block_number,
                            tx.timestamp,
                            tx.tx_hash,
                            Kind.GAS_FEE,
                            tx.from_address,
                            GAS_SINK,
                            NATIVE_TOKEN,
                            chain.native_symbol,
                            chain.native_decimals,
                            fee,
                            True,
                        )
                    )
            if tx.is_error:
                self.report.dropped_failed += 1
                continue
            if tx.value_wei == 0 or tx.to_address is None:
                continue  # plain contract calls carry no value
            out.append(
                _Draft(
                    f"{tx.tx_hash}:native",
                    tx.block_number,
                    tx.timestamp,
                    tx.tx_hash,
                    Kind.NATIVE,
                    tx.from_address,
                    tx.to_address,
                    NATIVE_TOKEN,
                    chain.native_symbol,
                    chain.native_decimals,
                    tx.value_wei,
                    True,
                )
            )
        return out

    def _internal_drafts(self, txs: Iterable[RawInternalTx]) -> list[_Draft]:
        chain = self._cfg.chain
        out = []
        for tx in txs:
            if tx.is_error:
                self.report.dropped_failed += 1
                continue
            if tx.value_wei == 0 or tx.to_address is None:
                continue
            key = (
                f"{tx.tx_hash}:internal:{tx.trace_id}:"
                f"{tx.from_address}:{tx.to_address}:{tx.value_wei}"
            )
            out.append(
                _Draft(
                    key,
                    tx.block_number,
                    tx.timestamp,
                    tx.tx_hash,
                    Kind.INTERNAL,
                    tx.from_address,
                    tx.to_address,
                    NATIVE_TOKEN,
                    chain.native_symbol,
                    chain.native_decimals,
                    tx.value_wei,
                    True,
                )
            )
        return out

    def _token_drafts(self, transfers: Iterable[RawTokenTransfer]) -> list[_Draft]:
        out = []
        for t in transfers:
            if t.raw_amount == 0:
                self.report.dropped_zero_amount += 1
                continue
            cfg = self._tokens.get(t.token_address)
            decimals: int | None
            if cfg is not None:
                if t.token_decimals is not None and t.token_decimals != cfg.decimals:
                    raise DecimalsMismatchError(
                        f"{cfg.symbol} {t.token_address}: provider says {t.token_decimals}, "
                        f"config says {cfg.decimals}"
                    )
                symbol, decimals, verified = cfg.symbol, cfg.decimals, True
            else:
                symbol, decimals, verified = t.token_symbol, t.token_decimals, False
            key = (
                f"{t.tx_hash}:erc20:{t.log_index if t.log_index is not None else ''}:"
                f"{t.token_address}:{t.from_address}:{t.to_address}:{t.raw_amount}"
            )
            out.append(
                _Draft(
                    key,
                    t.block_number,
                    t.timestamp,
                    t.tx_hash,
                    Kind.ERC20,
                    t.from_address,
                    t.to_address,
                    t.token_address,
                    symbol,
                    decimals,
                    t.raw_amount,
                    verified,
                )
            )
        return out

    def normalize(
        self,
        native: dict[str, list[RawNativeTx]],
        internal: dict[str, list[RawInternalTx]],
        tokens: dict[str, list[RawTokenTransfer]],
    ) -> list[Transfer]:
        """Inputs are keyed by the treasury address whose history they came from."""
        merged: dict[str, _Draft] = {}
        for address in self._treasury:
            lists = (
                self._native_drafts(native.get(address, [])),
                self._internal_drafts(internal.get(address, [])),
                self._token_drafts(tokens.get(address, [])),
            )
            for drafts in lists:
                for transfer_id, draft in _with_ids(drafts):
                    if transfer_id in merged:
                        self.report.merged_duplicates += 1
                    else:
                        merged[transfer_id] = draft

        result = []
        for transfer_id, d in merged.items():
            direction = self._direction(d.from_address, d.to_address)
            if direction is None:
                self.report.notes.append(f"skipped transfer not touching treasury: {transfer_id}")
                continue
            if not d.token_verified:
                self.report.unverified_token_transfers += 1
            result.append(
                Transfer(
                    transfer_id=transfer_id,
                    chain_id=self._cfg.chain.chain_id,
                    block_number=d.block_number,
                    block_time=datetime.fromtimestamp(d.timestamp, tz=UTC),
                    tx_hash=d.tx_hash,
                    kind=d.kind,
                    from_address=d.from_address,
                    to_address=d.to_address,
                    token_address=d.token_address,
                    symbol=d.symbol,
                    decimals=d.decimals,
                    raw_amount=d.raw_amount,
                    token_verified=d.token_verified,
                    direction=direction,
                )
            )
        result.sort(key=lambda t: (t.block_number, t.tx_hash, t.transfer_id))
        self.report.kept = len(result)
        return result
