# SmartTrader v2 — Isolated Development Environment

This branch (`roadmap-v2`) and its git worktree run **completely isolated** from your
live `smart-trading` stack so roadmap work never disturbs the running app or its data.

## Why a worktree?

The live stack live-mounts engine source (`./apps/engine:/app`), so editing engine code
in the original directory would affect the running engine/scanner. This worktree is a
separate checkout, so all edits here are invisible to the live stack.

| | Live stack | v2 (this worktree) |
|---|---|---|
| Directory | `/home/shivam/workspace/smart-trading` | `/home/shivam/workspace/smart-trading-v2` |
| Branch | `add-new-strategies-...` | `roadmap-v2` |
| Compose project | `smart-trading` | `smart-trading-v2` |
| Postgres | `smart-trading-db` @ host `5470` | `smart-trading-v2-db` @ host `5471` |
| API | `smart-trading-api` @ `3000` | `smart-trading-v2-api` @ `3001` |
| Engine | `smart-trading-engine` @ `8000` | `smart-trading-v2-engine` @ `8001` |
| Frontend | `smart-trading-frontend` @ `5173` | `smart-trading-v2-frontend` @ `5174` |
| DB volume | `smart-trading_postgres_data` | `smart-trading-v2_postgres_data` |

## The cloned database

The v2 Postgres volume was seeded with a full `pg_dump` of the live DB, verified to match
row-for-row (15 stocks, 83,053 candles, 9 trades, 9 signals, 955 backtest reports,
66 active configs, 2,364 NSE stocks). It is a point-in-time copy — changes here do **not**
flow back to the live DB.

To re-clone from live at any time:
```bash
docker exec smart-trading-db pg_dump -U trader -d smart_trading --clean --if-exists --no-owner --no-privileges \
  | docker exec -i smart-trading-v2-db psql -U trader -d smart_trading -q
```

## Running the v2 stack

```bash
cd /home/shivam/workspace/smart-trading-v2
docker compose up -d                      # db + api + engine + frontend (NOT the scanner)
docker compose --profile live up -d scanner   # opt-in: starts the live scanner
docker compose down                       # stop v2 only; live stack unaffected
```

- Secrets come from the gitignored root `.env` (template in `.env.example`).
- The `scanner` is gated behind the `live` profile and ships with `TELEGRAM_ENABLED=false`
  so you don't get duplicate alerts from two scanners.

## Promoting changes back

When the roadmap work is validated, merge `roadmap-v2` into your main line and rebuild the
live stack. Remove the worktree with `git worktree remove ../smart-trading-v2`.
