# Eval run `2026-10-03-v2-heldout`

Model: `gemini-3.5-flash-lite` via gemini. Questions: 32. Recorded at 2026-10-04T07:21:17Z from commit `eec19b3`.

| Metric | Naive baseline | Tools, no verifier | Full system |
|---|---:|---:|---:|
| Answer accuracy (answerable questions fully correct) | 4.0% | 88.0% | 88.0% |
| Numeric accuracy (expected figures matched) | 8.6% | 91.4% | 91.4% |
| Claim support rate (claims traceable to tool output) | 0.0% | 100.0% | 100.0% |
| Correct abstain/refuse on unanswerable questions | 83.3% | 100.0% | 100.0% |
| Wrongful refusals on answerable questions (lower is better) | 24.0% | 0.0% | 0.0% |
| Refusal rate: non-allowlisted addresses | 100.0% | 100.0% | 100.0% |
| Refusal rate: advice and price predictions | 100.0% | 100.0% | 100.0% |
| Missing price handled (no invented USD) | 100.0% | 100.0% | 100.0% |
| Tool selection accuracy | n/a | 100.0% | 100.0% |
| Mean tool calls per question | 0.0 | 2.47 | 2.41 |
| Model latency p50 (s) | 1.5 | 3.0 | 2.9 |
| Model latency p95 (s) | 3.2 | 5.6 | 5.3 |
| Mean input tokens per question | 139,355 | 12,453 | 11,573 |
| Approx. cost per question at paid-tier prices (USD) | $0.0423 | $0.0049 | $0.0047 |
| Errors (provider failures, step limit) | 0.0% | 0.0% | 0.0% |

## Accuracy by category

Unanswerable questions count as correct when the system declines without numbers.

| Category | Naive baseline | Tools, no verifier | Full system |
|---|---:|---:|---:|
| aggregation | 0.0% | 100.0% | 100.0% |
| comparison | 0.0% | 100.0% | 100.0% |
| lookup | 0.0% | 83.3% | 83.3% |
| multistep | 20.0% | 60.0% | 60.0% |
| ranking | 0.0% | 100.0% | 100.0% |
| unanswerable | 85.7% | 100.0% | 100.0% |

## Failures: Naive baseline (25)

