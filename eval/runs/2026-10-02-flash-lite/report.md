# Eval run `2026-10-02-flash-lite`

Model: `gemini-3.5-flash-lite` via gemini. Questions: 85. Recorded at 2026-10-03T07:21:23Z from commit `5823423`.

| Metric | Naive baseline | Tools, no verifier | Full system |
|---|---:|---:|---:|
| Answer accuracy (answerable questions fully correct) | 6.5% | 88.7% | 88.7% |
| Numeric accuracy (expected figures matched) | 5.3% | 91.5% | 92.5% |
| Claim support rate (claims traceable to tool output) | 0.0% | 98.9% | 99.4% |
| Correct abstain/refuse on unanswerable questions | 85.7% | 90.5% | 90.5% |
| Wrongful refusals on answerable questions (lower is better) | 25.8% | 0.0% | 0.0% |
| Refusal rate: non-allowlisted addresses | 100.0% | 100.0% | 100.0% |
| Refusal rate: advice and price predictions | 100.0% | 100.0% | 100.0% |
| Missing price handled (no invented USD) | 100.0% | 100.0% | 100.0% |
| Tool selection accuracy | n/a | 100.0% | 100.0% |
| Mean tool calls per question | 0.0 | 2.42 | 2.31 |
| Model latency p50 (s) | 1.6 | 3.0 | 2.7 |
| Model latency p95 (s) | 4.7 | 10.7 | 10.1 |
| Mean input tokens per question | 139,356 | 12,857 | 13,739 |
| Approx. cost per question at paid-tier prices (USD) | $0.0425 | $0.0050 | $0.0057 |
| Errors (provider failures, step limit) | 0.0% | 0.0% | 1.2% |

## Accuracy by category

Unanswerable questions count as correct when the system declines without numbers.

| Category | Naive baseline | Tools, no verifier | Full system |
|---|---:|---:|---:|
| aggregation | 0.0% | 81.2% | 93.8% |
| comparison | 0.0% | 90.0% | 90.0% |
| lookup | 18.8% | 87.5% | 93.8% |
| multistep | 0.0% | 90.0% | 60.0% |
| ranking | 10.0% | 100.0% | 100.0% |
| unanswerable | 87.0% | 91.3% | 91.3% |

## Failures: Naive baseline (61)

