"""Renders one recorded eval answer as a terminal-style HTML page for the README image.

The text is the agent's real output from an eval run (no editing). Screenshot with:
  chromium --headless --screenshot=docs/img/example-answer.png --window-size=1000,H file.html
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    run_id, qid, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    results = (ROOT / "eval/runs" / run_id / "results_full.jsonl").read_text().splitlines()
    result = next(json.loads(r) for r in results if json.loads(r)["id"] == qid)
    calls = " → ".join(c["tool"] for c in result["tool_calls"])
    checks = result["verification"][-1] if result["verification"] else {}
    n_ok = sum(1 for c in checks.get("claims", []) if c["verified"])
    body = html.escape(result["text"])
    page = f"""<!doctype html><meta charset="utf-8"><style>
body{{margin:0;background:#0d1117;font:15px/1.5 ui-monospace,Menlo,Consolas,monospace;color:#c9d1d9}}
.w{{padding:22px 26px}} .p{{color:#7ee787}} .q{{color:#e6edf3}} .m{{color:#8b949e}}
pre{{white-space:pre-wrap;margin:12px 0 0}} .t{{color:#d2a8ff}}</style>
<div class="w"><div><span class="p">$</span> <span class="q">dao-analyst ask
"{html.escape(result["question"])}"</span></div>
<pre>{body}</pre>
<div class="m" style="margin-top:14px">tool calls: <span class="t">{html.escape(calls)}</span>
&nbsp;·&nbsp; claims verified: {n_ok}/{len(checks.get("claims", []))}
&nbsp;·&nbsp; outcome: {result["outcome"]}</div></div>"""
    out.write_text(page)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
