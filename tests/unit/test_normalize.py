from __future__ import annotations

import pytest

from dao_analyst.config import NATIVE_TOKEN, DaoConfig
from dao_analyst.data.normalize import (
    GAS_SINK,
    DecimalsMismatchError,
    Direction,
    Kind,
    Normalizer,
)
from dao_analyst.data.providers.base import RawInternalTx, RawNativeTx, RawTokenTransfer
from tests.conftest import ALICE, BOB, FAKE_UNI, TREASURY, TREASURY_2, UNI, USDC


def tok(
    tx: str,
    token: str,
    frm: str,
    to: str,
    amount: int,
    *,
    symbol: str = "UNI",
    decimals: int | None = 18,
    block: int = 100,
    log_index: int | None = None,
) -> RawTokenTransfer:
    return RawTokenTransfer(
        block, 1_700_000_000, tx, log_index, token, symbol, decimals, frm, to, amount
    )


def native(
    tx: str,
    frm: str,
    to: str,
    value: int,
    *,
    error: bool = False,
    gas_used: int = 21_000,
    gas_price: int = 10**9,
) -> RawNativeTx:
    return RawNativeTx(100, 1_700_000_000, tx, frm, to, value, gas_used, gas_price, error)


def internal(
    tx: str, frm: str, to: str, value: int, *, trace: str = "0_1", error: bool = False
) -> RawInternalTx:
    return RawInternalTx(100, 1_700_000_000, tx, trace, frm, to, value, error)


def run(cfg: DaoConfig, *, native_txs=None, internal_txs=None, tokens=None, address=TREASURY):
    n = Normalizer(cfg)
    out = n.normalize(
        {address: native_txs or []}, {address: internal_txs or []}, {address: tokens or []}
    )
    return out, n.report


# --- decimals ---------------------------------------------------------------------------


def test_verified_token_uses_config_decimals_and_keeps_exact_raw_amount(cfg: DaoConfig) -> None:
    amount = 13_142_986_710_000_000_000_000_000  # 13,142,986.71 UNI
    out, _ = run(cfg, tokens=[tok("0x1", UNI, TREASURY, ALICE, amount)])
    assert out[0].raw_amount == amount
    assert (out[0].decimals, out[0].symbol, out[0].token_verified) == (18, "UNI", True)


def test_six_decimal_token(cfg: DaoConfig) -> None:
    out, _ = run(
        cfg, tokens=[tok("0x1", USDC, ALICE, TREASURY, 95_383_000, symbol="USDC", decimals=6)]
    )
    assert out[0].decimals == 6 and out[0].raw_amount == 95_383_000


def test_decimals_mismatch_with_config_is_an_error(cfg: DaoConfig) -> None:
    with pytest.raises(DecimalsMismatchError):
        run(cfg, tokens=[tok("0x1", USDC, ALICE, TREASURY, 1, symbol="USDC", decimals=18)])


def test_unverified_token_keeps_reported_decimals_and_huge_amounts(cfg: DaoConfig) -> None:
    huge = 2**255  # spam tokens routinely exceed 128-bit integers
    out, report = run(cfg, tokens=[tok("0x1", FAKE_UNI, ALICE, TREASURY, huge, decimals=None)])
    assert out[0].raw_amount == huge and out[0].decimals is None
    assert report.unverified_token_transfers == 1


def test_symbol_lookalike_is_not_verified(cfg: DaoConfig) -> None:
    out, _ = run(cfg, tokens=[tok("0x1", FAKE_UNI, ALICE, TREASURY, 10**18, symbol="UNI")])
    assert out[0].symbol == "UNI" and out[0].token_verified is False


# --- failed, zero-value, gas -------------------------------------------------------------


def test_zero_amount_transfers_are_dropped(cfg: DaoConfig) -> None:
    out, report = run(cfg, tokens=[tok("0x1", USDC, TREASURY, ALICE, 0, symbol="USDC", decimals=6)])
    assert out == [] and report.dropped_zero_amount == 1


def test_failed_native_tx_moves_no_value_but_treasury_still_pays_gas(cfg: DaoConfig) -> None:
    out, report = run(cfg, native_txs=[native("0x1", TREASURY, ALICE, 5 * 10**18, error=True)])
    assert report.dropped_failed == 1
    assert [(t.kind, t.to_address, t.raw_amount) for t in out] == [
        (Kind.GAS_FEE, GAS_SINK, 21_000 * 10**9)
    ]


def test_incoming_native_tx_has_no_gas_entry(cfg: DaoConfig) -> None:
    out, _ = run(cfg, native_txs=[native("0x1", ALICE, TREASURY, 10**17)])
    assert [(t.kind, t.direction, t.token_address) for t in out] == [
        (Kind.NATIVE, Direction.IN, NATIVE_TOKEN)
    ]


# --- internal transactions -----------------------------------------------------------------


def test_internal_pass_through_records_both_legs(cfg: DaoConfig) -> None:
    # Governor sends ETH into the treasury, which forwards it in the same tx.
    out, _ = run(
        cfg,
        internal_txs=[
            internal("0x1", ALICE, TREASURY, 10**16, trace="0_1"),
            internal("0x1", TREASURY, BOB, 10**16, trace="0_1_1"),
        ],
    )
    assert [(t.direction, t.raw_amount) for t in out] == [
        (Direction.IN, 10**16),
        (Direction.OUT, 10**16),
    ]


def test_failed_and_zero_value_internal_calls_are_dropped(cfg: DaoConfig) -> None:
    out, report = run(
        cfg,
        internal_txs=[
            internal("0x1", ALICE, TREASURY, 10**16, error=True),
            internal("0x2", ALICE, TREASURY, 0),
        ],
    )
    assert out == [] and report.dropped_failed == 1


# --- duplicates ------------------------------------------------------------------------------


def test_identical_transfers_in_one_tx_are_both_kept(cfg: DaoConfig) -> None:
    t = tok("0x1", UNI, TREASURY, ALICE, 10**18)
    out, report = run(cfg, tokens=[t, t])
    assert len(out) == 2 and report.merged_duplicates == 0
    assert len({x.transfer_id for x in out}) == 2


def test_transfer_between_two_treasury_addresses_is_kept_once(cfg: DaoConfig) -> None:
    t = tok("0x1", UNI, TREASURY, TREASURY_2, 10**18)
    n = Normalizer(cfg)
    out = n.normalize({}, {}, {TREASURY: [t], TREASURY_2: [t]})
    assert len(out) == 1 and out[0].direction is Direction.SELF
    assert n.report.merged_duplicates == 1


def test_log_index_distinguishes_otherwise_identical_transfers(cfg: DaoConfig) -> None:
    a = tok("0x1", UNI, TREASURY, ALICE, 10**18, log_index=3)
    b = tok("0x1", UNI, TREASURY, ALICE, 10**18, log_index=7)
    out, _ = run(cfg, tokens=[a, b])
    assert len(out) == 2


def test_output_is_deterministically_ordered(cfg: DaoConfig) -> None:
    txs = [tok(f"0x{i}", UNI, TREASURY, ALICE, 10**18, block=200 - i) for i in range(5)]
    out, _ = run(cfg, tokens=txs)
    assert [t.block_number for t in out] == sorted(t.block_number for t in out)