- `q001` [lookup] outcome=abstain. What was the treasury's UNI balance at the end of the snapshot? - missing 272134858.47907041001 UNI
- `q002` [lookup] outcome=abstain. How much UNI did the Uniswap treasury hold on 2023-12-31? - missing 369506042.287209538315428714 UNI
- `q003` [lookup] outcome=answer. What was the UNI balance of the treasury on January 1, 2022? - missing 173403155.204718417047184169 UNI
- `q004` [lookup] outcome=answer. What was the USD value of the treasury's UNI holdings on 2024-06-30? - missing 383266633.530740740750740737 UNI; missing 3389646562.64 USD
- `q005` [lookup] outcome=abstain. How much ETH does the treasury hold at the end of the snapshot? - missing 0.230707525462629109 ETH
- `q006` [lookup] outcome=answer. How much USDC did the treasury hold at the end of 2024? - missing 125.383008 USDC
- `q007` [lookup] outcome=answer. What is the treasury's USDT balance at the end of the snapshot? - missing 1002.280283 USDT
- `q008` [lookup] outcome=abstain. What was the total USD value of the treasury's verified holdings at the end of the snapshot? - missing 787132994.25 USD
- `q009` [lookup] outcome=abstain. What was the treasury's UNI balance the day before the 100M UNI burn, on 2025-12-26? - missing 369634857.290100000009999999 UNI
- `q012` [lookup] outcome=answer. How much UNI came back to the treasury in transaction 0x2eceb744813b41ff7f1266acad4904ef1ffcf7435104b609f70d14685d29838c? - missing 12500001.188970410000000001 UNI
- `q013` [lookup] outcome=answer. What did transaction 0x11ca81ecc4fb988bb8e2922d0fa6a82e66abc6e50180ed45196c8a2dc5323bd8 send from the treasury? - missing 7588532 UNI
- `q014` [lookup] outcome=answer. What was the largest single UNI outflow from the treasury in 2024? - missing 549124 UNI; missing mention of [['Uniswap Council (formerly Uniswap Accountability Committee) primary multisig', '0x3b59c6d0034490093460787566dc5d6ce17f2f9c']]
- `q016` [lookup] outcome=answer. How much UNI did the treasury send to the burn address? - missing 100000000 UNI
- `q017` [aggregation] outcome=answer. What were the treasury's total UNI outflows in 2024? - missing 2296058 UNI
- `q018` [aggregation] outcome=answer. What were the treasury's total UNI outflows in 2025? - missing 129882069 UNI
- `q019` [aggregation] outcome=answer. How much UNI did the treasury receive from the treasury vesting contracts in total? - missing 430000002 UNI
- `q020` [aggregation] outcome=abstain. How much UNI did the treasury vesters deliver in 2021? - missing 126692880.105276509386098429 UNI
- `q021` [aggregation] outcome=answer. How much UNI has the treasury sent to the Uniswap Foundation custody multisig in total? - missing 13142986.71 UNI
- `q022` [aggregation] outcome=answer. What was the total UNI sent to grant recipients over the treasury's history? - missing 2500000 UNI
- `q023` [aggregation] outcome=abstain. How much UNI did the treasury send to the Uniswap Council (formerly the Accountability Committee) in 2024? - missing 1219058 UNI
- `q024` [aggregation] outcome=answer. How much UNI went from the treasury to Franchiser delegation contracts in 2023? - missing 10000000 UNI
- `q025` [aggregation] outcome=answer. How much UNI was returned to the treasury from Franchiser delegation contracts in 2026? - missing 12500001.188970410000000001 UNI
- `q026` [aggregation] outcome=abstain. What was the USD value of UNI outflows in Q2 2024, at transfer-time prices? - missing 12382228.10 USD
- `q027` [aggregation] outcome=answer. How many UNI outflow transfers did the treasury make in 2025? - missing 13 count
- `q028` [aggregation] outcome=abstain. How many inbound transfers of verified tokens did the treasury receive in 2022? - missing 29 count
- `q029` [aggregation] outcome=answer. What was the treasury's total USDC received over its whole history? - missing 135.383008 USDC
- `q030` [aggregation] outcome=answer. What were total UNI outflows in the second half of 2023? - missing 20685984.71 UNI
- `q031` [aggregation] outcome=answer. How much ETH did the treasury forward to the Arbitrum Delayed Inbox in total? - missing 0.02314835 ETH
- `q032` [aggregation] outcome=answer. What was the net UNI flow of the treasury in 2026 up to the snapshot end? - missing 2500001.188970410000000001 UNI
- `q033` [ranking] outcome=answer. Who were the top 5 recipients of UNI from the treasury over its whole history? - missing 100000000 UNI; missing 20320405 UNI; missing 13142986.71 UNI; missing 10000000 UNI; missing 7588532 UNI; missing mention of [['Burn address (0x...dead)', '0x000000000000000000000000000000000000dead'], ['0x5069a64bc6616dec1584ee0500b7813a9b680f7e'], ['Uniswap Foundation custody multisig', '0xe571dc7a558bb6d68ffe264c3d7bb98b0c6c73fc'], ['0xaba63748c4b4def4a3319c3a29fe4829029d926f'], ['AeraVaultV2 contract', '0x7c8406384f7a5c147a6add16407803be146147e4']]
- `q034` [ranking] outcome=abstain. Rank the top 3 recipients of treasury outflows in 2025 by USD value at transfer time. - missing 582694237.37 USD; missing 140007590.45 USD; missing 52284985.48 USD; missing mention of [['Burn address (0x...dead)', '0x000000000000000000000000000000000000dead'], ['0x5069a64bc6616dec1584ee0500b7813a9b680f7e'], ['AeraVaultV2 contract', '0x7c8406384f7a5c147a6add16407803be146147e4']]
- `q035` [ranking] outcome=answer. Which 3 counterparties received the most UNI from the treasury in 2024? - missing 1219058 UNI; missing 500000 UNI; missing 500000 UNI
- `q037` [ranking] outcome=answer. List the top 4 sources of UNI inflows to the treasury over its history. - missing 172000000 UNI; missing 129000002 UNI; missing 86000000 UNI; missing 43000000 UNI; missing mention of [['UNI treasury vester 1 (year 1)', '0x4750c43867ef5f89869132eccf19b9b6c4286e1a'], ['UNI treasury vester 2 (year 2)', '0xe3953d9d317b834592ab58ab2c7a6ad22b54075d'], ['UNI treasury vester 3 (year 3)', '0x4b4e140d1f131fdad6fb59c13af796fd194e4135'], ['UNI treasury vester 4 (year 4)', '0x3d30b1ab88d487b0f3061f40de76845bec3f1e94']]
- `q038` [ranking] outcome=answer. Which Franchiser delegation contract received the most UNI in 2023, and how much? - missing 2499858 UNI; missing mention of [['Franchiser delegation - Anode (fka StableLab)', '0xfb6b912cf7082031822f52e7d7ef59280f97a257']]
- `q039` [ranking] outcome=answer. What were the 3 largest UNI outflow transfers in 2023? - missing 10685984.71 UNI; missing 2499858 UNI; missing 2250000 UNI
- `q040` [ranking] outcome=abstain. Who received ETH from the treasury over its history, and how much each? - missing 0.02314835 ETH; missing mention of [['Arbitrum One Delayed Inbox (L1 -> L2 messages)', '0x4dbd4fc535ac27206064b68ffcf827b0a60bab3f']]
- `q041` [ranking] outcome=answer. Which month of 2024 had the largest UNI outflows, and how much went out? - missing 1194155 UNI
- `q042` [ranking] outcome=abstain. Which month of 2025 had the largest UNI outflows? - missing 100034615 UNI; missing mention of [['2025-12', 'December']]
- `q043` [comparison] outcome=answer. Compare the treasury's UNI outflows in 2024 and 2025. - missing 2296058 UNI; missing 129882069 UNI
- `q044` [comparison] outcome=answer. How did UNI inflows in 2021 compare with 2022? - missing 126692880.105276509386098429 UNI; missing 148966500.319381024870476908 UNI
- `q045` [comparison] outcome=answer. How did the treasury's UNI balance change between the end of 2023 and the end of 2024? - missing 369506042.287209538315428714 UNI; missing 399516926.290000000009999999 UNI
- `q046` [comparison] outcome=abstain. Were there more verified-token transfers in H1 2024 or H2 2024? Give both counts. - missing 10 count; missing 13 count
- `q047` [comparison] outcome=answer. Compare UNI outflows in Q1 2025 with Q1 2024. - missing 549124 UNI; missing 28010981 UNI
- `q048` [comparison] outcome=answer. What was the percentage change in UNI outflows from 2023 to 2024? - missing -88.91 percent
- `q049` [comparison] outcome=answer. How did the UNI balance at the end of 2021 compare with the end of 2022? - missing 173403155.204718417047184169 UNI; missing 316402449.524099441917661076 UNI
- `q050` [comparison] outcome=abstain. Compare the USD value of all treasury outflows in 2023 and 2024 at transfer-time prices. - missing 105774756.18 USD; missing 22703239.63 USD
- `q051` [comparison] outcome=answer. Did the treasury receive more UNI in the first half of 2026 than in all of 2025? - missing 0.0001 UNI; missing 12500001.188970410000000001 UNI
- `q052` [comparison] outcome=answer. How did the number of UNI outflow transfers in 2024 compare with 2025? - missing 14 count; missing 13 count
- `q053` [multistep] outcome=answer. Find the largest UNI outflow in 2025, then tell me the treasury's UNI balance at the end of that day. - missing 100000000 UNI; missing 269634857.290100000009999999 UNI; missing mention of [['Burn address (0x...dead)', '0x000000000000000000000000000000000000dead']]
- `q054` [multistep] outcome=answer. Who received the largest UNI transfer in 2023, and how much UNI has that counterparty received from the treasury in total? - missing 10685984.71 UNI; missing 13142986.71 UNI; missing mention of [['Uniswap Foundation custody multisig', '0xe571dc7a558bb6d68ffe264c3d7bb98b0c6c73fc']]
- `q055` [multistep] outcome=answer. How much UNI did the treasury delegate through Franchiser contracts in total, and how much came back in 2026? - missing 12500000.000000000000000001 UNI; missing 12500001.188970410000000001 UNI
- `q056` [multistep] outcome=answer. What was the treasury's UNI balance at the end of 2024 and its USD value, and what were total UNI outflows that year? - missing 399516926.290000000009999999 UNI; missing 5321565458.18 USD; missing 2296058 UNI
- `q057` [multistep] outcome=answer. In transaction 0x1a1cb38f00454942457922c4dc1dbfc767d06f627fb6d7b8e6d17937fef61833, how many delegation contracts received UNI and what was the total? - missing 10000000 UNI
- `q058` [multistep] outcome=answer. How much UNI did the DeFi Education Fund receive from the treasury in total, across all its labeled addresses? - missing 2000000 UNI
- `q059` [multistep] outcome=abstain. What were total UNI outflows to the Uniswap Council in 2025, and how many transfers was that? - missing 382441 UNI; missing 8 count
- `q060` [multistep] outcome=abstain. How much UNI did the treasury hold right before the first vesting transfer of 2022, and how much did the vesters deliver that year? - missing 173403155.204718417047184169 UNI; missing 148966500.319381024860476908 UNI
- `q061` [multistep] outcome=answer. What happened in transaction 0xd6c4c93eaaac3b6cf144853655f91b326c5e3019b022baeec08eaf74c8af9833? How much ETH moved in and out? - missing 0.02004 ETH; missing 0.02004 ETH
- `q062` [multistep] outcome=answer. Excluding the burn, what were the treasury's total UNI outflows in 2025? - missing 29882069 UNI
- `q064` [unanswerable] outcome=answer. What is the treasury's UNI balance today? 
- `q080` [unanswerable] outcome=abstain. What is the USD value of the BOME tokens the treasury received? 
- `q081` [unanswerable] outcome=answer. How much is the treasury's UNI-V3 token position worth in USD? 

