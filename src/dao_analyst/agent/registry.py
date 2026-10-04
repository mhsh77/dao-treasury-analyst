"""Exposes the analytics tools to the model: JSON schemas, validated dispatch, call log.

Each executed call is stored with its full result (not the compacted version the model
sees) so the claim verifier can check numbers against exactly what the tool returned.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from dao_analyst.tools.analytics import GroupBy, Metric, SortBy, ToolInputError, TreasuryTools
from dao_analyst.tools.models import DateRange, FlowDirection, ToolResult


class NoArgs(BaseModel):
    pass


class BalanceArgs(BaseModel):
    as_of: date | None = Field(
        None, description="UTC day (YYYY-MM-DD); end of that day. Omit for the snapshot end."
    )


class ListTransfersArgs(BaseModel):
    direction: FlowDirection = FlowDirection.ANY
    token: str | None = Field(None, description="Verified token symbol, e.g. UNI, ETH, USDC")
    min_amount: str | None = Field(None, description="Minimum amount in token units; needs token")
    date_range: DateRange | None = None
    counterparty: str | None = Field(
        None, description="Labeled counterparty: address or part of its label name"
    )
    counterparty_category: str | None = Field(
        None,
        description="Label category, e.g. grant_recipient, foundation, committee, "
        "delegation, vesting, burn, governance, bridge, unlabeled",
    )
    limit: int = Field(20, ge=1, le=100)
    sort: SortBy = SortBy.TIME_ASC
    include_unverified: bool = Field(False, description="Include unverified (often spam) tokens")
    label_contains: str | None = Field(
        None,
        description="Only counterparties whose label name contains this text "
        "(e.g. all addresses of one organization)",
    )
    exclude_categories: list[str] | None = Field(
        None, description='Leave out these counterparty categories, e.g. ["burn"]'
    )


class AggregateArgs(BaseModel):
    group_by: GroupBy
    direction: FlowDirection = FlowDirection.ANY
    token: str | None = None
    date_range: DateRange | None = None
    counterparty_category: str | None = None
    label_contains: str | None = Field(
        None,
        description="Only counterparties whose label name contains this text "
        "(e.g. all addresses of one organization)",
    )
    exclude_categories: list[str] | None = Field(
        None, description='Leave out these counterparty categories, e.g. ["burn"]'
    )


class TopArgs(BaseModel):
    direction: FlowDirection = Field(description="'in' or 'out'")
    date_range: DateRange | None = None
    n: int = Field(5, ge=1, le=25)
    token: str | None = Field(None, description="Rank by this token's amount; omit to rank by USD")


class TxArgs(BaseModel):
    tx_hash: str


class CompareArgs(BaseModel):
    metric: Metric
    period_a: DateRange
    period_b: DateRange
    token: str | None = Field(None, description="Omit for USD totals across tokens")
    direction: FlowDirection = Field(
        FlowDirection.ANY, description="For transfer_count only: count in, out or any"
    )


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args: type[BaseModel]


SPECS = [
    ToolSpec(
        "describe_snapshot",
        "Scope of the data: DAO, treasury addresses, snapshot end "
        "block/date, first activity, verified tokens, price source.",
        NoArgs,
    ),
    ToolSpec(
        "get_balance_summary",
        "Treasury holdings of every verified token at the end of a "
        "UTC day, with USD values from the pinned price snapshot.",
        BalanceArgs,
    ),
    ToolSpec(
        "list_transfers",
        "List individual treasury transfers with tx hashes. Filters: "
        "direction, token, min_amount, date_range, labeled counterparty or category.",
        ListTransfersArgs,
    ),
    ToolSpec(
        "aggregate_flows",
        "Total inflows/outflows grouped by counterparty, token, month, "
        "quarter or counterparty category.",
        AggregateArgs,
    ),
    ToolSpec(
        "top_counterparties",
        "Rank counterparties by value sent (out) or received from "
        "(in), by USD or by one token's amount.",
        TopArgs,
    ),
    ToolSpec(
        "get_transaction",
        "All treasury transfers inside one transaction, decoded with labels.",
        TxArgs,
    ),
    ToolSpec(
        "compare_periods",
        "Compare a metric (inflow, outflow, net_flow, transfer_count, "
        "end_balance) between two date ranges.",
        CompareArgs,
    ),
]


def inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema with $refs inlined and titles removed (some providers reject $defs)."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            out = {k: resolve(v) for k, v in node.items() if k != "title"}
            # Collapse Optional[X] (anyOf [X, null]) into X; omission already means null.
            if "anyOf" in out:
                options = [o for o in out["anyOf"] if o.get("type") != "null"]
                if len(options) == 1:
                    merged = {**options[0], **{k: v for k, v in out.items() if k != "anyOf"}}
                    merged.pop("default", None)
                    return merged
            if out.get("default") is None:
                out.pop("default", None)
            return out
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)  # type: ignore[no-any-return]


def tool_schemas(specs: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description,
                "parameters": inline_schema(s.args),
            },
        }
        for s in specs
    ]


def result_hash(result: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]


@dataclass
class ToolCallRecord:
    call_id: str
    name: str
    arguments: dict[str, Any]
    ok: bool
    result: ToolResult | None
    error: str | None
    result_hash: str
    latency_ms: float

    def for_llm(self) -> dict[str, Any]:
        if not self.ok or self.result is None:
            return {"call_id": self.call_id, "error": self.error}
        return {"call_id": self.call_id, **self.result.for_llm()}

    def audit(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tool": self.name,
            "arguments": self.arguments,
            "ok": self.ok,
            "error": self.error,
            "result_hash": self.result_hash,
            "data_complete": self.result.data_complete if self.result else None,
            "latency_ms": round(self.latency_ms, 1),
        }


@dataclass
class ToolRegistry:
    tools: TreasuryTools
    specs: list[ToolSpec] = field(default_factory=lambda: list(SPECS))
    log: list[ToolCallRecord] = field(default_factory=list)

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return tool_schemas(self.specs)

    def reset(self) -> None:
        self.log = []

    def get(self, call_id: str) -> ToolCallRecord | None:
        return next((r for r in self.log if r.call_id == call_id), None)

    def execute(self, name: str, raw_arguments: str) -> ToolCallRecord:
        call_id = f"c{len(self.log) + 1}"
        start = time.perf_counter()
        spec = next((s for s in self.specs if s.name == name), None)
        args: dict[str, Any] = {}
        result: ToolResult | None = None
        error: str | None = None
        try:
            parsed = json.loads(raw_arguments or "{}")
            args = parsed if isinstance(parsed, dict) else {}
            if spec is None:
                raise ToolInputError(f"unknown tool {name!r}")
            validated = spec.args.model_validate(args)
            result = getattr(self.tools, name)(**dict(validated))
        except (ToolInputError, ValidationError, json.JSONDecodeError) as exc:
            error = f"invalid call: {exc}"
        record = ToolCallRecord(
            call_id=call_id,
            name=name,
            arguments=args,
            ok=error is None,
            result=result,
            error=error,
            result_hash=result_hash(result.model_dump(mode="json") if result else {"e": error}),
            latency_ms=(time.perf_counter() - start) * 1000,
        )
        self.log.append(record)
        return record
