"""Builds the tool layer from settings and DAO config."""

from __future__ import annotations

from dao_analyst.config import DaoConfig
from dao_analyst.settings import Settings
from dao_analyst.tools.analytics import TreasuryTools
from dao_analyst.tools.dataset import load_dataset


def build_tools(cfg: DaoConfig, settings: Settings) -> TreasuryTools:
    data = load_dataset(
        settings.db_path, cfg.treasury_set, cfg.chain.explorer_tx_url, cfg.chain.name
    )
    return TreasuryTools(data, cfg.dao.name)
