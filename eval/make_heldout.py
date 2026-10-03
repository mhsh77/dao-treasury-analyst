"""Held-out question set for evaluating changes made after the v1 error analysis.

Written after v1's failures were known (stated openly in the README), but before any run
of the changed system on them, and with new phrasings and different facts so the changes
are not scored on the questions that motivated them. Run `make questions` to regenerate.
"""

from __future__ import annotations

import json
from pathlib import Path

from make_questions import (
    AGG,
    ALL,
    BAL,
    CMP,
    LIST,
    TOP,
    TX,
    Y,
    bal,
    cmp,
    count,
    flow,
    largest,
    month_max,
    q,
    tags_for,
    top,
    tx,
)

DEF_2024_TX = "0x4d5c546045a5948e200be8acc27a547bbaec977c33bc7681787663c70ba45972"
UF_2022_TX = "0x9188543cd776b65a5f34a6c0d10d5166dfc225b7a5c5fa44bc9b1df812947d42"
OTHER_EOA = "0x00000000219ab540356cbb839cbe05303d7705fa"

HELDOUT = [
    # lookups
    q(
        "lookup",
        "What was the treasury's UNI balance at the end of 2022?",
        bal("UNI", "2022-12-31"),
        [BAL],
    ),
    q(
        "lookup",
        "How much ETH did the treasury hold on 2024-12-31?",
        bal("ETH", "2024-12-31"),
        [BAL],
    ),
    q(
        "lookup",
        "What was the USD value of the treasury's UNI on 2025-06-30?",
        bal("UNI", "2025-06-30", usd=True),
        [BAL],
    ),
    q(
        "lookup",
        f"How much UNI did transaction {DEF_2024_TX} move out of the treasury?",
        tx(DEF_2024_TX, "UNI"),
        [TX],
    ),
    q(
        "lookup",
        f"Which counterparties received UNI in transaction {UF_2022_TX}, and how much in total?",
        tx(UF_2022_TX, "UNI"),
        [TX],
    ),
    q(
        "lookup",
        "What was the single largest UNI transfer out of the treasury in 2022?",
        largest("out", *Y[2022], "UNI"),
        [LIST, TOP],
    ),
    # aggregations
    q(
        "aggregation",
        "How much UNI did the treasury send out in 2023 in total?",
        flow("out", *Y[2023], "UNI"),
        [AGG, CMP],
    ),
    q(
        "aggregation",
        "How much UNI did vester 3 deliver to the treasury?",
        flow("in", *ALL, "UNI", label="vester 3"),
        [AGG, LIST],
    ),
    q(
        "aggregation",
        "Across all its Franchiser delegation contracts, how much UNI did the "
        "treasury delegate in 2022?",
        flow("out", *Y[2022], "UNI", category="delegation"),
        [AGG],
    ),
    q(
        "aggregation",
        "How many outbound UNI transfers went to the Uniswap Council in 2024?",
        {
            "fn": "count_label",
            "direction": "out",
            "start": Y[2024][0],
            "end": Y[2024][1],
            "token": "UNI",
            "label": "Uniswap Council",
        },
        [LIST, AGG],
    ),
    q(
        "aggregation",
        "How many UNI transfers did the treasury receive in 2023?",
        count("in", *Y[2023], "UNI"),
        [LIST, AGG, CMP],
    ),
    q(
        "aggregation",
        "Leaving out the burn, how much UNI did the treasury send out over its whole history?",
        flow("out", *ALL, "UNI") | {"exclude_categories": ["burn"]},
        [AGG],
    ),
    # rankings
    q(
        "ranking",
        "Name the 3 largest recipients of UNI in 2023.",
        top("out", *Y[2023], 3, "UNI"),
        [TOP, AGG],
    ),
    q(
        "ranking",
        "Which counterparty sent the treasury the most UNI in 2022?",
        top("in", *Y[2022], 1, "UNI"),
        [TOP, AGG],
    ),
    q(
        "ranking",
        "In which month of 2023 did the most UNI leave the treasury?",
        month_max("out", 2023, "UNI"),
        [AGG],
    ),
    q(
        "ranking",
        "Rank the top 2 recipients of treasury outflows in 2024 by USD value.",
        top("out", *Y[2024], 2),
        [TOP],
    ),
    # comparisons
    q(
        "comparison",
        "Compare UNI outflows in 2022 with 2023.",
        cmp("outflow", Y[2022], Y[2023], "UNI"),
        [CMP, AGG],
    ),
    q(
        "comparison",
        "How many UNI transfers left the treasury in 2023 versus 2025?",
        [count("out", *Y[2023], "UNI"), count("out", *Y[2025], "UNI")],
        [CMP, LIST, AGG],
    ),
    q(
        "comparison",
        "How did the UNI balance at the end of 2024 compare with the end of 2025?",
        cmp("end_balance", Y[2024], Y[2025], "UNI"),
        [CMP, BAL],
    ),
    q(
        "comparison",
        "By what percentage did UNI inflows change from 2022 to 2023?",
        cmp("inflow", Y[2022], Y[2023], "UNI") | {"take": "pct"},
        [CMP],
    ),
    # multi-step
    q(
        "multistep",
        "How much UNI did the DeFi Education Fund's addresses receive in 2024 in total?",
        flow("out", *Y[2024], "UNI", label="DeFi Education Fund"),
        [AGG, LIST],
    ),
    q(
        "multistep",
        "What was the treasury's UNI balance at the end of 2023, and how much UNI "
        "went out during 2024?",
        [bal("UNI", "2023-12-31"), flow("out", *Y[2024], "UNI")],
        [BAL + AGG, BAL + CMP],
    ),
    q(
        "multistep",
        "Who received the largest UNI outflow in 2024, and how much has the treasury "
        "sent to them in total over its history?",
        [largest("out", *Y[2024], "UNI"), flow("out", *ALL, "UNI", label="Uniswap Council")],
        [LIST + AGG, TOP + AGG, TOP],
    ),
    q(
        "multistep",
        "Excluding transfers to the burn address, how much UNI left the treasury in December 2025?",
        flow("out", "2025-12-01", "2025-12-31", "UNI") | {"exclude_categories": ["burn"]},
        [AGG],
    ),
    q(
        "multistep",
        "How much UNI did the Uniswap Foundation's Franchiser delegation contract "
        "receive, and how much did it send back?",
        [
            flow("out", *ALL, "UNI", label="Franchiser delegation - Uniswap Foundation"),
            flow("in", *ALL, "UNI", label="Franchiser delegation - Uniswap Foundation"),
        ],
        [AGG, LIST],
    ),
    # unanswerable / out of scope
    q("unanswerable", "What is the treasury's ETH balance right now?", expect="abstain"),
    q("unanswerable", "What were total UNI outflows in Q3 2026?", expect="abstain"),
    q("unanswerable", f"What tokens does {OTHER_EOA} hold?", expect="refuse"),
    q(
        "unanswerable",
        "Would buying UNI be a smart investment after the UNIfication burn?",
        expect="refuse",
    ),
    q("unanswerable", "How much is the treasury's BOME worth in dollars?", expect="abstain"),
    q(
        "unanswerable",
        "In US dollars, what were the treasury's UNI holdings worth on October 12, 2022?",
        bal("UNI", "2022-10-12"),
        [BAL],
        expect="amount_only",
    ),
    q("unanswerable", "How much did the Aave DAO treasury receive in 2025?", expect="refuse"),
]

HELDOUT_TAGS = [
    ("right now", "after_snapshot"),
    ("Q3 2026", "after_snapshot"),
    (f"does {OTHER_EOA}", "non_allowlisted"),
    ("smart investment", "advice"),
    ("BOME", "unverified_token"),
    ("October 12, 2022", "missing_price"),
    ("Aave DAO", "out_of_scope"),
]


def main() -> None:
    out = Path(__file__).with_name("questions_heldout.jsonl")
    with out.open("w") as f:
        for i, item in enumerate(HELDOUT, start=1):
            if item["category"] == "unanswerable":
                found = [t for k, t in HELDOUT_TAGS if k in item["question"]]
                assert len(found) == 1, item["question"]
                item["tags"] = found
            else:
                item["tags"] = tags_for(item)
            f.write(json.dumps({"id": f"h{i:03d}", **item}) + "\n")
    print(f"wrote {len(HELDOUT)} held-out questions to {out}")


if __name__ == "__main__":
    main()
