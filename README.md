# DAO Treasury Analyst

An AI agent that answers questions about a DAO's on-chain treasury where every number is
computed by deterministic, tested code and every claim links to real transactions.

Work in progress. Phase 1 (data layer) is done:

```bash
make install
make ingest   # rebuilds data/treasury.duckdb from committed fixtures, offline, no keys
make check    # lint, types, tests
```

Default target: the Uniswap DAO treasury (Governance Timelock), Ethereum mainnet, full history
up to block 25,433,938 (2026-06-30 23:59:59 UTC). See `config/` for every address and label
with its source.
