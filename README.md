# DAO Treasury Analyst

**Ask questions about a DAO treasury in plain English. Every number in the answer is computed
by tested code, checked against the tool output before you see it, and linked to the
transactions behind it.**

Default target: the [Uniswap DAO treasury](https://docs.uniswap.org/concepts/governance/overview)
(Governance Timelock `0x1a9C…35BC`) on Ethereum mainnet, full history up to block 25,433,938
(2026-06-30 23:59:59 UTC). Pointing it at another DAO is a config change.

![Example answer from the CLI](docs/img/example-answer.png)

## Results

The full system against a naive baseline that gets all raw transactions in its prompt, and an
ablation without the claim verifier. Same model and the same questions for every column.
Ground truth comes from an independent SQL script, not from the agent's tools.

<!-- RESULTS:START -->
<!-- RESULTS:END -->

Accuracy by question category:

<!-- CATEGORIES:START -->
<!-- CATEGORIES:END -->

The [error analysis](#error-analysis) below explains the remaining failures. Raw outputs, per-question
scores and the full report are in [`eval/runs/`](eval/runs/).

## What it does

- Answers questions about balances, inflows and outflows, counterparties, rankings, period
  comparisons and individual transactions.
- Shows every figure with explorer links to the supporting transactions, plus caveats (for
  example, that USD values use a pinned price snapshot).
- Abstains when the data can't answer: dates after the snapshot, missing prices, unverified
  tokens, other chains.
- Refuses investment advice, price predictions, and questions about addresses that are not the
  treasury or a hand-verified institutional counterparty. It never profiles private wallets.
- Runs as a CLI and a Telegram bot, with the same core behind both.

## Architecture

```mermaid
flowchart LR
    subgraph Data["Data layer (pluggable, cached)"]
        ES[Etherscan V2<br/>transfers] --> REC
        RPC[Archive RPC<br/>balances] --> REC
        DL[DefiLlama<br/>daily prices] --> REC
        REC[Record / replay<br/>fixtures] --> NORM[Normalizer]
    end
    NORM --> DB[(DuckDB<br/>local store)]
    DB --> TOOLS[Typed tools<br/>balances, flows, rankings,<br/>tx details, comparisons]
    Q([Question]) --> GUARD[Guardrails<br/>allowlist, advice]
    GUARD --> AGENT[LLM agent<br/>tool calls]
    AGENT <--> TOOLS
    AGENT --> ANS[Structured answer<br/>claims + citations]
    ANS --> VER{Claim verifier}
    VER -- mismatch: one retry --> AGENT
    VER -- verified --> OUT([Answer + tx links + caveats])
    VER -- still failing --> PART([Verified parts only])
    TOOLS -. data_complete=false .-> ABS([Abstain: what is missing])
```

| Layer | Code | Notes |
|---|---|---|
| Providers | `src/dao_analyst/data/providers/` | `ChainDataProvider`, `BalanceProvider`, `PriceProvider` interfaces. Etherscan V2 takes a `chainid`, so adding an EVM chain is configuration. |
| Record/replay | `src/dao_analyst/data/fetch.py` | Every API response is stored gzipped under `fixtures/` (no secrets). Replay runs the same parsing code as live runs. |
| Store | `src/dao_analyst/store/db.py` | DuckDB. Amounts are exact integers stored as strings; nothing goes through a float. |
| Tools | `src/dao_analyst/tools/analytics.py` | 6 typed tools plus `describe_snapshot`. Each result carries tx hashes, a block range and `data_complete`. |
| Agent | `src/dao_analyst/agent/` | Provider-agnostic `LLMClient` (OpenAI-compatible: Gemini, Groq, OpenRouter). Guardrails, verifier and renderer. |
| Eval | `eval/`, `src/dao_analyst/evaluation/` | Question set, independent ground truth, runner, scoring, report. |
| Interfaces | `src/dao_analyst/interfaces/`, `cli.py` | Telegram bot and CLI over one `QuestionService` (rate limits, concurrency cap). |

## Run it

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
make install
make ingest        # build data/treasury.duckdb from committed fixtures (offline, no keys)
make eval          # replay the recorded eval run offline and recompute every metric (no keys)
make check         # lint, types, 130+ tests
```

Ask a question (needs a free `GEMINI_API_KEY` or `GROQ_API_KEY` in `.env`, see
[`.env.example`](.env.example)):

```bash
uv run dao-analyst ask "Who were the top 5 recipients of UNI from the treasury?" --show-trace
```

Start the Telegram bot (`TELEGRAM_BOT_TOKEN` from @BotFather):

```bash
uv run dao-analyst bot                 # or: docker compose up -d --build
```

Deployment notes for a small VPS: [docs/deploy.md](docs/deploy.md).

Other commands:

| Command | What it does |
|---|---|
| `make fetch` | Re-record fixtures from the live APIs (`ETHERSCAN_API_KEY`; `ETH_RPC_URL` optional for the balance cross-check) |
| `make questions` | Regenerate `eval/questions.jsonl` and the ground truth |
| `make eval-live RUN=<id>` | Run the eval against the live model and record a new cassette (resumable) |

### Using another DAO

Copy `config/dao.uniswap.yaml` and `config/labels.uniswap.yaml`, set the treasury addresses,
verified tokens and labels (each with a source URL), point `DAO_CONFIG` at the new file and run
`make fetch`. Nothing in the agent or tools is Uniswap-specific.

## How correctness is enforced

1. **The model never does arithmetic.** It can only reach data through typed tools, which
   compute totals, rankings and differences with exact integer math.
2. **Answers are structured.** The final answer is a list of claims (value, unit, the tool
   call ids it came from, supporting tx hashes) plus text that may only refer to numbers
   through placeholders like `{c1}`.
3. **A verifier checks every claim in code.** Each value must appear in a cited tool result
   with a compatible unit, either exactly or rounded to the claim's own precision. Tx hashes
   must come from those results, and any digit in the prose that isn't a date or from the
   question is rejected. On failure the model gets one retry with the specific problems. If
   it fails again, only the verified claims are shown, together with what could not be verified.
4. **Abstention is enforced, not requested.** If a cited result says `data_complete: false`
   (for example, a date after the snapshot), the answer becomes an abstention that states
   what is missing.
5. **Guardrails run before the model.** Addresses outside the allowlist and requests for advice
   or predictions are refused in code.
6. **Everything is logged.** The audit log records every question, tool call (arguments and
   result hash), verification outcome and latency (`logs/audit.jsonl`).

## Data provenance

- **Treasury address**: verified against Uniswap's
  [governance technical reference](https://github.com/Uniswap/docs/blob/main/content/ecosystem/governance/technical-reference.mdx).
- **Snapshot**: pinned in [`fixtures/snapshot.json`](fixtures/snapshot.json). Balances rebuilt
  from the stored transfers **match on-chain `eth_getBalance`/`balanceOf` exactly** at the
  snapshot block for ETH, UNI, USDC and USDT.
- **Tokens**: only tokens listed in the config, matched by contract address, count toward
  totals. The treasury also received 342 transfers of unverified tokens (spam airdrops,
  including one token that calls itself "UNI"); these are stored but flagged.
- **Labels**: 25 counterparties in [`config/labels.uniswap.yaml`](config/labels.uniswap.yaml),
  each with a source: Uniswap docs, governance forum posts, on-chain proposal descriptions,
  Arbitrum docs, or Etherscan-verified contract names. Unlabeled addresses stay unlabeled.
- **Prices**: DefiLlama, the price nearest 00:00 UTC (±6h) for each day, pinned in the fixtures.
  Two days have no DefiLlama price (UNI 2022-10-12, USDT 2022-08-13); questions that need
  them get token amounts only.

## Evaluation method

- **Questions**: 85 in [`eval/questions.jsonl`](eval/questions.jsonl), generated from
  [`eval/make_questions.py`](eval/make_questions.py): 16 lookups, 16 aggregations, 10 rankings,
  10 period comparisons, 10 multi-step, and 23 unanswerable or out-of-scope (after the snapshot,
  non-allowlisted addresses, advice and predictions, missing prices, unverified tokens, other
  chains or DAOs).
- **Ground truth**: [`eval/ground_truth.py`](eval/ground_truth.py) uses plain SQL over the store
  and Python `Decimal`s, and imports none of the tool code. A test checks that the tools and
  the ground truth agree on all 45 figures where both can be compared.
- **Scoring**: token amounts and counts must match exactly (rounding to two or more decimals is
  accepted). USD values within 0.5%, percentages within 0.01 points. Rankings must also name the
  right counterparty. Unanswerable questions count as correct only when the system declines
  without stating numbers.
- **Configs**: `naive` (raw transfers, labels and prices in the prompt; no tools, no verifier),
  `tools_no_verifier` (tools and guardrails; the final answer is accepted as is), and `full`.
- **Claim support** is measured for every config by re-executing the logged tool calls (the
  tools are deterministic) and verifying each submitted claim against them. The naive baseline
  has no tool output, so its claims are untraceable by construction.
- **Reproducibility**: every model request and response is stored in a cassette per config.
  `make eval` replays them with no network or key and recomputes all metrics.

<!-- ANALYSIS:START -->
<!-- ANALYSIS:END -->

## Design decisions

<!-- DECISIONS:START -->
**Typed tools instead of free-form SQL.** A model writing SQL can get joins, units and
decimals subtly wrong, and every query is a new, untested program. Six typed tools cover the
question types, use exact integer arithmetic, and are unit-tested against a hand-computed
dataset and cross-checked against an independent SQL ground truth on the real data. Typed
arguments also let policy live in code: counterparty filters accept only labeled institutional
addresses, so the tools cannot be used to profile a wallet. The cost is coverage. When a
question needs a combination no tool computes (a total across three labels, "excluding the
burn"), the agent has to say it can't, or it fails. Those failures show up in the error analysis.

**A claim verifier instead of trusting the prompt.** Telling a model "only use tool numbers"
is a request, not a guarantee. The verifier makes it a property of the system: every number
the user sees was matched to a tool result it cites, with a compatible unit. Numbers the model
derived itself are rejected by design, even when they happen to be right. That is deliberate:
"correct but unverifiable" is not good enough for treasury reporting.

**A pinned, recorded snapshot.** The data, the prices and the model's responses are all
recorded. The end block is pinned in `fixtures/snapshot.json`. API responses (about 400 KB
gzipped) are committed and replayed through the same parsing code. Model calls are stored in
per-config cassettes. Anyone can clone the repo and recompute every number in this README
offline, with no API keys, and get identical results.

**An independent ground truth.** Expected answers come from plain SQL in `eval/ground_truth.py`,
which imports none of the tool code. If the tools and the ground truth shared code, a bug in
it would make both agree and the eval would be circular. A test checks that they agree on every
figure both can compute.

**Provider-agnostic LLM client.** The agent talks to one small `LLMClient` interface. A single
OpenAI-compatible adapter covers Gemini, Groq and OpenRouter, so changing models is a config
change. The eval uses one model for every config so the comparison is fair.

**What did not work, or needed rework.**
- DefiLlama's `/chart` endpoint silently skipped about 14% of days. Switching to
  `/batchHistorical` with explicit midnight timestamps left two genuinely missing days.
- The first agent version could explore until the step limit. The last round now offers
  only `submit_answer`.
- Gemini's free tier allows 20 requests per day for `gemini-3.5-flash`, far too few for an
  eval of about 800 calls. The runs use `gemini-3.5-flash-lite`. Groq's free tier (8K tokens
  per minute) cannot fit the naive baseline's prompt at all.
- The prose check flags digits inside counterparty names and step numbers. That turned
  correct answers into "partially verified" ones (see the error analysis).
<!-- DECISIONS:END -->

## Limitations

<!-- LIMITATIONS:START -->
<!-- LIMITATIONS:END -->

## License and data

Code in this repository. Chain data from Etherscan and an archive node, prices from DefiLlama,
recorded for reproducibility. Nothing here is financial advice.