- `h001` [lookup] outcome=answer. What was the treasury's UNI balance at the end of 2022? - missing 316402449.524099441917661076 UNI
- `h002` [lookup] outcome=abstain. How much ETH did the treasury hold on 2024-12-31? - missing 0.219089824609891454 ETH
- `h003` [lookup] outcome=abstain. What was the USD value of the treasury's UNI on 2025-06-30? - missing 371260163.290000000009999999 UNI; missing 2747325208.35 USD
- `h004` [lookup] outcome=answer. How much UNI did transaction 0x4d5c546045a5948e200be8acc27a547bbaec977c33bc7681787663c70ba45972 move out of the treasury? - missing 1000000 UNI
- `h005` [lookup] outcome=answer. Which counterparties received UNI in transaction 0x9188543cd776b65a5f34a6c0d10d5166dfc225b7a5c5fa44bc9b1df812947d42, and how much in total? - missing 4957002.000000000000000001 UNI
- `h006` [lookup] outcome=answer. What was the single largest UNI transfer out of the treasury in 2022? - missing 2500000.000000000000000001 UNI; missing mention of [['Franchiser delegation - Uniswap Foundation', '0x3d4acfd2c8b0641fb8db762179ee5a8db385e573']]
- `h007` [aggregation] outcome=answer. How much UNI did the treasury send out in 2023 in total? - missing 20700317.71 UNI
- `h008` [aggregation] outcome=answer. How much UNI did vester 3 deliver to the treasury? - missing 86000000 UNI
- `h009` [aggregation] outcome=abstain. Across all its Franchiser delegation contracts, how much UNI did the treasury delegate in 2022? - missing 2500000.000000000000000001 UNI
- `h010` [aggregation] outcome=answer. How many outbound UNI transfers went to the Uniswap Council in 2024? - missing 11 count
- `h011` [aggregation] outcome=answer. How many UNI transfers did the treasury receive in 2023? - missing 8 count
- `h012` [aggregation] outcome=answer. Leaving out the burn, how much UNI did the treasury send out over its whole history? - missing 70365150.710000000000000001 UNI
- `h013` [ranking] outcome=answer. Name the 3 largest recipients of UNI in 2023. - missing 10685984.71 UNI; missing 2499858 UNI; missing mention of [['Uniswap Foundation custody multisig', '0xe571dc7a558bb6d68ffe264c3d7bb98b0c6c73fc'], ['Franchiser delegation - Anode (fka StableLab)', '0xfb6b912cf7082031822f52e7d7ef59280f97a257'], ['Franchiser delegation - PGov', '0x61bed6a58c4dc592f1dc32f9ec0f67e49208405c']]
- `h014` [ranking] outcome=answer. Which counterparty sent the treasury the most UNI in 2022? - missing 126077347.795281582952815831 UNI
- `h015` [ranking] outcome=abstain. In which month of 2023 did the most UNI leave the treasury? - missing 10685984.71 UNI; missing mention of [['2023-10', 'October']]
- `h016` [ranking] outcome=abstain. Rank the top 2 recipients of treasury outflows in 2024 by USD value. - missing 11239459.63 USD; missing 5380000.00 USD; missing mention of [['Uniswap Council (formerly Uniswap Accountability Committee) primary multisig', '0x3b59c6d0034490093460787566dc5d6ce17f2f9c'], ['DeFi Education Fund UNI stream contract', '0x3b560de4db054b54945ec95c8c346d8901cfdab9']]
- `h017` [comparison] outcome=answer. Compare UNI outflows in 2022 with 2023. - missing 5967206.000000000000000001 UNI; missing 20700317.71 UNI
- `h018` [comparison] outcome=answer. How many UNI transfers left the treasury in 2023 versus 2025? - missing 9 count; missing 13 count
- `h019` [comparison] outcome=answer. How did the UNI balance at the end of 2024 compare with the end of 2025? - missing 399516926.290000000009999999 UNI; missing 269634857.290100000009999999 UNI
- `h020` [comparison] outcome=answer. By what percentage did UNI inflows change from 2022 to 2023? - missing -50.46 percent
- `h021` [multistep] outcome=answer. How much UNI did the DeFi Education Fund's addresses receive in 2024 in total? - missing 1000000 UNI
- `h022` [multistep] outcome=answer. What was the treasury's UNI balance at the end of 2023, and how much UNI went out during 2024? - missing 369506042.287209538315428714 UNI; missing 2296058 UNI
- `h023` [multistep] outcome=abstain. Who received the largest UNI outflow in 2024, and how much has the treasury sent to them in total over its history? - missing 549124 UNI; missing 1615832 UNI; missing mention of [['Uniswap Council (formerly Uniswap Accountability Committee) primary multisig', '0x3b59c6d0034490093460787566dc5d6ce17f2f9c']]
- `h024` [multistep] outcome=answer. Excluding transfers to the burn address, how much UNI left the treasury in December 2025? - missing 34615 UNI
- `h030` [unanswerable] outcome=abstain. How much is the treasury's BOME worth in dollars? 

## Failures: Tools, no verifier (3)

- `h004` [lookup] outcome=answer. How much UNI did transaction 0x4d5c546045a5948e200be8acc27a547bbaec977c33bc7681787663c70ba45972 move out of the treasury? - missing 1000000 UNI
- `h021` [multistep] outcome=answer. How much UNI did the DeFi Education Fund's addresses receive in 2024 in total? - missing 1000000 UNI
- `h023` [multistep] outcome=answer. Who received the largest UNI outflow in 2024, and how much has the treasury sent to them in total over its history? - missing 549124 UNI

## Failures: Full system (3)

- `h004` [lookup] outcome=answer. How much UNI did transaction 0x4d5c546045a5948e200be8acc27a547bbaec977c33bc7681787663c70ba45972 move out of the treasury? - missing 1000000 UNI
- `h021` [multistep] outcome=answer. How much UNI did the DeFi Education Fund's addresses receive in 2024 in total? - missing 1000000 UNI
- `h023` [multistep] outcome=answer. Who received the largest UNI outflow in 2024, and how much has the treasury sent to them in total over its history? - missing 549124 UNI
