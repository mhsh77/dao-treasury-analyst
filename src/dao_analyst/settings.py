"""Runtime settings read from the environment (and an optional .env file)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    dao_config: Path = Path("config/dao.uniswap.yaml")
    fixtures_dir: Path = Path("fixtures")
    db_path: Path = Path("data/treasury.duckdb")

    etherscan_api_key: str | None = None
    etherscan_base_url: str = "https://api.etherscan.io/v2/api"
    eth_rpc_url: str | None = None
    defillama_base_url: str = "https://coins.llama.fi"

    # Requests per second; the Etherscan free tier currently allows 3/s.
    etherscan_rps: float = 2.5
    http_timeout_s: float = 30.0
    http_max_retries: int = 4


def get_settings() -> Settings:
    return Settings()
