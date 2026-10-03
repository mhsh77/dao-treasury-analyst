"""Writes the results tables of an eval run into README.md between marker comments.

Usage: python eval/update_readme.py [run_id]   (default: eval/runs/LATEST)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dao_analyst.evaluation.report import category_table, results_table

ROOT = Path(__file__).resolve().parents[1]


def replace_block(text: str, name: str, body: str) -> str:
    start, end = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
    head, _, rest = text.partition(start)
    _, _, tail = rest.partition(end)
    if not rest:
        raise SystemExit(f"README has no {start} marker")
    return f"{head}{start}\n{body}\n{end}{tail}"


def main() -> None:
    run_id = sys.argv[1] if len(sys.argv) > 1 else (ROOT / "eval/runs/LATEST").read_text().strip()
    out = json.loads((ROOT / "eval/runs" / run_id / "metrics.json").read_text())
    run = out["run"]
    caption = (
        f"Run `{run_id}`: {out['metrics'][next(iter(out['metrics']))]['questions']} questions, "
        f"model `{run['model']}` ({run['provider']} free tier), recorded "
        f"{run.get('recorded_at', 'n/a')} (last recording session). "
        "Reproduce offline with `make eval`."
    )
    readme = ROOT / "README.md"
    text = readme.read_text()
    text = replace_block(text, "RESULTS", f"{caption}\n\n{results_table(out['metrics'])}")
    text = replace_block(text, "CATEGORIES", category_table(out["metrics"]))
    readme.write_text(text)
    print(f"README updated from run {run_id}")


if __name__ == "__main__":
    main()
