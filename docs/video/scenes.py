"""Scenes of the project video: one slide (HTML) and one narration paragraph each.

Every number and every answer shown comes from the repository's recorded eval runs
(eval/runs/) or its data layer; nothing here is invented for the video.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scene:
    id: str
    html: str
    narration: str


def term(lines: str) -> str:
    return f'<div class="term">{lines}</div>'


SCENES = [
    Scene(
        "01-title",
        """<div class="center">
  <div class="kicker">Open-source AI agent · Ethereum · Uniswap DAO</div>
  <h1 class="big">DAO Treasury Analyst</h1>
  <p class="lead">Plain-English answers about a DAO treasury.<br>
  Every number computed by tested code. Every claim checked and linked on-chain.</p>
  <div class="pill">github.com/mhsh77/dao-treasury-analyst</div>
</div>""",
        "This is DAO Treasury Analyst. You ask a question about a DAO's treasury in plain "
        "English. You get an answer where every number was computed by tested code, checked "
        "before you see it, and linked to the transactions behind it. In the next few minutes "
        "I'll show how it works, and how I measured whether it is actually right.",
    ),
    Scene(
        "02-problem",
        """<h2>The problem: confident, wrong numbers</h2>
<p class="lead">A language model reading raw transactions, asked:
<em>"What were the treasury's total UNI outflows in 2024?"</em></p>
<div class="cols">
  <div class="card bad"><div class="label">Model reading raw data</div>
    <div class="num">925,034,000,000,000,000,000,000 UNI</div>
    <div class="small">forgot to divide by 10<sup>18</sup></div></div>
  <div class="card good"><div class="label">Correct (independent SQL)</div>
    <div class="num">2,296,058 UNI</div>
    <div class="small">sum of 14 transfers</div></div>
</div>
<p class="foot">Recorded answer from the naive baseline in the eval (question q017).</p>""",
        "Here is the problem. If you paste a treasury's raw transactions into a language model "
        "and ask for total outflows in 2024, it answers confidently. In my evaluation it said "
        "nine hundred twenty-five sextillion UNI. It forgot that token amounts have eighteen "
        "decimals. The real answer is about two point three million. For treasury reporting, a "
        "fluent answer is worthless if the number is wrong.",
    ),
    Scene(
        "03-data",
        """<h2>A pinned, verified snapshot of the treasury</h2>
<div class="grid3">
  <div class="card"><div class="num">25,433,938</div><div class="small">snapshot block<br>2026-06-30 23:59:59 UTC</div></div>
  <div class="card"><div class="num">498</div><div class="small">normalized transfers<br>342 spam-token transfers flagged</div></div>
  <div class="card"><div class="num">25</div><div class="small">hand-verified labels<br>each with a source URL</div></div>
</div>
<ul class="list">
  <li>Etherscan, an archive node and DefiLlama prices, recorded once and replayed offline</li>
  <li>Balances rebuilt from transfers <b>match on-chain balances exactly</b> for ETH, UNI, USDC and USDT</li>
  <li>Tokens verified by contract address: a fake "UNI" airdrop is ignored</li>
</ul>""",
        "It starts with data I can trust. The pipeline pulls the full history of the Uniswap "
        "governance timelock from Etherscan, an archive node and DefiLlama prices, and pins it "
        "at one block, the end of June twenty twenty-six. Every response is recorded, so the "
        "whole thing replays offline. As a check, I rebuilt the balances from the transfers "
        "and compared them with the chain. They match exactly. Tokens are verified by contract "
        "address, so a spam token that calls itself UNI is ignored. And every counterparty "
        "label has a source; anything I couldn't verify stays unlabeled.",
    ),
    Scene(
        "04-architecture",
        """<h2>How an answer is made</h2>
<div class="flow">
  <div class="box">Question</div><div class="arrow">→</div>
  <div class="box">Guardrails<br><span>allowlist · advice</span></div><div class="arrow">→</div>
  <div class="box hl">LLM agent<br><span>plans tool calls</span></div><div class="arrow">⇄</div>
  <div class="box">Typed tools<br><span>exact integer math</span></div>
