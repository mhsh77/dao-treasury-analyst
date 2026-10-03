"""Writes the results tables of an eval run into README.md between marker comments.

Usage: python eval/update_readme.py [run_id]   (default: the v1 headline run)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dao_analyst.evaluation.report import category_table, fmt, results_table

ROOT = Path(__file__).resolve().parents[1]


def replace_block(text: str, name: str, body: str) -> str:
    start, end = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
    head, _, rest = text.partition(start)
    _, _, tail = rest.partition(end)
    if not rest:
        raise SystemExit(f"README has no {start} marker")
    return f"{head}{start}\n{body}\n{end}{tail}"


HELDOUT_ROWS = [
    ("answer_accuracy", "Answer accuracy (answerable questions fully correct)"),
    ("numeric_value_accuracy", "Numeric accuracy (expected figures matched)"),
    ("claim_support_rate", "Claim support rate"),
    ("correct_decline_rate", "Correct abstain/refuse on unanswerable questions"),
    ("wrongful_refusal_rate", "Wrongful refusals on answerable questions"),
    ("refusal_rate_advice", "Refusal rate: advice and price predictions"),
    ("refusal_rate_non_allowlisted", "Refusal rate: non-allowlisted addresses"),
    ("mean_tool_calls", "Mean tool calls per question"),
    ("error_rate", "Errors"),
]


def heldout_table() -> str | None:
    """Held-out comparison: v1 code vs v2 code (plus v2's baseline and ablation)."""
    runs = ROOT / "eval/runs"
    v1, v2 = (
        runs / "2026-10-03-v1-heldout/metrics.json",
        runs / "2026-10-03-v2-heldout/metrics.json",
    )
    if not (v1.exists() and v2.exists()):
        return None
    m1 = json.loads(v1.read_text())["metrics"]
    m2 = json.loads(v2.read_text())["metrics"]
    cols = [
        ("Naive baseline", m2.get("naive")),
        ("v1 full system", m1.get("full")),
        ("v2 tools, no verifier", m2.get("tools_no_verifier")),
        ("v2 full system", m2.get("full")),
    ]
    cols = [(name, m) for name, m in cols if m]
    lines = ["| Metric | " + " | ".join(n for n, _ in cols) + " |", "|---|" + "---:|" * len(cols)]
    for key, label in HELDOUT_ROWS:
        kind = "num" if key == "mean_tool_calls" else "pct"
        lines.append(f"| {label} | " + " | ".join(fmt(m.get(key), kind) for _, m in cols) + " |")
    n = next(iter(m2.values()))["questions"]
    return (
        f"{n} held-out questions, same model (`gemini-3.5-flash-lite`). "
        "Reproduce v2 offline with `make eval RUN=2026-10-03-v2-heldout`.\n\n" + "\n".join(lines)
    )


def main() -> None:
    # The headline table is the original blind run (v1); see the README for why.
    run_id = sys.argv[1] if len(sys.argv) > 1 else "2026-10-02-flash-lite"
    out = json.loads((ROOT / "eval/runs" / run_id / "metrics.json").read_text())
    run = out["run"]
    caption = (
        f"Run `{run_id}`: {out['metrics'][next(iter(out['metrics']))]['questions']} questions, "
        f"model `{run['model']}` ({run['provider']} free tier), recorded "
        f"{run.get('recorded_at', 'n/a')} (last recording session). "
        "Reproduce offline at commit `35e38fa` with `make eval` (later commits changed the "
        "prompts and tool schemas, so the v1 cassettes only replay there)."
    )
    readme = ROOT / "README.md"
    text = readme.read_text()
    text = replace_block(text, "RESULTS", f"{caption}\n\n{results_table(out['metrics'])}")
    text = replace_block(text, "CATEGORIES", category_table(out["metrics"]))
    heldout = heldout_table()
    if heldout:
        text = replace_block(text, "HELDOUT", heldout)
    readme.write_text(text)
    print(f"README updated from run {run_id}")


if __name__ == "__main__":
    main()
