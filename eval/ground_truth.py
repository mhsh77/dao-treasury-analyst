"""Independent ground truth for the eval question set.

Deliberately does NOT import the agent's tool code (dao_analyst.tools): it reads the
normalized DuckDB store with plain SQL and does exact arithmetic with Python Decimals.
Two separate implementations agreeing is the evidence that the tools are right; sharing
code would make the eval circular.

The store itself is shared with the tools. Its correctness is checked separately: balances
rebuilt from the stored transfers match on-chain balances at the snapshot block.

Usage: python eval/ground_truth.py [--db data/treasury.duckdb]
Writes eval/ground_truth.json: {question_id: {"values": [...], "mentions": [...]}}.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path
from typing import Any

import duckdb

HERE = Path(__file__).parent
CENT = Decimal("0.01")

FLOWS = """
SELECT t.tx_hash, t.direction, t.symbol, t.decimals, t.raw_amount, t.token_address,
       CAST(t.block_time AS DATE) AS day, strftime(t.block_time, '%Y-%m') AS month,
       CASE WHEN t.direction = 'in' THEN t.from_address ELSE t.to_address END AS cp,
       l.name AS label, COALESCE(l.category, 'unlabeled') AS category, p.usd AS price,
       t.block_number, t.transfer_id
FROM transfers t
LEFT JOIN labels l
  ON l.address = CASE WHEN t.direction = 'in' THEN t.from_address ELSE t.to_address END