</div>
<div class="flow">
  <div class="box">Structured claims<br><span>value · unit · cited call</span></div><div class="arrow">→</div>
  <div class="box hl">Claim verifier<br><span>checks every number</span></div><div class="arrow">→</div>
  <div class="box">Answer<br><span>+ tx links + caveats</span></div>
</div>
<p class="foot">Tools read a local DuckDB store built from the pinned snapshot.</p>""",
        "Here is the architecture. The language model never sees raw transactions and never "
        "does arithmetic. It plans calls to typed tools: balances, flows, rankings, period "
        "comparisons and transaction details. The tools compute with exact integers. The model "
        "then submits its answer as structured claims, and each claim names the tool call it "
        "came from. A verifier checks every one of those numbers in code before the user sees "
        "anything.",
    ),
    Scene(
        "05-answer",
        term("""<div><span class="g">$</span> dao-analyst ask "How much UNI has the treasury sent to the Uniswap Foundation custody multisig in total?"</div>
<pre>The treasury has sent a total of 13,142,986.71 UNI to the Uniswap Foundation custody
multisig, with a historical USD value of $59,277,734.43 across two transactions.

Supporting transactions:
- https://etherscan.io/tx/0x9188543cd776b65a5f34a6c0d10d5166dfc225b7a5c5fa44bc9b1df812947d42
- https://etherscan.io/tx/0xd8304a661d34282ed988507f5b9353605062e92a5f621becf3a5284076b66b0e

Caveats:
- USD figures use the pinned price snapshot (DefiLlama), not live prices.</pre>
<div class="m">tool calls: <span class="p">describe_snapshot → top_counterparties → list_transfers</span> · claims verified: 2/2</div>""")
        + '<p class="foot">Recorded answer (eval question q021), model gemini-3.5-flash-lite.</p>',
        "Here is a real answer. I ask how much UNI the treasury has sent to the Uniswap "
        "Foundation. The agent calls three tools, and answers: thirteen point one four million "
        "UNI, in two transactions. Both transactions are linked, so anyone can open them on "
        "Etherscan. The dollar value comes with a caveat: it uses a pinned price snapshot, not "
        "live prices. Both claims were verified against the tool output.",
    ),
    Scene(
        "06-verifier",
        """<h2>The claim verifier</h2>
<div class="cols">
<div class="code"><pre>{
  "id": "c1",
  "value": "13142986.71",
  "unit": "UNI",
  "source_call_ids": ["c2"],
  "tx_hashes": ["0x9188…", "0xd830…"]
}</pre><div class="ok">✓ matches c2: counterparties[2].amounts[0].amount</div></div>
<ul class="list">
  <li>Each value must appear in the cited tool result, with the right unit</li>
  <li>Tx hashes must come from that result</li>
  <li>No stray digits in the prose: numbers only via claim placeholders</li>
  <li>On failure: one retry with the exact problems</li>
  <li>Still failing: only verified parts are shown</li>
</ul></div>""",
        "This is the verifier. A claim is a value, a unit, the call it came from, and its "
        "transactions. The verifier finds that value in the stored tool result, checks the unit "
        "and the transaction hashes, and rejects any number written into the prose that isn't a "
        "verified claim. If something fails, the model gets one retry with the exact problems. "
        "If it fails again, the user only sees the verified parts. A number the model computed "
        "itself is rejected, even when it happens to be right.",
    ),
    Scene(
        "07-safety",
        """<h2>Knowing when to say no</h2>
