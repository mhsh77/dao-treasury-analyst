# Eval run `2026-10-03-v1-heldout`

Model: `gemini-3.5-flash-lite` via gemini. Questions: 32. Recorded at 2026-10-03T09:57:18Z from commit `35e38fa`.

| Metric | Full system |
|---|---:|
| Answer accuracy (answerable questions fully correct) | 76.0% |
| Numeric accuracy (expected figures matched) | 82.9% |
| Claim support rate (claims traceable to tool output) | 93.8% |
| Correct abstain/refuse on unanswerable questions | 83.3% |
| Wrongful refusals on answerable questions (lower is better) | 0.0% |
| Refusal rate: non-allowlisted addresses | 100.0% |
| Refusal rate: advice and price predictions | 100.0% |
| Missing price handled (no invented USD) | 100.0% |
| Tool selection accuracy | 100.0% |
| Mean tool calls per question | 3.09 |
| Model latency p50 (s) | 3.7 |
| Model latency p95 (s) | 7.4 |
| Mean input tokens per question | 21,808 |
| Approx. cost per question at paid-tier prices (USD) | $0.0080 |
| Errors (provider failures, step limit) | 0.0% |

## Accuracy by category

Unanswerable questions count as correct when the system declines without numbers.

| Category | Full system |
|---|---:|
| aggregation | 83.3% |
| comparison | 75.0% |
| lookup | 83.3% |
| multistep | 60.0% |
| ranking | 75.0% |
| unanswerable | 85.7% |

## Failures: Full system (7)

- `h005` [lookup] outcome=answer. Which counterparties received UNI in transaction 0x9188543cd776b65a5f34a6c0d10d5166dfc225b7a5c5fa44bc9b1df812947d42, and how much in total? - missing 4957002.000000000000000001 UNI
- `h012` [aggregation] outcome=answer. Leaving out the burn, how much UNI did the treasury send out over its whole history? - missing 70365150.710000000000000001 UNI
- `h014` [ranking] outcome=partial. Which counterparty sent the treasury the most UNI in 2022? - missing mention of [['UNI treasury vester 2 (year 2)', '0xe3953d9d317b834592ab58ab2c7a6ad22b54075d']]
- `h018` [comparison] outcome=answer. How many UNI transfers left the treasury in 2023 versus 2025? - missing 9 count; missing 13 count
- `h021` [multistep] outcome=answer. How much UNI did the DeFi Education Fund's addresses receive in 2024 in total? - missing 1000000 UNI
- `h023` [multistep] outcome=answer. Who received the largest UNI outflow in 2024, and how much has the treasury sent to them in total over its history? - missing 549124 UNI
- `h026` [unanswerable] outcome=answer. What is the treasury's ETH balance right now? 
