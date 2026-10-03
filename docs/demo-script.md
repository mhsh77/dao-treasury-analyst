# Demo script (2-3 minutes)

Spoken walkthrough for a video or a call. Short sentences. Screen cues in brackets.

---

**Intro (20 s)**

[README open, image at the top]

This is a treasury analyst for DAOs.
You ask a question in plain English.
It answers with numbers you can check.
Every figure comes from tested code, not from the language model.
And every answer links to the transactions behind it.

The demo uses the Uniswap DAO treasury, the governance timelock on Ethereum.

**A real question (40 s)**

[Terminal: `uv run dao-analyst ask "How much UNI has the treasury sent to the Uniswap Foundation custody multisig in total?" --show-trace`]

Here I ask how much UNI went to the Uniswap Foundation.
The model doesn't read raw transactions.
It calls typed tools: a ranking tool, then a transfer list.
The tools do the math with exact integers.
The answer is 13,142,986.71 UNI, in two transactions.
Both transactions are linked, so you can open them on Etherscan.
The USD value comes with a note: it uses a pinned price snapshot, not live prices.

**Why you can trust the number (40 s)**

[Show the trace: tool calls, then the verification lines]

The model must submit its answer as a list of claims.
Each claim says which tool call it came from.
A verifier checks every claim in code, before you see it.
If a number isn't in the tool output, the answer is sent back once with the problem.
If it still fails, you only get the parts that were verified.
The model can't sneak in its own arithmetic.

**Saying no (20 s)**

[Terminal: ask "Should the DAO sell UNI for stablecoins?", then ask about a random wallet address]

It refuses investment advice and price predictions.
It refuses to look up wallets that aren't the treasury or a verified institution.
And when data is missing, for example a date after the snapshot, it says exactly what is missing.

**The evidence (40 s)**

[README results table]

I tested it on 85 questions, with answers computed by a separate SQL script.
A naive version that reads all raw transactions got 6.5 percent of answerable questions right.
With tools, it gets 88.7 percent.
The verifier didn't raise accuracy on this set. Its job is different: every figure shown to a user is traceable.
I also report what still fails, and why.
Anyone can re-run the whole eval offline, without API keys, with one command.

**Close (10 s)**

The same pipeline works for another DAO with a config change.
The code and the full results are on GitHub.