<div class="qa"><div class="q">What is your price prediction for UNI at the end of 2026?</div>
<div class="a">"I can't give investment advice, price predictions or trading recommendations."</div></div>
<div class="qa"><div class="q">Who owns the address 0x5069a64b…7e?</div>
<div class="a">"I only report on the configured treasury and hand-verified institutional counterparties.
Looking up other addresses could mean profiling private individuals."</div></div>
<div class="qa"><div class="q">What were the treasury's UNI outflows in July 2026?</div>
<div class="a">Abstained: "The snapshot end date is 2026-06-30, so July 2026 is outside the data scope."</div></div>
<p class="foot">Recorded answers from the eval (q075, q069, q063).</p>""",
        "Just as important is knowing when to say no. It refuses investment advice and price "
        "predictions. It refuses to look up wallets that aren't the treasury or a verified "
        "institution, because that could mean profiling private people. And when the data "
        "simply isn't there, like a date after the snapshot, it abstains and says exactly what "
        "is missing. These are real recorded answers from the evaluation.",
    ),
    Scene(
        "08-eval",
        """<h2>Measuring it, not trusting it</h2>
<div class="grid3">
  <div class="card"><div class="num">85</div><div class="small">questions: lookups, aggregations,<br>rankings, comparisons, multi-step,<br>23 unanswerable</div></div>
  <div class="card"><div class="num">45 / 45</div><div class="small">figures where the tools agree with<br>an independent SQL ground truth</div></div>
  <div class="card"><div class="num">615</div><div class="small">recorded model calls:<br>the eval replays offline, no keys</div></div>
</div>
<ul class="list">
  <li><b>Naive baseline</b>: raw transactions, labels and prices in the prompt</li>
  <li><b>Tools, no verifier</b>: the ablation</li>
  <li><b>Full system</b>: tools + verifier + abstention</li>
</ul>""",
        "Then I measured it. I wrote eighty-five questions, including twenty-three that should "
        "be declined. The expected answers come from a separate SQL script that shares no code "
        "with the tools, and the two agree on every figure they can both compute. I compared "
        "three setups with the same model: a naive baseline that reads the raw transactions, "
        "the tools without the verifier, and the full system. Every model call is recorded, so "
        "anyone can replay the evaluation offline and get identical numbers.",
    ),
    Scene(
        "09-results",
        """<h2>Results (85 questions, gemini-3.5-flash-lite)</h2>
<table>
<tr><th></th><th>Naive baseline</th><th>Tools, no verifier</th><th>Full system</th></tr>
<tr><td>Answer accuracy</td><td class="bad">6.5%</td><td>88.7%</td><td class="good">88.7%</td></tr>
<tr><td>Numeric accuracy</td><td class="bad">5.3%</td><td>91.5%</td><td class="good">92.5%</td></tr>
<tr><td>Claims traceable to tool output</td><td class="bad">0%</td><td>98.9%</td><td class="good">99.4%</td></tr>
<tr><td>Wrongful refusals</td><td class="bad">25.8%</td><td>0%</td><td class="good">0%</td></tr>
<tr><td>Refused advice &amp; unknown wallets</td><td>100%</td><td>100%</td><td class="good">100%</td></tr>
<tr><td>Input tokens per question</td><td>139,356</td><td>12,857</td><td>13,739</td></tr>
</table>""",
        "Here are the results. The naive baseline answered six and a half percent of the "
        "answerable questions correctly, and wrongly gave up on a quarter of them. With typed "
        "tools, accuracy jumps to almost eighty-nine percent, using a tenth of the tokens. "
        "Advice requests and unknown wallets were refused every time.",
    ),
    Scene(
        "10-honest",
        """<h2>An honest finding</h2>
<p class="lead">The claim verifier did <b>not</b> raise accuracy: 88.7% with and without it.</p>
<ul class="list">
  <li>With tools, the model never invented a number</li>
  <li>The verifier rejected two <em>correct</em> sums the model computed itself</li>
  <li>Its prose check had false positives: "fka <b>404</b>DAO", list numbers</li>
  <li>What it buys: every figure a user sees is traceable to a cited tool result</li>
