# Deploying the Telegram bot on a small VPS

Any 1 vCPU / 1 GB VPS with Docker is enough: the data store is a few MB and all model
inference happens at the LLM provider.

1. Install Docker and the compose plugin (Ubuntu: `apt install docker.io docker-compose-v2`).
2. Clone the repo and create the environment file:

   ```bash
   git clone https://github.com/mhsh77/dao-treasury-analyst.git
   cd dao-treasury-analyst
   cp .env.example .env
   ```

3. Fill in `.env`:
   - `TELEGRAM_BOT_TOKEN`: from [@BotFather](https://t.me/BotFather) (`/newbot`).
   - `LLM_PROVIDER`, `LLM_MODEL` and the matching key (`GEMINI_API_KEY` or `GROQ_API_KEY`).
   - Optional: `TELEGRAM_ALLOWED_USERS=123,456` to make the bot private, and
     `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_S` (default 5 questions per 10 minutes per
     user).

4. Build and start:

   ```bash
   docker compose up -d --build
   docker compose logs -f bot
   ```

The image rebuilds the DuckDB store from the committed fixtures at build time, so it needs
no Etherscan or RPC key. Structured JSON logs go to stdout; the per-question audit trail
(tool calls, result hashes, verification outcomes, latency) is written to `./logs/audit.jsonl`.

To update: `git pull && docker compose up -d --build`.

Free-tier note: the Gemini free tier limits requests per model per day. For a public bot,
use a paid key or keep `TELEGRAM_ALLOWED_USERS` set.
