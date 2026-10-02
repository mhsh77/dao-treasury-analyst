"""End-to-end ingestion: providers -> normalization -> DuckDB.

``record`` mode calls the real APIs and writes every response under ``fixtures/raw``.
``replay`` mode rebuilds the identical database from those fixtures with no network and
no API keys. The snapshot end block is pinned in ``fixtures/snapshot.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import structlog

from dao_analyst.config import NATIVE_TOKEN, DaoConfig, TokenConfig, load_labels
from dao_analyst.data.fetch import (
    FetchMode,
    FixtureMissingError,
    FixtureStore,
    HttpFetcher,
    ReplayFetcher,
)
from dao_analyst.data.normalize import Normalizer, Transfer
from dao_analyst.data.providers.base import (
    BalanceProvider,
    ChainDataProvider,
    DailyPrice,
    PriceProvider,
)
from dao_analyst.data.providers.defillama import DefiLlamaPriceProvider
from dao_analyst.data.providers.etherscan import EtherscanProvider
from dao_analyst.data.providers.rpc import RpcBalanceProvider
from dao_analyst.settings import Settings
from dao_analyst.store import db

log = structlog.get_logger(__name__)


class SnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class Snapshot:
    chain_id: int
    start_block: int
    end_block: int
    end_timestamp: str  # ISO-8601 UTC, as configured
    end_block_timestamp: int

    @classmethod
    def load(cls, path: Path) -> Snapshot:
        return cls(**json.loads(path.read_text()))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")


@dataclass
class Providers:
    chain: ChainDataProvider
    prices: PriceProvider
    balances: BalanceProvider | None


@dataclass
class IngestResult:
    snapshot: Snapshot
    transfers: int
    report: dict[str, Any]
    balance_checks: list[dict[str, Any]] = field(default_factory=list)


def build_providers(cfg: DaoConfig, settings: Settings, mode: FetchMode) -> Providers:
    store = FixtureStore(settings.fixtures_dir / "raw")
    if mode is FetchMode.REPLAY:
        fetcher: HttpFetcher | ReplayFetcher = ReplayFetcher(store)
    else:
        if not settings.etherscan_api_key:
            raise SystemExit(
                "ETHERSCAN_API_KEY is required for live/record mode (see .env.example)"
            )
        fetcher = HttpFetcher(
            store=store if mode is FetchMode.RECORD else None,
            timeout_s=settings.http_timeout_s,
            max_retries=settings.http_max_retries,
            min_interval_s={"etherscan": 1.0 / settings.etherscan_rps},
        )
    chain = EtherscanProvider(
        fetcher,
        chain_id=cfg.chain.chain_id,
        api_key=settings.etherscan_api_key,
        base_url=settings.etherscan_base_url,
    )
    has_rpc = mode is FetchMode.REPLAY or bool(settings.eth_rpc_url)
    balances = (
        RpcBalanceProvider(fetcher, chain_id=cfg.chain.chain_id, rpc_url=settings.eth_rpc_url)
        if has_rpc
        else None
    )
    return Providers(chain, DefiLlamaPriceProvider(fetcher, settings.defillama_base_url), balances)


def resolve_snapshot(
    cfg: DaoConfig, chain: EtherscanProvider | ChainDataProvider, path: Path, mode: FetchMode
) -> Snapshot:
    configured = cfg.snapshot.end_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    if path.exists():
        snap = Snapshot.load(path)
        if (snap.end_timestamp, snap.start_block, snap.chain_id) != (
            configured,
            cfg.snapshot.start_block,
            cfg.chain.chain_id,
        ):
            raise SnapshotError(
                f"{path} pins {snap.end_timestamp} (start {snap.start_block}) but config says "
                f"{configured} (start {cfg.snapshot.start_block}). Delete it and re-record."
            )
        return snap
    if mode is FetchMode.REPLAY:
        raise SnapshotError(f"{path} is missing; run ingestion in record mode first")
    end_block = chain.block_at_or_before(int(cfg.snapshot.end_timestamp.timestamp()))
    block_ts = (
        chain.block_timestamp(end_block)
        if isinstance(chain, EtherscanProvider)
        else int(cfg.snapshot.end_timestamp.timestamp())
    )
    snap = Snapshot(cfg.chain.chain_id, cfg.snapshot.start_block, end_block, configured, block_ts)
    snap.save(path)
    return snap


def native_token(cfg: DaoConfig) -> TokenConfig:
    return TokenConfig(
        address=NATIVE_TOKEN,
        symbol=cfg.chain.native_symbol,
        decimals=cfg.chain.native_decimals,
        price_id=cfg.native_price_id,
        source="Native asset of the configured chain",
    )


def computed_balance(transfers: list[Transfer], address: str, token: str) -> int:
    total = 0
    for t in transfers:
        if t.token_address != token:
            continue
        if t.to_address == address:
            total += t.raw_amount
        if t.from_address == address:
            total -= t.raw_amount
    return total


def run_ingest(cfg: DaoConfig, settings: Settings, mode: FetchMode) -> IngestResult:
    providers = build_providers(cfg, settings, mode)
    snap = resolve_snapshot(cfg, providers.chain, settings.fixtures_dir / "snapshot.json", mode)
    log.info("ingest.snapshot", **asdict(snap), mode=mode.value)

    native, internal, tokens = {}, {}, {}
    for t in cfg.treasury_addresses:
        a = t.address
        native[a] = providers.chain.native_txs(a, snap.start_block, snap.end_block)
        internal[a] = providers.chain.internal_txs(a, snap.start_block, snap.end_block)
        tokens[a] = providers.chain.token_transfers(a, snap.start_block, snap.end_block)
        log.info(
            "ingest.fetched",
            address=a,
            native=len(native[a]),
            internal=len(internal[a]),
            tokens=len(tokens[a]),
        )

    normalizer = Normalizer(cfg)
    transfers = normalizer.normalize(native, internal, tokens)

    # Prices: one daily series per priced, verified asset, from the first transfer to the end.
    end_day = datetime.fromtimestamp(snap.end_block_timestamp, tz=UTC).date()
    start_day = min((t.block_time.date() for t in transfers), default=end_day)
    priced = [tok for tok in [native_token(cfg), *cfg.tokens] if tok.price_id]
    prices: list[DailyPrice] = []
    for tok in priced:
        assert tok.price_id is not None
        prices.extend(providers.prices.daily_prices(tok.price_id, start_day, end_day))

    checks = balance_checks(cfg, providers.balances, transfers, snap)

    con = db.connect(settings.db_path)
    try:
        db.reset(con)
        db.insert_transfers(con, transfers)
        db.insert_tokens(con, cfg.tokens, native_token(cfg))
        if cfg.labels_file is not None:
            db.insert_labels(con, load_labels(cfg.labels_file))
        db.insert_prices(con, prices)
        for c in checks:
            if c["status"] == "checked":
                db.insert_balance_check(
                    con,
                    c["address"],
                    c["token"],
                    snap.end_block,
                    int(c["onchain_raw"]),
                    int(c["computed_raw"]),
                )
        report = asdict(normalizer.report)
        db.set_meta(
            con,
            {
                "dao_id": cfg.dao.id,
                "chain_id": str(cfg.chain.chain_id),
                "start_block": str(snap.start_block),
                "end_block": str(snap.end_block),
                "end_timestamp": snap.end_timestamp,
                "end_block_timestamp": str(snap.end_block_timestamp),
                "price_source": prices[0].source if prices else "",
                "price_first_day": min((p.day for p in prices), default=date.min).isoformat(),
                "ingest_mode": mode.value,
                "normalization_report": json.dumps(report, sort_keys=True),
            },
        )
    finally:
        con.close()
    log.info(
        "ingest.done",
        transfers=len(transfers),
        prices=len(prices),
        **{k: v for k, v in report.items() if k != "notes"},
    )
    return IngestResult(snap, len(transfers), report, checks)


def balance_checks(
    cfg: DaoConfig, balances: BalanceProvider | None, transfers: list[Transfer], snap: Snapshot
) -> list[dict[str, Any]]:
    """Compare balances rebuilt from transfers with on-chain balances at the end block."""
    if balances is None:
        return [{"status": "skipped", "reason": "no RPC configured"}]
    if snap.start_block != 0:
        return [{"status": "skipped", "reason": "window does not start at genesis"}]
    out: list[dict[str, Any]] = []
    for t in cfg.treasury_addresses:
        for tok in [native_token(cfg), *cfg.tokens]:
            try:
                if tok.address == NATIVE_TOKEN:
                    onchain = balances.native_balance(t.address, snap.end_block)
                else:
                    onchain = balances.token_balance(tok.address, t.address, snap.end_block)
            except FixtureMissingError:
                out.append(
                    {
                        "status": "skipped",
                        "reason": "no recorded RPC response",
                        "address": t.address,
                        "token": tok.address,
                    }
                )
                continue
            computed = computed_balance(transfers, t.address, tok.address)
            out.append(
                {
                    "status": "checked",
                    "address": t.address,
                    "token": tok.address,
                    "symbol": tok.symbol,
                    "onchain_raw": str(onchain),
                    "computed_raw": str(computed),
                    "match": onchain == computed,
                }
            )
    return out
