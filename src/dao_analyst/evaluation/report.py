"""Markdown report for one eval run: headline table, per-category accuracy, failures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dao_analyst.evaluation.scoring import QuestionScore

ROWS = [
    ("answer_accuracy", "Answer accuracy (answerable questions fully correct)", "pct"),
    ("numeric_value_accuracy", "Numeric accuracy (expected figures matched)", "pct"),
    ("claim_support_rate", "Claim support rate (claims traceable to tool output)", "pct"),
    ("correct_decline_rate", "Correct abstain/refuse on unanswerable questions", "pct"),
    ("wrongful_refusal_rate", "Wrongful refusals on answerable questions (lower is better)", "pct"),
    ("refusal_rate_non_allowlisted", "Refusal rate: non-allowlisted addresses", "pct"),
    ("refusal_rate_advice", "Refusal rate: advice and price predictions", "pct"),
    ("missing_price_handled", "Missing price handled (no invented USD)", "pct"),
    ("tool_selection_accuracy", "Tool selection accuracy", "pct"),
    ("mean_tool_calls", "Mean tool calls per question", "num"),
    ("model_latency_p50_s", "Model latency p50 (s)", "sec"),
    ("model_latency_p95_s", "Model latency p95 (s)", "sec"),
    ("mean_input_tokens", "Mean input tokens per question", "int"),
    ("cost_per_question_usd", "Approx. cost per question at paid-tier prices (USD)", "usd"),
    ("error_rate", "Errors (provider failures, step limit)", "pct"),
]
LABELS = {
    "naive": "Naive baseline",
    "tools_no_verifier": "Tools, no verifier",
    "full": "Full system",
}


def fmt(value: Any, kind: str) -> str:
    if value is None:
        return "n/a"
    if kind == "pct":
        return f"{value * 100:.1f}%"
    if kind == "sec":
        return f"{value:.1f}"
    if kind == "usd":
        return f"${value:.4f}"
    if kind == "int":
        return f"{int(value):,}"
    return f"{value}"


def results_table(metrics: dict[str, Any]) -> str:
    configs = [c for c in ("naive", "tools_no_verifier", "full") if c in metrics]
    head = "| Metric | " + " | ".join(LABELS[c] for c in configs) + " |"
    sep = "|---|" + "---:|" * len(configs)
    lines = [head, sep]
    for key, label, kind in ROWS:
        lines.append(
            f"| {label} | " + " | ".join(fmt(metrics[c].get(key), kind) for c in configs) + " |"
        )
    return "\n".join(lines)


def category_table(metrics: dict[str, Any]) -> str:
    configs = [c for c in ("naive", "tools_no_verifier", "full") if c in metrics]
    cats = sorted({k for c in configs for k in metrics[c]["accuracy_by_category"]})
    lines = [
        "| Category | " + " | ".join(LABELS[c] for c in configs) + " |",
        "|---|" + "---:|" * len(configs),
    ]
    for cat in cats:
        lines.append(
            f"| {cat} | "
            + " | ".join(fmt(metrics[c]["accuracy_by_category"].get(cat), "pct") for c in configs)
            + " |"
        )
    return "\n".join(lines)


def write_report(
    run_dir: Path,
    out: dict[str, Any],
    scores: dict[str, list[QuestionScore]],
    questions: list[dict[str, Any]],
) -> None:
    run = out["run"]
    by_id = {q["id"]: q for q in questions}
    parts = [
        f"# Eval run `{run.get('run_id', run_dir.name)}`",
        "",
        f"Model: `{run['model']}` via {run['provider']}. Questions: {len(questions)}. "
        f"Recorded at {run.get('recorded_at', 'n/a')} from commit "
        f"`{run.get('recorded_with_git_sha', 'n/a')}`.",
        "",
        results_table(out["metrics"]),
        "",
        "## Accuracy by category",
        "",
        "Unanswerable questions count as correct when the system declines without numbers.",
        "",
        category_table(out["metrics"]),
    ]
    for name, rows in scores.items():
        failures = [s for s in rows if not s.correct]
        parts += ["", f"## Failures: {LABELS[name]} ({len(failures)})", ""]
        for s in failures:
            notes = "; ".join(s.notes) or (s.error or "")
            parts.append(
                f"- `{s.id}` [{s.category}] outcome={s.outcome}. "
                f"{by_id[s.id]['question']} {('- ' + notes) if notes else ''}"
            )
    (run_dir / "report.md").write_text("\n".join(parts) + "\n")
