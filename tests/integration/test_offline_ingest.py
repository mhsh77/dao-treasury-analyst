"""Rebuilds the store from the committed fixtures, offline, and checks known facts."""

from __future__ import annotations

from pathlib import Path

from dao_analyst.config import load_dao_config
from dao_analyst.data.fetch import FetchMode
from dao_analyst.data.ingest import run_ingest
from dao_analyst.settings import Settings
from dao_analyst.store import db

ROOT = Path(__file__).resolve().parents[2]


def test_replay_rebuilds_store_and_balances_reconcile(tmp_path: Path) -> None:
    settings = Settings(
        dao_config=ROOT / "config/dao.uniswap.yaml",
        fixtures_dir=ROOT / "fixtures",
        db_path=tmp_path / "t.duckdb",
        etherscan_api_key=None,
        eth_rpc_url=None,
    )
    cfg = load_dao_config(settings.dao_config)
    cfg.labels_file = ROOT / "config/labels.uniswap.yaml"
    result = run_ingest(cfg, settings, FetchMode.REPLAY)

    assert result.snapshot.end_block == 25_433_938
    checked = [c for c in result.balance_checks if c["status"] == "checked"]
    assert len(checked) == 4 and all(c["match"] for c in checked)

    con = db.connect(settings.db_path, read_only=True)
    (n,) = con.execute("SELECT count(*) FROM transfers").fetchone()  # type: ignore[misc]
    assert n == result.transfers > 0
    (dupes,) = con.execute(  # type: ignore[misc]
        "SELECT count(*) - count(DISTINCT transfer_id) FROM transfers"
    ).fetchone()
    assert dupes == 0
