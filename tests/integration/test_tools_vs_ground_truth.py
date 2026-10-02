"""The tools and the independent SQL ground truth must agree on the real snapshot.

This is the cross-check that makes the eval meaningful: two separate implementations
(typed Python tools vs. plain SQL in eval/ground_truth.py) compute the same figures.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from dao_analyst.config import load_dao_config
from dao_analyst.data.fetch import FetchMode
from dao_analyst.data.ingest import run_ingest
from dao_analyst.settings import Settings
from dao_analyst.tools.analytics import GroupBy, Metric, TreasuryTools
from dao_analyst.tools.factory import build_tools
from dao_analyst.tools.models import DateRange, FlowDirection

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))
from ground_truth import GroundTruth  # noqa: E402


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory) -> tuple[TreasuryTools, GroundTruth]:
    db = tmp_path_factory.mktemp("db") / "t.duckdb"
    settings = Settings(
        dao_config=ROOT / "config/dao.uniswap.yaml",
        fixtures_dir=ROOT / "fixtures",
        db_path=db,
        etherscan_api_key=None,
        eth_rpc_url=None,
    )
    cfg = load_dao_config(settings.dao_config)
    cfg.labels_file = ROOT / "config/labels.uniswap.yaml"
    run_ingest(cfg, settings, FetchMode.REPLAY)
    return build_tools(cfg, settings), GroundTruth(db)


def rng(a: str, b: str) -> DateRange:
    return DateRange(start=date.fromisoformat(a), end=date.fromisoformat(b))


def questions() -> list[dict]:
    return [json.loads(line) for line in (ROOT / "eval/questions.jsonl").read_text().splitlines()]


def tool_values(tools: TreasuryTools, spec: dict) -> list[tuple[str, str]]:
    fn = spec["fn"]
    if fn == "balance":
        res = tools.get_balance_summary(date.fromisoformat(spec["as_of"]))
        h = next(m for m in res.holdings if m.token == spec["token"])
        return [(h.amount, h.token)] + ([(h.usd or "", "USD")] if spec.get("usd") else [])
    if fn == "balance_total_usd":
        return [
            (tools.get_balance_summary(date.fromisoformat(spec["as_of"])).total_usd or "", "USD")
        ]
    if fn == "flow" and not spec.get("label") and not spec.get("exclude_categories"):
        res = tools.aggregate_flows(
            GroupBy.TOKEN,
            FlowDirection(spec["direction"]),
            spec.get("token"),
            rng(spec["start"], spec["end"]),
            spec.get("category"),
        )
        out = []
        if spec.get("token") and not spec.get("usd_only"):
            amounts = [m for g in res.groups for m in g.amounts]
            out.append((amounts[0].amount if amounts else "0", spec["token"]))
        if spec.get("usd") or not spec.get("token"):
            out.append((res.groups[0].total_usd or "", "USD"))
        return out
    if fn == "compare":
        res = tools.compare_periods(
            Metric(spec["metric"]), rng(*spec["a"]), rng(*spec["b"]), spec.get("token")
        )
        unit = res.period_a.unit if res.period_a.unit != "transfers" else "count"
        a, b = (res.period_a.value or "", unit), (res.period_b.value or "", unit)
        take = spec.get("take", "both")
        return {"a": [a], "b": [b], "pct": [(res.pct_change or "", "percent")]}.get(take, [a, b])
    if fn == "top" and not spec.get("category"):
        res = tools.top_counterparties(
            FlowDirection(spec["direction"]),
            rng(spec["start"], spec["end"]),
            spec["n"],
            spec.get("token"),
        )
        if spec.get("token"):
            return [(c.amounts[0].amount, spec["token"]) for c in res.counterparties]
        return [(c.total_usd or "", "USD") for c in res.counterparties]
    raise NotImplementedError(fn)


SUPPORTED = []
for item in questions():
    for i, spec in enumerate(item["gt"] or []):
        if (
            spec["fn"] in {"balance", "balance_total_usd", "compare"}
            or (
                spec["fn"] == "flow"
                and not spec.get("label")
                and not spec.get("exclude_categories")
            )
            or (spec["fn"] == "top" and not spec.get("category"))
        ):
            SUPPORTED.append((item["id"], i, spec))


def close(a: str, b: str, unit: str) -> bool:
    if unit == "USD":  # tools round per token before summing; allow a few cents
        return abs(Decimal(a) - Decimal(b)) <= Decimal("0.05")
    return Decimal(a) == Decimal(b)


@pytest.mark.parametrize(
    ("qid", "idx", "spec"), SUPPORTED, ids=[f"{q}-{i}" for q, i, _ in SUPPORTED]
)
def test_tools_agree_with_ground_truth(
    env: tuple[TreasuryTools, GroundTruth], qid: str, idx: int, spec: dict
) -> None:
    tools, gt = env
    expected, _ = getattr(gt, f"fn_{spec['fn']}")(spec)
    got = tool_values(tools, spec)
    assert len(got) == len(expected), (got, expected)
    for (value, unit), exp in zip(got, expected, strict=True):
        assert unit == exp["unit"]
        assert close(value, exp["value"], unit), f"{qid}: tools {value} vs ground truth {exp}"
