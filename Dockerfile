# Small image for the Telegram bot / CLI. The DuckDB store is rebuilt from the committed
# fixtures at build time, so the container needs no chain-data API keys.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY config ./config
COPY fixtures ./fixtures
RUN uv sync --frozen --no-dev \
    && uv run --no-sync dao-analyst ingest --mode replay

RUN useradd --create-home --uid 1000 analyst \
    && mkdir -p /app/logs \
    && chown -R analyst /app/logs /app/data
USER analyst

ENTRYPOINT ["uv", "run", "--no-sync", "dao-analyst"]
CMD ["bot"]