LEFT JOIN tokens k ON k.token_address = t.token_address
LEFT JOIN prices p ON p.price_id = k.price_id AND p.day = CAST(t.block_time AS DATE)
WHERE t.token_verified AND t.direction <> 'self'
"""


def amount(raw: int, decimals: int) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 100
        return Decimal(raw).scaleb(-decimals)


def fmt(d: Decimal) -> str:
    text = format(d, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def usd_of(raw: int, decimals: int, price: float | None) -> Decimal | None:
    if price is None:
        return None
    return amount(raw, decimals) * Decimal(repr(price))


class GroundTruth:
    def __init__(self, db: Path) -> None:
        self.con = duckdb.connect(str(db), read_only=True)
        self.rows = [
            dict(zip([d[0] for d in self.con.description], r, strict=True))
            for r in self.con.execute(FLOWS).fetchall()
        ]
        for r in self.rows:
            r["raw"] = int(r["raw_amount"])
            r["day"] = r["day"].isoformat()

    def filtered(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        out = []
        for r in self.rows:
            if spec.get("direction") not in (None, "any") and r["direction"] != spec["direction"]:
                continue
            if spec.get("token") and r["symbol"] != spec["token"]:
                continue
            if spec.get("start") and r["day"] < spec["start"]:
                continue
            if spec.get("end") and r["day"] > spec["end"]:
                continue
            if spec.get("category") and r["category"] != spec["category"]:
                continue
            if spec.get("label") and spec["label"].lower() not in (r["label"] or "").lower():
                continue
            if r["category"] in spec.get("exclude_categories", []):
                continue
            out.append(r)
        return out

    @staticmethod
    def token_value(rows: list[dict[str, Any]], token: str) -> dict[str, Any]:
        dec = rows[0]["decimals"] if rows else 18
        total = sum(r["raw"] for r in rows)
        return {"value": fmt(amount(total, dec)), "unit": token}

    @staticmethod
    def usd_value(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        total = Decimal(0)
        for r in rows:
            v = usd_of(r["raw"], r["decimals"], r["price"])
            if v is None:
                return None
            total += v
        return {"value": str(total.quantize(CENT, ROUND_HALF_UP)), "unit": "USD"}

    def price_on(self, token: str, day: str) -> float | None:
        row = self.con.execute(
            "SELECT p.usd FROM prices p JOIN tokens k ON k.price_id = p.price_id "
            "WHERE k.symbol = ? AND p.day = CAST(? AS DATE)",
            [token, day],
        ).fetchone()
        return row[0] if row else None

    def balance_raw(self, token: str, as_of: str) -> tuple[int, int]:
        row = self.con.execute(
            "SELECT COALESCE(SUM(CASE direction WHEN 'in' THEN CAST(raw_amount AS HUGEINT) "
            "WHEN 'out' THEN -CAST(raw_amount AS HUGEINT) ELSE 0 END), 0), "
            "(SELECT decimals FROM tokens WHERE symbol = ?) "
            "FROM transfers WHERE token_verified AND symbol = ? "
            "AND CAST(block_time AS DATE) <= CAST(? AS DATE)",
            [token, token, as_of],
        ).fetchone()
        assert row is not None
        return int(row[0]), int(row[1])

    # --- spec functions -------------------------------------------------------------------

    def fn_balance(self, s: dict[str, Any]) -> tuple[list[dict[str, Any]], list[list[str]]]:
        raw, dec = self.balance_raw(s["token"], s["as_of"])
        values = [{"value": fmt(amount(raw, dec)), "unit": s["token"]}]
        if s.get("usd"):
            price = self.price_on(s["token"], s["as_of"])
            assert price is not None, f"no price for {s}"
            v = usd_of(raw, dec, price)
            assert v is not None
            values.append({"value": str(v.quantize(CENT, ROUND_HALF_UP)), "unit": "USD"})
        return values, []

    def fn_balance_total_usd(self, s: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any]]:
        total = Decimal(0)
        for (symbol,) in self.con.execute("SELECT symbol FROM tokens").fetchall():
            raw, dec = self.balance_raw(symbol, s["as_of"])
            if raw:
                v = usd_of(raw, dec, self.price_on(symbol, s["as_of"]))
                assert v is not None
                total += v
        return [{"value": str(total.quantize(CENT, ROUND_HALF_UP)), "unit": "USD"}], []

    def fn_flow(self, s: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any]]:
        rows = self.filtered(s)
        values = []
        if s.get("token"):
            values.append(self.token_value(rows, s["token"]))
        if s.get("usd") or not s.get("token"):
            usd = self.usd_value(rows)
            assert usd is not None, f"missing price in {s}"
            values.append(usd)
        return values, []

    def fn_count(self, s: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any]]:
        return [{"value": str(len(self.filtered(s))), "unit": "count"}], []

    def fn_count_label(self, s: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any]]:
        return self.fn_count(s)

    def _name(self, r: dict[str, Any]) -> list[str]:
        return [r["label"], r["cp"]] if r["label"] else [r["cp"]]

    def fn_top(self, s: dict[str, Any]) -> tuple[list[dict[str, Any]], list[list[str]]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in self.filtered(s):
            groups[r["cp"]].append(r)
        scored = []
        for cp, rows in groups.items():
            if s.get("token"):
                score = Decimal(sum(r["raw"] for r in rows))
                val = self.token_value(rows, s["token"])
            else:
                usd = self.usd_value(rows)
                assert usd is not None
                score, val = Decimal(usd["value"]), usd
            scored.append((score, cp, val, rows))
        scored.sort(key=lambda x: (-x[0], x[1]))
        top = scored[: s["n"]]
        return [v for _, _, v, _ in top], [self._name(rows[0]) for _, _, _, rows in top]

    def fn_largest(self, s: dict[str, Any]) -> tuple[list[dict[str, Any]], list[list[str]]]:
        r = max(self.filtered(s), key=lambda r: r["raw"])
        return [self.token_value([r], s["token"])], [self._name(r)]

    def fn_largest_n(self, s: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any]]:
        rows = sorted(self.filtered(s), key=lambda r: -r["raw"])[: s["n"]]
        return [self.token_value([r], s["token"]) for r in rows], []

    def _tx_rows(self, h: str) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["tx_hash"] == h.lower()]

    def fn_tx(self, s: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any]]:
        rows = [r for r in self._tx_rows(s["hash"]) if r["symbol"] == s["token"]]
        return [self.token_value(rows, s["token"])], []

    def fn_tx_count(self, s: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any]]:
        return [{"value": str(len(self._tx_rows(s["hash"]))), "unit": "count"}], []

    def fn_tx_dir(self, s: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any]]:
        rows = [r for r in self._tx_rows(s["hash"]) if r["direction"] == s["direction"]]
        return [self.token_value(rows, rows[0]["symbol"])], []

    def _metric(self, metric: str, token: str | None, start: str, end: str) -> dict[str, Any]:
        if metric == "end_balance":
            assert token
            raw, dec = self.balance_raw(token, end)
            return {"value": fmt(amount(raw, dec)), "unit": token}
        if metric == "transfer_count":
            spec = {"start": start, "end": end, "token": token}
            return {"value": str(len(self.filtered(spec))), "unit": "count"}
        ins = self.filtered({"direction": "in", "start": start, "end": end, "token": token})
        outs = self.filtered({"direction": "out", "start": start, "end": end, "token": token})
        plus, minus = {"inflow": (ins, []), "outflow": (outs, []), "net_flow": (ins, outs)}[metric]
        if token:
            dec = (plus or minus or [{"decimals": 18}])[0]["decimals"]
            total = sum(r["raw"] for r in plus) - sum(r["raw"] for r in minus)
            return {"value": fmt(amount(total, dec)), "unit": token}
        p, m = self.usd_value(plus), self.usd_value(minus)
        assert p is not None and m is not None
        return {"value": str(Decimal(p["value"]) - Decimal(m["value"])), "unit": "USD"}

    def fn_compare(self, s: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any]]:
        a = self._metric(s["metric"], s.get("token"), *s["a"])
        b = self._metric(s["metric"], s.get("token"), *s["b"])
        take = s.get("take", "both")
        if take == "a":
            return [a], []
        if take == "b":
            return [b], []
        if take == "pct":
            va, vb = Decimal(a["value"]), Decimal(b["value"])
            pct = ((vb - va) / abs(va) * 100).quantize(CENT, ROUND_HALF_UP)
            return [{"value": str(pct), "unit": "percent"}], []
        return [a, b], []

    def fn_month_max(self, s: dict[str, Any]) -> tuple[list[dict[str, Any]], list[list[str]]]:
        spec = {
            "direction": s["direction"],
            "token": s["token"],
            "start": f"{s['year']}-01-01",
            "end": f"{s['year']}-12-31",
        }
        by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in self.filtered(spec):
            by_month[r["month"]].append(r)
        month, rows = max(by_month.items(), key=lambda kv: (sum(r["raw"] for r in kv[1]), kv[0]))
        import calendar

        name = calendar.month_name[int(month[5:])]
        return [self.token_value(rows, s["token"])], [[month, name]]

    def fn_mention(self, s: dict[str, Any]) -> tuple[list[dict[str, Any]], list[list[str]]]:
        return [], [s["any"]]

    def evaluate(self, specs: list[dict[str, Any]] | None) -> dict[str, Any]:
        values: list[dict[str, Any]] = []
        mentions: list[list[str]] = []
        for spec in specs or []:
            v, m = getattr(self, f"fn_{spec['fn']}")(spec)
            values += v
            mentions += m
        return {"values": values, "mentions": mentions}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("data/treasury.duckdb"))
    parser.add_argument("--questions", type=Path, default=HERE / "questions.jsonl")
    parser.add_argument("--out", type=Path, default=HERE / "ground_truth.json")
    args = parser.parse_args()
    gt = GroundTruth(args.db)
    result = {}
    for line in args.questions.read_text().splitlines():
        item = json.loads(line)
        result[item["id"]] = gt.evaluate(item["gt"])
    args.out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(f"wrote ground truth for {len(result)} questions to {args.out}")


if __name__ == "__main__":
    main()
