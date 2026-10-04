.PHONY: install ingest fetch test lint check questions eval eval-live

install:
	uv sync

# Rebuild the local store from committed fixtures. Offline, no API keys.
ingest:
	uv run dao-analyst ingest --mode replay

# Re-record fixtures from the live APIs (needs ETHERSCAN_API_KEY; ETH_RPC_URL optional).
fetch:
	uv run dao-analyst ingest --mode record

test:
	uv run pytest

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run mypy

check: lint test

# --- evaluation -------------------------------------------------------------------------
RUN ?= $(shell cat eval/runs/LATEST 2>/dev/null)

questions:
	uv run python eval/make_questions.py
	uv run python eval/ground_truth.py
	cd eval && uv run python make_heldout.py
	uv run python eval/ground_truth.py --questions eval/questions_heldout.jsonl \
		--out eval/ground_truth_heldout.json

# Offline: replays the recorded model responses of run $(RUN) and recomputes all metrics.
eval: ingest
	uv run dao-analyst eval --run-id $(RUN) --mode replay

# Live: calls the model (needs GEMINI_API_KEY or GROQ_API_KEY); resumable.
eval-live: ingest
	uv run dao-analyst eval --run-id $(RUN) --mode record
