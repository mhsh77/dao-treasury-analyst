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

    # LLM (any OpenAI-compatible provider; see dao_analyst.llm.client.PROVIDERS)
    llm_provider: str = "gemini"
    llm_model: str = "gemini-3.5-flash-lite"
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    audit_log: Path | None = Path("logs/audit.jsonl")

    # Telegram bot
    telegram_bot_token: str | None = None
    telegram_allowed_users: str = ""  # comma-separated numeric ids; empty = public
    rate_limit_requests: int = 5
    rate_limit_window_s: float = 600.0
    max_concurrent_questions: int = 2

    # Requests per second; the Etherscan free tier currently allows 3/s.
    etherscan_rps: float = 2.5
    http_timeout_s: float = 30.0
    http_max_retries: int = 4


def get_settings() -> Settings:
    return Settings()