## Failures: Tools, no verifier (9)

- `q004` [lookup] outcome=answer. What was the USD value of the treasury's UNI holdings on 2024-06-30? - missing 383266633.530740740750740737 UNI
- `q012` [lookup] outcome=answer. How much UNI came back to the treasury in transaction 0x2eceb744813b41ff7f1266acad4904ef1ffcf7435104b609f70d14685d29838c? - missing 12500001.188970410000000001 UNI
- `q025` [aggregation] outcome=answer. How much UNI was returned to the treasury from Franchiser delegation contracts in 2026? - missing 12500001.188970410000000001 UNI
- `q027` [aggregation] outcome=answer. How many UNI outflow transfers did the treasury make in 2025? - missing 13 count
- `q028` [aggregation] outcome=answer. How many inbound transfers of verified tokens did the treasury receive in 2022? - missing 29 count
- `q052` [comparison] outcome=answer. How did the number of UNI outflow transfers in 2024 compare with 2025? - missing 13 count
- `q061` [multistep] outcome=answer. What happened in transaction 0xd6c4c93eaaac3b6cf144853655f91b326c5e3019b022baeec08eaf74c8af9833? How much ETH moved in and out? - missing 0.02004 ETH; missing 0.02004 ETH
- `q064` [unanswerable] outcome=answer. What is the treasury's UNI balance today? 
- `q081` [unanswerable] outcome=answer. How much is the treasury's UNI-V3 token position worth in USD? 

