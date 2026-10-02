"""Eval runner: questions -> agent (per config) -> scores -> metrics + report.

Each run lives in ``eval/runs/<run_id>/``:
- ``run.json``                 model, provider, configs, input hashes
- ``cassette_<config>.jsonl.gz`` every model request/response (replayable offline)
- ``results_<config>.jsonl``   raw agent outputs
- ``scores_<config>.jsonl``    per-question scores
- ``metrics.json``, ``report.md``

``record`` mode calls the live model and appends to the cassettes; re-running it resumes
(already recorded calls are replayed, failed ones are retried). ``replay`` mode needs no
network and no API key, and recomputes everything from the cassettes.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import structlog

from dao_analyst.agent.agent import AgentConfig, AgentResult, Outcome
from dao_analyst.agent.answer import Claim
from dao_analyst.agent.factory import build_agent, build_llm
from dao_analyst.agent.registry import ToolRegistry
from dao_analyst.agent.verifier import verify_claim
from dao_analyst.config import DaoConfig
from dao_analyst.evaluation.report import write_report
from dao_analyst.evaluation.scoring import QuestionScore, score_question, summarize
from dao_analyst.llm.client import CassetteMissingError
from dao_analyst.settings import Settings
from dao_analyst.tools.factory import build_tools

log = structlog.get_logger(__name__)

CONFIGS: dict[str, AgentConfig] = {
    "naive": AgentConfig(name="naive"),
    "tools_no_verifier": AgentConfig(
        name="tools_no_verifier", use_verifier=False, enforce_abstention=False
    ),
    "full": AgentConfig(name="full"),
}
# Paid-tier list prices (USD per 1M tokens) used for the cost estimate. Source:
# https://ai.google.dev/gemini-api/docs/pricing (read 2026-10-02). The runs used the free tier.
PRICES = {"gemini-3.5-flash-lite": (0.30, 2.50)}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def claim_support(result: dict[str, Any], registry: ToolRegistry) -> tuple[int, int]:
    """Re-executes the logged tool calls (tools are deterministic) and verifies every claim
    the model submitted. Works for configs that ran without the verifier too."""
    claims = [
        Claim.model_validate(c)
        for c in (result.get("claims") or []) + (result.get("unverified_claims") or [])
    ]
    if not claims:
        return 0, 0
    registry.reset()
    for call in result.get("tool_calls") or []:
        registry.execute(call["tool"], json.dumps(call["arguments"]))
    by_id = {r.call_id: r for r in registry.log}
    supported = sum(1 for c in claims if verify_claim(c, by_id).verified)
    return len(claims), supported


def run_config(
    name: str,
    questions: list[dict[str, Any]],
    run_dir: Path,
    cfg: DaoConfig,
    settings: Settings,
    *,
    replay: bool,
    model: str,
    provider: str,
    min_interval_s: float,
) -> list[dict[str, Any]]:
    cassette = run_dir / f"cassette_{name}.jsonl.gz"
    llm = build_llm(
        settings,
        provider=provider,
        model=model,
        cassette=cassette,
        replay_only=replay,
        min_interval_s=min_interval_s,
    )
    agent = build_agent(cfg, settings, llm, CONFIGS[name], audit_path=Path("/dev/null"))
    results = []
    for i, q in enumerate(questions, start=1):
        try:
            result = agent.answer(q["question"])
        except CassetteMissingError as exc:
            result = AgentResult(
                question=q["question"],
                config=name,
                outcome=Outcome.ERROR,
                text="",
                error=f"not recorded: {exc}",
            )
        record = {"id": q["id"], **result.to_dict()}
        results.append(record)
        log.info(
            "eval.question",
            config=name,
            n=f"{i}/{len(questions)}",
            id=q["id"],
            outcome=record["outcome"],
        )
    with (run_dir / f"results_{name}.jsonl").open("w") as f:
        for r in results:
            f.write(json.dumps(r, default=str) + "\n")
    return results


def run_eval(
    cfg: DaoConfig,
    settings: Settings,
    *,
    run_id: str,
    configs: list[str],
    replay: bool,
    eval_dir: Path = Path("eval"),
    only: list[str] | None = None,
    model: str | None = None,
    provider: str | None = None,
    min_interval_s: float = 4.0,
) -> dict[str, Any]:
    run_dir = eval_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    questions_path = eval_dir / "questions.jsonl"
    gt_path = eval_dir / "ground_truth.json"
    questions = load_jsonl(questions_path)
    if only:
        questions = [q for q in questions if q["id"] in set(only)]
    ground_truth = json.loads(gt_path.read_text())

    meta_path = run_dir / "run.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    model = model or meta.get("model") or settings.llm_model
    provider = provider or meta.get("provider") or settings.llm_provider
    if not replay:
        meta.update(
            {
                "run_id": run_id,
                "model": model,
                "provider": provider,
                "recorded_with_git_sha": git_sha(),
                "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "questions_sha256": sha256(questions_path),
                "ground_truth_sha256": sha256(gt_path),
            }
        )
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    elif meta.get("questions_sha256") not in (None, sha256(questions_path)):
        log.warning("eval.questions_changed_since_recording", run=run_id)

    registry = ToolRegistry(build_tools(cfg, settings))
    price_in, price_out = PRICES.get(model, (None, None))
    metrics: dict[str, Any] = {}
    all_scores: dict[str, list[QuestionScore]] = {}
    for name in configs:
        results = run_config(
            name,
            questions,
            run_dir,
            cfg,
            settings,
            replay=replay,
            model=model,
            provider=provider,
            min_interval_s=min_interval_s,
        )
        scores = [
            score_question(q, ground_truth[q["id"]], r, claim_support(r, registry))
            for q, r in zip(questions, results, strict=True)
        ]
        all_scores[name] = scores
        with (run_dir / f"scores_{name}.jsonl").open("w") as f:
            for s in scores:
                f.write(json.dumps(asdict(s)) + "\n")
        metrics[name] = summarize(scores, price_in, price_out)
    out = {"run": meta | {"model": model, "provider": provider}, "metrics": metrics}
    (run_dir / "metrics.json").write_text(json.dumps(out, indent=2) + "\n")
    write_report(run_dir, out, all_scores, questions)
    return out
