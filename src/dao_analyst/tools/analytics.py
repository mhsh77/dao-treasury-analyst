"""Deterministic analytics tools. The agent can reach treasury data only through these.

Conventions shared by every tool:
- Dates are inclusive UTC calendar days. Anything after the snapshot end makes the result
  ``data_complete=false`` with a reason; the tool never extrapolates.
- Only verified tokens count, unless a tool explicitly offers ``include_unverified``.
- Transfers between two treasury addresses are internal moves, not inflows or outflows.
- Flow USD values use the pinned daily price on the day of each transfer; balance USD
  values use the price on the as-of day. Missing prices leave USD empty with a reason.
- Counterparty filters accept only labeled (hand-verified, institutional) addresses, so the
  tools cannot be used to profile arbitrary wallets.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from enum import StrEnum

from dao_analyst.tools.dataset import Dataset, Row, TokenInfo
from dao_analyst.tools.models import (
    BalanceSummary,
    Counterparty,
    CounterpartyRanking,
    DateRange,
    Evidence,
    FlowAggregate,
    FlowDirection,
    FlowGroup,
    Money,
    PeriodComparison,
    PeriodValue,
    SnapshotInfo,
    ToolResult,
    TransactionDetail,
    TransferList,
    TransferRow,
    TxTransfer,
)

CENT = Decimal("0.01")
MAX_LIST_LIMIT = 100
MAX_TOP_N = 25


class ToolInputError(ValueError):
    """Bad arguments. The message is shown to the model so it can correct the call."""


class GroupBy(StrEnum):
    COUNTERPARTY = "counterparty"
    TOKEN = "token"
    MONTH = "month"
    QUARTER = "quarter"
    CATEGORY = "category"


class SortBy(StrEnum):
    TIME_ASC = "time_asc"
    TIME_DESC = "time_desc"
    AMOUNT_DESC = "amount_desc"


class Metric(StrEnum):
    INFLOW = "inflow"
    OUTFLOW = "outflow"
    NET_FLOW = "net_flow"
    TRANSFER_COUNT = "transfer_count"
    END_BALANCE = "end_balance"


# --- formatting helpers ------------------------------------------------------------------


def format_amount(raw: int, decimals: int | None) -> str:
    """Exact decimal string, no exponent, no trailing zeros."""
    if decimals is None:
        return str(raw)
    with localcontext() as ctx:
        ctx.prec = 100
        value = Decimal(raw).scaleb(-decimals)
        text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def usd_value(raw: int, decimals: int, price: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 100
        return Decimal(raw).scaleb(-decimals) * price


def cents(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def parse_decimal(text: str, name: str) -> Decimal:
    try:
        value = Decimal(str(text))
    except InvalidOperation as exc:
        raise ToolInputError(f"{name} must be a number, got {text!r}") from exc
    if value < 0:
        raise ToolInputError(f"{name} must not be negative")
    return value


def _unique(hashes: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(hashes))


def quarter_of(d: date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


class TreasuryTools:
    def __init__(self, data: Dataset, dao_name: str) -> None:
        self.data = data
        self.dao_name = dao_name
        self._verified_rows = [r for r in data.rows if r.token_verified]

    # --- shared plumbing -----------------------------------------------------------------

    def _price_note(self) -> str:
        return (
            f"USD values use the pinned price snapshot ({self.data.price_source}); flows are "
            "valued at the daily price on the day of each transfer."
        )

    def _token(self, token: str) -> TokenInfo:
        t = token.strip().lower()
        if t in self.data.tokens:
            return self.data.tokens[t]
        info = self.data.token_by_symbol(t)
        if info is None:
            known = ", ".join(sorted(x.symbol for x in self.data.tokens.values()))
            raise ToolInputError(f"unknown or unverified token {token!r}. Verified tokens: {known}")
        return info

    def _counterparty(self, value: str) -> str:
        v = value.strip().lower()
        if v in self.data.labels:
            return v
        if v.startswith("0x"):
            raise ToolInputError(
                f"{value} is not a labeled institutional counterparty. Filtering by "
                "unlabeled addresses is not allowed (privacy policy: no profiling of "
                "arbitrary wallets)."
            )
        matches = [a for a, lb in self.data.labels.items() if v in lb.name.lower()]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ToolInputError(f"no labeled counterparty matches {value!r}")
        names = "; ".join(self.data.labels[a].name for a in matches)
        raise ToolInputError(f"{value!r} is ambiguous; matches: {names}")

    def _check_range(self, rng: DateRange | None, result: ToolResult) -> DateRange:
        """Returns the effective range and flags any part outside the snapshot."""
        end = self.data.end_date
        if rng is None:
            first = self.data.rows[0].block_time.date() if self.data.rows else end
            return DateRange(start=first, end=end)
        if rng.end > end:
            result.mark_incomplete(
                f"requested range ends {rng.end}, after the snapshot end {end} "
                f"(block {self.data.end_block}); data after the snapshot is not available"
            )
        return rng

    def _in_range(self, row: Row, rng: DateRange) -> bool:
        return rng.start <= row.block_time.date() <= rng.end

    def _money(
        self,
        token: TokenInfo | None,
        rows: Sequence[Row],
        raw_override: int | None = None,
        price_day: date | None = None,
    ) -> Money:
        """Sum rows of a single token. ``price_day`` values the total at one day's price."""
        sample = rows[0] if rows else None
        address = token.address if token else (sample.token_address if sample else "")
        symbol = token.symbol if token else (sample.symbol if sample else "")
        decimals = token.decimals if token else (sample.decimals if sample else None)
        raw = raw_override if raw_override is not None else sum(r.raw_amount for r in rows)
        money = Money(
            token=symbol,
            token_address=address,
            raw_amount=str(raw),
            amount=format_amount(raw, decimals),
            decimals=decimals,
        )
        if token is None or decimals is None:
            money.usd_missing_reason = "unverified token: not priced"
            return money
        if price_day is not None:
            price = self.data.price(token, price_day)
            if price is None:
                money.usd_missing_reason = f"no pinned {symbol} price for {price_day}"
            else:
                money.usd = cents(usd_value(raw, decimals, price))
            return money
        total = Decimal(0)
        for r in rows:
            price = self.data.price(token, r.block_time.date())
            if price is None:
                money.usd_missing_reason = f"no pinned {symbol} price for {r.block_time.date()}"
                return money
            total += usd_value(r.raw_amount, decimals, price)
        money.usd = cents(total)
        return money

    def _flow_rows(
        self, direction: FlowDirection, token: TokenInfo | None, rng: DateRange
    ) -> list[Row]:
        return [
            r
            for r in self._verified_rows
            if r.direction != "self"
            and (direction is FlowDirection.ANY or r.direction == direction.value)
            and (token is None or r.token_address == token.address)
            and self._in_range(r, rng)
        ]

    def _evidence(self, rows: Sequence[Row], rng_blocks: tuple[int, int] | None = None) -> Evidence:
        hashes = _unique(r.tx_hash for r in rows)
        if rng_blocks is None:
            rng_blocks = (
                (rows[0].block_number, rows[-1].block_number)
                if rows
                else (self.data.start_block, self.data.end_block)
            )
        return Evidence(block_range=rng_blocks, tx_hashes=hashes, tx_count=len(hashes))

    def _amounts_by_token(self, rows: Sequence[Row]) -> tuple[list[Money], str | None]:
        by_token: dict[str, list[Row]] = defaultdict(list)
        for r in rows:
            by_token[r.token_address].append(r)
        amounts = [
            self._money(self.data.tokens.get(a), rs)
            for a, rs in sorted(by_token.items(), key=lambda kv: kv[1][0].symbol)
        ]
        total = None
        if amounts and all(m.usd is not None for m in amounts):
            total = cents(sum((Decimal(m.usd) for m in amounts if m.usd), Decimal(0)))
        return amounts, total

    def _label(self, address: str) -> str | None:
        lb = self.data.labels.get(address)
        return lb.name if lb else None

    # --- tools ---------------------------------------------------------------------------

    def describe_snapshot(self) -> SnapshotInfo:
        d = self.data
        first = d.rows[0].block_time.isoformat() if d.rows else None
        return SnapshotInfo(
            tool="describe_snapshot",
            evidence=Evidence(block_range=(d.start_block, d.end_block)),
            dao=self.dao_name,
            chain=d.chain_name,
            treasury_addresses=[
                {"address": a, "label": self._label(a) or "treasury"} for a in sorted(d.treasury)
            ],
            snapshot_end_block=d.end_block,
            snapshot_end_utc=d.end_time.isoformat(),
            first_activity_utc=first,
            verified_tokens=sorted(t.symbol for t in d.tokens.values()),
            price_source=d.price_source,
        )

    def get_balance_summary(self, as_of: date | None = None) -> BalanceSummary:
        """Holdings of every verified token at the end of ``as_of`` (UTC)."""
        d = self.data
        day = as_of or d.end_date
        result = BalanceSummary(
            tool="get_balance_summary",
            evidence=Evidence(block_range=(0, 0)),
            as_of_date=day,
            holdings=[],
            price_note=self._price_note(),
        )
        if day > d.end_date:
            result.mark_incomplete(
                f"as_of {day} is after the snapshot end {d.end_date}; balances after block "
                f"{d.end_block} are not available"
            )
        rows = [r for r in self._verified_rows if r.block_time.date() <= day]
        for token in sorted(d.tokens.values(), key=lambda t: t.symbol):
            balance = 0
            for r in rows:
                if r.token_address != token.address:
                    continue
                if r.to_address in d.treasury:
                    balance += r.raw_amount
                if r.from_address in d.treasury:
                    balance -= r.raw_amount
            result.holdings.append(self._money(token, [], raw_override=balance, price_day=day))
            for check in d.balance_checks:
                if check.token_address == token.address and not check.matches:
                    result.mark_incomplete(
                        f"{token.symbol}: balance rebuilt from transfers does not match the "
                        f"on-chain balance at block {check.block_number}"
                    )
        if not d.balance_checks:
            result.notes.append("balances were not cross-checked against on-chain state")
        else:
            result.notes.append(
                f"rebuilt balances were cross-checked against on-chain balances at block "
                f"{d.end_block}"
            )
        priced = [h for h in result.holdings if h.raw_amount != "0"]
        if all(h.usd is not None for h in priced):
            result.total_usd = cents(sum((Decimal(h.usd) for h in priced if h.usd), Decimal(0)))
        last_block = rows[-1].block_number if rows else d.start_block
        result.evidence = self._evidence(rows, (d.start_block, last_block))
        return result

    def list_transfers(
        self,
        direction: FlowDirection = FlowDirection.ANY,
        token: str | None = None,
        min_amount: str | None = None,
        date_range: DateRange | None = None,
        counterparty: str | None = None,
        counterparty_category: str | None = None,
        limit: int = 20,
        sort: SortBy = SortBy.TIME_ASC,
        include_unverified: bool = False,
        label_contains: str | None = None,
        exclude_categories: list[str] | None = None,
    ) -> TransferList:
        if not 1 <= limit <= MAX_LIST_LIMIT:
            raise ToolInputError(f"limit must be between 1 and {MAX_LIST_LIMIT}")
        tok = self._token(token) if token else None
        min_raw: int | None = None
        if min_amount is not None:
            if tok is None:
                raise ToolInputError("min_amount needs a token (amounts are per token)")
            min_raw = int(parse_decimal(min_amount, "min_amount").scaleb(tok.decimals))
        cp = self._counterparty(counterparty) if counterparty else None
        cp_ok = self._counterparty_filter(counterparty_category, label_contains, exclude_categories)
        result = TransferList(
            tool="list_transfers",
            evidence=Evidence(block_range=(0, 0)),
            total_matching=0,
            returned=0,
            transfers=[],
            price_note=self._price_note(),
        )
        rng = self._check_range(date_range, result)
        source = self.data.rows if include_unverified else self._verified_rows
        rows = [
            r
            for r in source
            if r.direction != "self"
            and (direction is FlowDirection.ANY or r.direction == direction.value)
            and (tok is None or r.token_address == tok.address)
            and (min_raw is None or r.raw_amount >= min_raw)
            and (cp is None or r.counterparty == cp)
            and cp_ok(r.counterparty)
            and self._in_range(r, rng)
        ]
        if sort is SortBy.TIME_DESC:
            rows = rows[::-1]
        elif sort is SortBy.AMOUNT_DESC:
            if tok is not None:
                rows = sorted(rows, key=lambda r: -r.raw_amount)
            else:
                rows = sorted(rows, key=self._usd_sort_key)
        result.total_matching = len(rows)
        shown = rows[:limit]
        result.returned = len(shown)
        if len(rows) > limit:
            result.notes.append(f"showing {limit} of {len(rows)} matching transfers")
        if include_unverified:
            result.notes.append("includes unverified tokens; their symbols may be spoofed")
        for r in shown:
            result.transfers.append(
                TransferRow(
                    tx_hash=r.tx_hash,
                    tx_url=self.data.tx_url(r.tx_hash),
                    block_number=r.block_number,
                    timestamp=r.block_time.isoformat(),
                    direction=r.direction,
                    kind=r.kind,
                    counterparty=r.counterparty,
                    counterparty_label=self._label(r.counterparty),
                    value=self._money(
                        self.data.tokens.get(r.token_address) if r.token_verified else None, [r]
                    ),
                    token_verified=r.token_verified,
                )
            )
        result.evidence = self._evidence(shown, self._blocks(rng))
        return result

    def aggregate_flows(
        self,
        group_by: GroupBy,
        direction: FlowDirection = FlowDirection.ANY,
        token: str | None = None,
        date_range: DateRange | None = None,
        counterparty_category: str | None = None,
        label_contains: str | None = None,
        exclude_categories: list[str] | None = None,
    ) -> FlowAggregate:
        tok = self._token(token) if token else None
        cp_ok = self._counterparty_filter(counterparty_category, label_contains, exclude_categories)
        result = FlowAggregate(
            tool="aggregate_flows",
            evidence=Evidence(block_range=(0, 0)),
            group_by=group_by.value,
            groups=[],
            price_note=self._price_note(),
        )
        rng = self._check_range(date_range, result)
        rows = [r for r in self._flow_rows(direction, tok, rng) if cp_ok(r.counterparty)]
        key_fn: Callable[[Row], str] = {
            GroupBy.COUNTERPARTY: lambda r: r.counterparty,
            GroupBy.TOKEN: lambda r: r.symbol,
            GroupBy.MONTH: lambda r: r.block_time.strftime("%Y-%m"),
            GroupBy.QUARTER: lambda r: quarter_of(r.block_time.date()),
            GroupBy.CATEGORY: lambda r: self._category(r.counterparty),
        }[group_by]
        buckets: dict[tuple[str, str], list[Row]] = defaultdict(list)
        for r in rows:
            buckets[(key_fn(r), r.direction)].append(r)
        for (key, flow_dir), group_rows in sorted(buckets.items()):
            amounts, total = self._amounts_by_token(group_rows)
            hashes = _unique(r.tx_hash for r in group_rows)
            result.groups.append(
                FlowGroup(
                    key=key,
                    label=self._label(key) if group_by is GroupBy.COUNTERPARTY else None,
                    direction=flow_dir,
                    amounts=amounts,
                    total_usd=total,
                    tx_count=len(hashes),
                    tx_hashes=hashes,
                )
            )
        result.evidence = self._evidence(rows, self._blocks(rng))
        return result

    def top_counterparties(
        self,
        direction: FlowDirection,
        date_range: DateRange | None = None,
        n: int = 5,
        token: str | None = None,
    ) -> CounterpartyRanking:
        if direction is FlowDirection.ANY:
            raise ToolInputError("direction must be 'in' or 'out' for a ranking")
        if not 1 <= n <= MAX_TOP_N:
            raise ToolInputError(f"n must be between 1 and {MAX_TOP_N}")
        tok = self._token(token) if token else None
        result = CounterpartyRanking(
            tool="top_counterparties",
            evidence=Evidence(block_range=(0, 0)),
            ranked_by=f"{tok.symbol} amount" if tok else "USD value at transfer time",
            direction=direction.value,
            counterparties=[],
            price_note=self._price_note(),
        )
        rng = self._check_range(date_range, result)
        rows = self._flow_rows(direction, tok, rng)
        by_cp: dict[str, list[Row]] = defaultdict(list)
        for r in rows:
            by_cp[r.counterparty].append(r)
        scored = []
        for address, cp_rows in by_cp.items():
            amounts, total = self._amounts_by_token(cp_rows)
            if tok is not None:
                score = Decimal(sum(r.raw_amount for r in cp_rows))
            elif total is not None:
                score = Decimal(total)
            else:
                result.mark_incomplete(
                    f"cannot rank {address} by USD: some transfers have no pinned price"
                )
                score = Decimal(-1)
            scored.append((score, address, amounts, total, cp_rows))
        scored.sort(key=lambda s: (-s[0], s[1]))
        for rank, (_, address, amounts, total, cp_rows) in enumerate(scored[:n], start=1):
            lb = self.data.labels.get(address)
            hashes = _unique(r.tx_hash for r in cp_rows)
            result.counterparties.append(
                Counterparty(
                    rank=rank,
                    address=address,
                    label=lb.name if lb else None,
                    category=lb.category if lb else None,
                    amounts=amounts,
                    total_usd=total,
                    tx_count=len(hashes),
                    tx_hashes=hashes,
                )
            )
        if len(scored) > n:
            result.notes.append(f"{len(scored)} counterparties in total; showing top {n}")
        result.evidence = self._evidence(rows, self._blocks(rng))
        return result

    def get_transaction(self, tx_hash: str) -> TransactionDetail:
        h = tx_hash.strip().lower()
        if not (h.startswith("0x") and len(h) == 66):
            raise ToolInputError("tx_hash must be a 0x-prefixed 32-byte hex string")
        rows = [r for r in self.data.rows if r.tx_hash == h]
        result = TransactionDetail(
            tool="get_transaction",
            tx_hash=h,
            found=bool(rows),
            evidence=Evidence(block_range=(0, 0)),
            price_note=self._price_note(),
        )
        if not rows:
            result.mark_incomplete(
                "no treasury transfer with this hash in the snapshot (it may not involve the "
                f"treasury, or may be after block {self.data.end_block})"
            )
            result.evidence = Evidence(block_range=(self.data.start_block, self.data.end_block))
            return result
        first = rows[0]
        result.tx_url = self.data.tx_url(h)
        result.block_number = first.block_number
        result.timestamp = first.block_time.isoformat()
        for r in rows:
            token = self.data.tokens.get(r.token_address) if r.token_verified else None
            result.transfers.append(
                TxTransfer(
                    kind=r.kind,
                    direction=r.direction,
                    from_address=r.from_address,
                    from_label=self._label(r.from_address),
                    to_address=r.to_address,
                    to_label=self._label(r.to_address),
                    value=self._money(token, [r]),
                    token_verified=r.token_verified,
                )
            )
        result.evidence = self._evidence(rows)
        return result

    def compare_periods(
        self,
        metric: Metric,
        period_a: DateRange,
        period_b: DateRange,
        token: str | None = None,
        direction: FlowDirection = FlowDirection.ANY,
    ) -> PeriodComparison:
        tok = self._token(token) if token else None
        if direction is not FlowDirection.ANY and metric is not Metric.TRANSFER_COUNT:
            raise ToolInputError(
                "direction only applies to transfer_count; use inflow or outflow instead"
            )
        if metric is Metric.END_BALANCE and tok is None:
            raise ToolInputError("end_balance needs a token")
        result = PeriodComparison(
            tool="compare_periods",
            metric=metric.value,
            token=tok.symbol if tok else None,
            evidence=Evidence(block_range=(0, 0)),
            difference=None,
            pct_change=None,
            period_a=PeriodValue(period=period_a, value=None, unit="", tx_count=0),
            period_b=PeriodValue(period=period_b, value=None, unit="", tx_count=0),
            price_note=self._price_note(),
        )
        all_rows: list[Row] = []
        values: list[Decimal | None] = []
        for slot, period in (("period_a", period_a), ("period_b", period_b)):
            rng = self._check_range(period, result)
            value, unit, rows = self._metric_value(metric, tok, rng, result, direction)
            all_rows.extend(rows)
            pv = PeriodValue(
                period=period,
                value=None if value is None else self._fmt(value, unit),
                unit=unit,
                tx_count=len(_unique(r.tx_hash for r in rows)),
            )
            setattr(result, slot, pv)
            values.append(value)
        a, b = values
        if a is not None and b is not None:
            result.difference = self._fmt(b - a, result.period_a.unit)
            if a != 0:
                result.pct_change = str(((b - a) / abs(a) * 100).quantize(CENT, ROUND_HALF_UP))
            else:
                result.notes.append("percent change undefined: period A value is zero")
        all_rows.sort(key=lambda r: r.block_number)
        result.evidence = self._evidence(all_rows, (self.data.start_block, self.data.end_block))
        return result

    # --- internals for the tools above -----------------------------------------------------

    def _counterparty_filter(
        self,
        category: str | None,
        label_contains: str | None,
        exclude_categories: list[str] | None,
    ) -> Callable[[str], bool]:
        """Predicate over counterparty addresses for the category/label filters."""
        matching: set[str] | None = None
        if label_contains:
            needle = label_contains.strip().lower()
            matching = {a for a, lb in self.data.labels.items() if needle in lb.name.lower()}
            if not matching:
                raise ToolInputError(f"no labeled counterparty name contains {label_contains!r}")
        excluded = set(exclude_categories or [])

        def ok(address: str) -> bool:
            cat = self._category(address)
            return (
                (category is None or cat == category)
                and (matching is None or address in matching)
                and cat not in excluded
            )

        return ok

    def _category(self, address: str) -> str:
        lb = self.data.labels.get(address)
        return lb.category if lb else "unlabeled"

    def _blocks(self, rng: DateRange) -> tuple[int, int]:
        inside = [r.block_number for r in self.data.rows if self._in_range(r, rng)]
        return (min(inside), max(inside)) if inside else (0, 0)

    def _usd_sort_key(self, r: Row) -> tuple[int, Decimal, str]:
        token = self.data.tokens.get(r.token_address)
        price = self.data.price(token, r.block_time.date()) if token else None
        if token is None or price is None:
            return (1, Decimal(0), r.transfer_id)
        return (0, -usd_value(r.raw_amount, token.decimals, price), r.transfer_id)

    @staticmethod
    def _fmt(value: Decimal, unit: str) -> str:
        if unit == "USD":
            return cents(value)
        if unit == "transfers":
            return str(int(value))
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text

    def _metric_value(
        self,
        metric: Metric,
        tok: TokenInfo | None,
        rng: DateRange,
        result: ToolResult,
        direction: FlowDirection = FlowDirection.ANY,
    ) -> tuple[Decimal | None, str, list[Row]]:
        if metric is Metric.END_BALANCE:
            assert tok is not None
            summary = self.get_balance_summary(min(rng.end, self.data.end_date))
            holding = next(h for h in summary.holdings if h.token_address == tok.address)
            rows = [
                r
                for r in self._verified_rows
                if r.token_address == tok.address and r.block_time.date() <= rng.end
            ]
            return Decimal(holding.amount), tok.symbol, rows
        if metric is Metric.TRANSFER_COUNT:
            rows = self._flow_rows(direction, tok, rng)
            return Decimal(len(rows)), "transfers", rows
        ins = self._flow_rows(FlowDirection.IN, tok, rng)
        outs = self._flow_rows(FlowDirection.OUT, tok, rng)
        chosen = {
            Metric.INFLOW: (ins, []),
            Metric.OUTFLOW: (outs, []),
            Metric.NET_FLOW: (ins, outs),
        }[metric]
        plus, minus = chosen
        if tok is not None:
            total = sum(r.raw_amount for r in plus) - sum(r.raw_amount for r in minus)
            return Decimal(total).scaleb(-tok.decimals), tok.symbol, [*plus, *minus]
        usd_plus = self._amounts_by_token(plus)[1] if plus else "0.00"
        usd_minus = self._amounts_by_token(minus)[1] if minus else "0.00"
        if usd_plus is None or usd_minus is None:
            result.notes.append("USD total unavailable: some transfers have no pinned price")
            return None, "USD", [*plus, *minus]
        return Decimal(usd_plus) - Decimal(usd_minus), "USD", [*plus, *minus]