## Failures: Full system (9)

- `q012` [lookup] outcome=answer. How much UNI came back to the treasury in transaction 0x2eceb744813b41ff7f1266acad4904ef1ffcf7435104b609f70d14685d29838c? - missing 12500001.188970410000000001 UNI
- `q028` [aggregation] outcome=answer. How many inbound transfers of verified tokens did the treasury receive in 2022? - missing 29 count
- `q052` [comparison] outcome=answer. How did the number of UNI outflow transfers in 2024 compare with 2025? - missing 13 count
- `q053` [multistep] outcome=partial. Find the largest UNI outflow in 2025, then tell me the treasury's UNI balance at the end of that day. - missing mention of [['Burn address (0x...dead)', '0x000000000000000000000000000000000000dead']]
- `q058` [multistep] outcome=answer. How much UNI did the DeFi Education Fund receive from the treasury in total, across all its labeled addresses? - missing 2000000 UNI
- `q061` [multistep] outcome=partial. What happened in transaction 0xd6c4c93eaaac3b6cf144853655f91b326c5e3019b022baeec08eaf74c8af9833? How much ETH moved in and out? - missing 0.02004 ETH; missing 0.02004 ETH
- `q062` [multistep] outcome=error. Excluding the burn, what were the treasury's total UNI outflows in 2025? - missing 29882069 UNI
- `q064` [unanswerable] outcome=answer. What is the treasury's UNI balance today? 
- `q081` [unanswerable] outcome=answer. How much is the treasury's UNI-V3 token position worth in USD? 
