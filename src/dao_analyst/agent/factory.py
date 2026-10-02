"""Wiring: settings + DAO config -> LLM client, tools, policy, agent."""

from __future__ import annotations

from pathlib import Path

from dao_analyst.agent.agent import Agent, AgentConfig, AuditLog, NaiveAgent
from dao_analyst.agent.policy import Policy
from dao_analyst.agent.registry import ToolRegistry
from dao_analyst.config import DaoConfig
from dao_analyst.llm.client import PROVIDERS, CassetteLLM, LLMClient, OpenAICompatClient
from dao_analyst.settings import Settings
from dao_analyst.tools.factory import build_tools


class ConfigError(RuntimeError):
    pass


def build_llm(
    settings: Settings,
    *,
    provider: str | None = None,
    model: str | None = None,
    cassette: Path | None = None,
    replay_only: bool = False,
) -> LLMClient:
    provider = provider or settings.llm_provider
    model = model or settings.llm_model
    if replay_only:
        if cassette is None:
            raise ConfigError("replay needs a cassette path")
        return CassetteLLM(cassette, model=model)
    if provider not in PROVIDERS:
        raise ConfigError(f"unknown LLM provider {provider!r}; choose from {sorted(PROVIDERS)}")
    base_url, key_name = PROVIDERS[provider]
    api_key = getattr(settings, key_name.lower(), None)
    if not api_key:
        raise ConfigError(f"{key_name} is not set (see .env.example)")
    inner = OpenAICompatClient(base_url=base_url, api_key=api_key, model=model)
    return CassetteLLM(cassette, model=model, inner=inner) if cassette else inner


def build_policy(cfg: DaoConfig, registry: ToolRegistry) -> Policy:
    allowed = set(cfg.treasury_set) | set(registry.tools.data.labels)
    return Policy(allowed, [t.name for t in cfg.treasury_addresses])


def build_agent(
    cfg: DaoConfig,
    settings: Settings,
    llm: LLMClient,
    config: AgentConfig | None = None,
    audit_path: Path | None = None,
) -> Agent | NaiveAgent:
    registry = ToolRegistry(build_tools(cfg, settings))
    audit = AuditLog(audit_path if audit_path is not None else settings.audit_log)
    if config is not None and config.name == "naive":
        return NaiveAgent(llm, registry, audit)
    return Agent(llm, registry, build_policy(cfg, registry), config, audit)
