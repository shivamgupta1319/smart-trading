# Deployment runbook (work-pc)

Smart Trading runs as one Docker Compose stack on work-pc and is served at
**https://trading.pseo.cloud**. This page is how to deploy, check and operate it.

Since 2026-11-19 there is one product and one stack. The two earlier stacks were stopped
that day; their files are in `infra/_archive-before-merge-20261119/` on work-pc.

## Layout

| | |
|---|---|
| Host | `work-pc` (`ssh work-pc`), user `work` |
| Stack folder | `/home/work/workspace/smart-trading/infra` (not a git checkout: files are copied in) |
| Compose project | `smart-trading` |
| Images | `shivam13gupta/smart-trading-{api,engine,frontend}:latest` on Docker Hub |
| Database volume | `smart-trading_pgdata_final` |
| Public address | `trading.pseo.cloud` → Cloudflare tunnel → host port 5173 |

| Container | What it does | Host port |
|---|---|---|
| `smart-trading-db` | Postgres 16 | 5470 |
| `smart-trading-api` | NestJS API, trade booking, Telegram alerts | 3000 |
| `smart-trading-engine` | Python engine: backtests, live prices | 8000 |
| `smart-trading-frontend` | nginx: landing page, password gate, the app, proxy to the API | 5173 |
| `smart-trading-scanner` | Scans the roster during market hours, opens and closes paper trades | none |
| `smart-trading-scheduler` | Fetches price history at start-up and daily at 16:00 IST | none |

The scanner and scheduler run the engine image with a different command, so pushing the
engine image updates all three.

The page at `/` is public (the landing page in `infra/landing`). Everything else is behind
HTTP Basic Auth (`.htpasswd` shared from `/home/work/workspace/edge/`), then the app's own PIN.

## Deploy a code change

1. **Dev PC, from `main`:** build and push the images.

   ```bash
   infra/scripts/build-and-push.sh              # all three
   infra/scripts/build-and-push.sh engine       # or just one: api | engine | frontend
   ```

   It needs the Docker Hub login in `~/.docker-account2` (the script says how if it is missing).

2. **If `infra/docker-compose.yml`, `infra/nginx/` or `infra/landing/` changed,** copy them over:

   ```bash
   scp infra/docker-compose.yml work-pc:/home/work/workspace/smart-trading/infra/
   scp infra/nginx/default.conf work-pc:/home/work/workspace/smart-trading/infra/nginx/
   ```

3. **work-pc:** pull and restart.

   ```bash
   ssh work-pc 'cd /home/work/workspace/smart-trading/infra && ./scripts/deploy.sh'
   ```

4. **Check it** (next section).

A database change is applied by hand with `psql` before the restart. Each file under
`apps/api/prisma/migrations/` is written to be safe to run twice.

## Check that it is healthy

```bash
ssh work-pc
cd /home/work/workspace/smart-trading/infra
docker compose ps                                   # six containers, all Up
docker logs --tail 30 smart-trading-scanner         # "Done in NNs (387 configs)"; no STALL lines
docker logs --tail 30 smart-trading-api
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5173/            # 200  landing page
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5173/dashboard   # 401  password gate
```

Things worth knowing when reading the logs:

- `Signal rejected: ... costs would be NN% of the risk` is the cost rule working, not a fault.
- `CANNOT EVALUATE <stock> (<strategy>)` means a strategy had too little data. Check the
  scheduler fetched history for that stock.
- `STALL: cycle took NNs` means a scan took longer than 100 seconds. Open trades are only
  checked once per cycle, so a long cycle delays exits.
- The scanner only works 09:15–15:30 IST on weekdays. Outside that it prints
  `Market is CLOSED`.

## Settings (`infra/.env` on work-pc)

Secrets live only in this file. Do not commit it or paste it anywhere.

| Setting | Purpose |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL` | Database |
| `API_KEY`, `APP_PIN` | API key the browser gets after entering the PIN |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_ENABLED` | Alerts |
| `DB_PORT`, `API_PORT`, `ENGINE_PORT`, `FRONTEND_PORT` | Host ports (5470, 3000, 8000, 5173) |
| `DATA_SOURCE`, `BROKER`, `DHAN_*`, `UPSTOX_*` | Where prices come from (`yfinance` today) |
| `FETCH_*` | When the scheduler fetches history |

Trading rules are **not** in `.env`. Fund size, leverage, the risk cap, costs, the cost rule
and the pause rules are in `config/trading.json` in the repo and ship inside the images.

To send a test Telegram message without printing the key:

```bash
docker exec smart-trading-api node -e 'fetch("https://api.telegram.org/bot"+process.env.TELEGRAM_BOT_TOKEN+"/sendMessage",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({chat_id:process.env.TELEGRAM_CHAT_ID,text:"test"})}).then(r=>r.json()).then(j=>console.log(j.ok,j.description||""))'
```

## Database

```bash
# open a SQL prompt (credentials come from the container, nothing to type)
docker exec -it smart-trading-db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

# back up
docker exec smart-trading-db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > ~/backups/smart_trading-$(date +%Y%m%d).sql.gz
```

Read-only analysis queries are in `infra/scripts/analysis/`.

### Starting from an empty database

This is what was done on 2026-11-19.

```bash
cd /home/work/workspace/smart-trading/infra
docker compose up -d postgres
docker exec -i smart-trading-db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < scripts/init-fresh-db.sql
# stock list and price history go in here (copied from the previous database that day;
# on a truly empty system add stocks in the app and let the scheduler fetch)
docker exec -i smart-trading-db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < scripts/seed-starting-roster.sql
docker compose up -d
```

`seed-starting-roster.sql` puts every strategy on a fixed stock list: the 11 intraday
strategies on 12 volatile stocks and the 17 swing strategies on 15 large stocks, 387 cells.
Cells are added or removed in the app after that.

## Roll back

The images that were running before the merge are tagged on work-pc as
`shivam13gupta/smart-trading-*:pre-merge-v1` and `shivam13gupta/smart-trading-v2-*:pre-merge-v2`,
the old compose files and settings are in `infra/_archive-before-merge-20261119/`, and the old
database volumes (`smart-trading_postgres_data`, `smart-trading-v2_postgres_data`) are still on
the host. Database dumps from that morning are in `~/backups/`.

## Gotchas

- **502 on every API call after a restart.** nginx used to keep the API container's old
  address. `infra/nginx/default.conf` now re-resolves it on each request; if it ever returns,
  `docker restart smart-trading-frontend` clears it.
- **The API limits each client to 240 requests a minute.** Scripts that hammer it get 429.
- **`RISK_PER_TRADE_PCT` is a fraction** (0.02 means 2%). A value like `2` stops the API and
  engine at start-up on purpose, because it would switch the risk cap off.
- **Old roster rows naming a retired strategy** are skipped by the scanner with
  `Unknown strategy`.