</ul>
<p class="foot">Failures, causes and fixes are documented in the README's error analysis.</p>""",
        "There's also a finding I didn't expect, and I report it as it is. The verifier did not "
        "raise accuracy. Once the model had tools, it never invented a number. The verifier "
        "rejected two correct sums the model had computed itself, and its prose check flagged "
        "harmless digits, like the four hundred four in a delegate's name. So its value is a "
        "guarantee, not a score: every figure a user sees can be traced to a tool result.",
    ),
    Scene(
        "11-heldout",
        """<h2>Fixing the failures, tested on new questions</h2>
<div class="cols">
<ul class="list">
  <li>Direction filter for transfer counts</li>
  <li>Totals across one organization's addresses; "excluding the burn"</li>
  <li>Prose check ignores digits inside label names</li>
  <li>"Today" / "now" questions abstain</li>
</ul>
<table>
<tr><th>32 held-out questions</th><th>v1</th><th>v2</th></tr>
<tr><td>Answer accuracy</td><td>76.0%</td><td class="good">88.0%</td></tr>
<tr><td>Correct declines</td><td>83.3%</td><td class="good">100%</td></tr>
<tr><td>Claims traceable</td><td>93.8%</td><td class="good">100%</td></tr>
<tr><td>Naive baseline</td><td colspan="2">4.0%</td></tr>
</table></div>
<p class="foot">Small sample, one run each: the gain is three questions, each traced to a specific fix.</p>""",
        "The error analysis pointed to four fixes. To avoid tuning on the test, I evaluated them "
        "on thirty-two new held-out questions, and ran the old code on the same questions. "
        "Accuracy went from seventy-six to eighty-eight percent, and correct refusals from "
        "eighty-three to a hundred. It's a small sample, so I traced every changed answer to the "
        "fix that caused it.",
    ),
    Scene(
        "12-interfaces",
        """<h2>Use it where you work</h2>
<div class="grid3">
  <div class="card"><div class="num">CLI</div><div class="small">dao-analyst ask "…"<br>with --show-trace</div></div>
  <div class="card"><div class="num">Telegram</div><div class="small">@daotreasuryanalystbot<br>rate limits, allowlist</div></div>
  <div class="card"><div class="num">Docker</div><div class="small">docker compose up -d<br>runs on a small VPS</div></div>
</div>
<ul class="list">
  <li>Any OpenAI-compatible model: Gemini, Groq, OpenRouter</li>
  <li>Another DAO or EVM chain: a config change, not a code change</li>
  <li>Audit log of every question, tool call and verification</li>
</ul>""",
        "You can use it from the command line, or as a Telegram bot, and it ships with Docker "
        "for a small server. The model provider is swappable, and pointing it at another DAO or "
        "another EVM chain is a configuration change. Every question, tool call and "
        "verification result is written to an audit log.",
    ),
    Scene(
        "13-reproduce",
        "<h2>Reproduce it yourself</h2>"
        + term("""<div><span class="g">$</span> git clone https://github.com/mhsh77/dao-treasury-analyst</div>
<div><span class="g">$</span> make install</div>
<div><span class="g">$</span> make ingest   <span class="m"># rebuild the store from recorded fixtures, offline</span></div>
<div><span class="g">$</span> make eval     <span class="m"># replay the eval, recompute every metric, no API keys</span></div>
<div><span class="g">$</span> make check    <span class="m"># lint, strict types, 159 tests</span></div>"""),
        "And you don't have to trust me either. Clone the repository, and three commands "
        "rebuild the data, replay the full evaluation and run all the tests, offline, without "
        "any API keys.",
    ),
    Scene(
        "14-close",
        """<div class="center">
  <h1 class="big">Numbers you can check.</h1>
  <p class="lead">Typed tools · claim verification · honest evaluation</p>
  <div class="pill">github.com/mhsh77/dao-treasury-analyst</div>
  <p class="small" style="margin-top:40px">Not financial advice. Data: Ethereum mainnet up to block 25,433,938.</p>
</div>""",
        "That's DAO Treasury Analyst: typed tools, verified claims, and an evaluation you can "
        "rerun yourself. If you run a DAO and want this for your treasury, it's a config change "
        "away. The code and every result are on GitHub.",
    ),
]
