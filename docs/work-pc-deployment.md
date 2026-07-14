# work-pc Deployment Runbook — smart-trading-v2

How the **v2** stack is built, shipped, and run on **work-pc**. The model is
**build-on-dev-PC → push to Docker Hub → pull on work-pc** — work-pc never compiles
source, it only pulls prebuilt images.

> v2 runs **alongside** the older v1 stack on the same host. v1 owns ports
> `8000/3000/5173/5470`; v2 owns `8001/3001/5174/5471`. Don't confuse the two — a
> v2-only API route hit on `:3000` returns 404 because that's v1.
> For the abandoned Oracle Cloud path see [deployment_guide.md](deployment_guide.md).

---

## Topology at a glance

| Piece | Value |
|---|---|
| Host / SSH | `ssh work-pc` (user `work`) |
| Compose project dir | `/home/work/workspace/smart-trading-v2/infra` — **not a git repo**, pull-based |
| Compose file | [infra/docker-compose.yml](../infra/docker-compose.yml) (`name: smart-trading-v2`) |
| Secrets | `/home/work/workspace/smart-trading-v2/infra/.env` (gitignored, never committed) |
| Registry | Docker Hub `shivam13gupta/smart-trading-v2-{api,engine,frontend}:latest` |
| Public URL | `https://trading-v2.pseo.cloud` (HTTP Basic Auth gated) |

### Services (6 containers)

| Container | Image | Host port | Role |
|---|---|---|---|
| `smart-trading-v2-db` | `postgres:16-alpine` | `5471` → 5432 | Postgres (`trader`/`trader`/`smart_trading`), volume `postgres_data` |
| `smart-trading-v2-api` | `…/smart-trading-v2-api` | `3001` → 3000 | NestJS API + WebSocket + Telegram + per-cell fund bookkeeping |
| `smart-trading-v2-engine` | `…/smart-trading-v2-engine` | `8001` → 8000 | Python backtest / auto-select engine |
| `smart-trading-v2-scanner` | `…/smart-trading-v2-engine` (`python scanner/live_scanner.py`) | — | Live signal generator during NSE hours |
| `smart-trading-v2-scheduler` | `…/smart-trading-v2-engine` (`python scheduler/fetch_scheduler.py`) | — | Daily after-close yfinance data fetch (16:00 IST) + on-start backfill |
| `smart-trading-v2-frontend` | `…/smart-trading-v2-frontend` | `5174` → 5173 | nginx SPA; proxies `/api` + `/socket.io` to api, HTTP Basic Auth gate |

> **scanner + scheduler share the engine image** (different command). Rebuilding/pushing
> `engine` updates all three. There is **no `profiles:` gating** anymore — a plain
> `docker compose up -d` / `down` manages the whole 6-service stack.

---

## Standard deploy (code change → live)

### 1. On the **dev PC** — build & push image(s)

```bash
cd /home/shivam/workspace/smart-trading-v2
./infra/scripts/build-and-push.sh api          # or: engine | frontend | (none = all three)
```

- Builds `linux/amd64` (work-pc is x86_64) and pushes to Docker Hub.
- **Push account matters:** the script uses an isolated docker config
  `DOCKER_CFG=$HOME/.docker-account2` logged in as **shivam13gupta**. The default dev-PC
  login (`wisfluxp`) has **no push rights** and fails with `denied: requested access to
  the resource is denied`. One-time setup if missing:
  ```bash
  docker --config $HOME/.docker-account2 login -u shivam13gupta
  ```
- The `scanner` **and** `scheduler` share the **engine** image — rebuild/push `engine` to
  update both.

### 2. On **work-pc** — pull & restart

```bash
ssh work-pc
cd /home/work/workspace/smart-trading-v2/infra
./scripts/deploy.sh                 # = docker compose pull && docker compose up -d && ps
```

Or a single service: `docker compose pull api && docker compose up -d api`.
`pull_policy: always` means `up -d` re-pulls `:latest`. `deploy.sh` aborts if `.env` is missing.

### 3. Verify

```bash
docker compose ps                                          # all 6 Up (incl. scanner + scheduler)
docker exec smart-trading-v2-db psql -U trader -d smart_trading \
  -c 'SELECT MAX(timestamp) FROM "HistoricalData";'        # should be today
docker logs --since 2m smart-trading-v2-scanner | tail
```

- Scanner only acts during **NSE hours 09:15–15:30 IST**; a `heartbeat … Market is CLOSED`
  loop outside that is normal.
- Frontend reachable at `https://trading-v2.pseo.cloud` (basic-auth) or `http://<work-pc>:5174`.

---

## Secrets & configuration (`infra/.env`)

Copied from [infra/.env.example](../infra/.env.example); **never committed**. Compose reads
everything via `${VAR}` with safe defaults. After editing `.env`, apply with
`docker compose up -d <service>` (a plain `restart` does **not** reload `.env`).

- **Data source** — `DATA_SOURCE=yfinance` on this deploy, so scanner + scheduler pull candles
  from yfinance; the `DHAN_*`/`UPSTOX_*` vars are dormant (v2 is pure paper-trading).
- **Capital model** — strategy-testing lab: each (stock × strategy) cell owns its own
  ₹10k fund (`BASE_CELL_CAPITAL=10000`) that compounds with that cell's realized P&L.
  A trade deploys cellCapital × leverage of notional (intraday 5×, swing/delivery 1×).
  No funding gate — every selected-strategy signal is a real mock-money trade.
- **Telegram / LLM / CORS** — `TELEGRAM_*`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `CORS_ORIGINS`.

---

## Common operations

```bash
# Status / logs
ssh work-pc 'cd /home/work/workspace/smart-trading-v2/infra && docker compose ps'
ssh work-pc 'docker logs -f --since 1m smart-trading-v2-scanner'

# DB query (closed net P&L)
ssh work-pc 'docker exec smart-trading-v2-db psql -U trader -d smart_trading -c \
  "SELECT count(*), round(sum(pnl),2) FROM \"Trade\" WHERE status='"'"'CLOSED'"'"';"'

# Prune chronically-losing strategies from live scanning (review first — see the SQL header)
ssh work-pc 'docker exec -i smart-trading-v2-db psql -U trader -d smart_trading' \
  < infra/scripts/hygiene-prune-losers.sql
```

---

## One-time: deploying the strategy-testing-lab redesign

The per-cell ₹10k model, long-only-swing, dropped `fundingStatus`, and `Stock.sector`
ship together. Deploy order (after `build-and-push.sh` for all three images + `deploy.sh`):

```bash
# 1. Apply the new Prisma migrations (drop fundingStatus, add Stock.sector) inside the api container
ssh work-pc 'docker exec smart-trading-v2-api npx prisma migrate deploy'

# 2. Start clean — old trades used the old sizing/funding, so the per-cell leaderboard
#    is only meaningful from a fresh book. Wipes Trade+LiveSignal+ActiveConfiguration.
curl -X POST http://<work-pc>:3001/api/admin/reset -H "x-api-key: $API_KEY"

# 3. Repopulate ActiveConfiguration (now long-only) so the scanner has cells to trade
curl -X POST http://<work-pc>:8001/api/engine/auto-select -H "x-api-key: $API_KEY"

# 4. Backfill sector tags on the tradeable universe (fixes risk-engine "Unknown")
ssh work-pc 'docker exec smart-trading-v2-engine python populate_stock_sectors.py'
```

Then forward-test ~3 months and pick the top cell from the Portfolio → Leaderboard.

---

## Gotchas

- **502 Bad Gateway right after a deploy (login/`/api` fails, SPA loads).** `docker compose up -d`
  recreates the `api` container with a **new internal IP**; the frontend nginx used to `proxy_pass
  http://api:3000` and cached that IP **once at startup**, so it kept hitting the dead old IP →
  `connect() failed (111: Connection refused)` → 502 on every `/api` call incl. `/api/auth/login`
  (looks like "incorrect PIN"/won't log in). **Permanent fix applied 2026-07-14:** `infra/nginx/default.conf`
  now has `resolver 127.0.0.11 valid=10s ipv6=off;` + a variable in `proxy_pass`
  (`set $api_upstream api; proxy_pass http://$api_upstream:3000;`) so nginx re-resolves at request
  time. If you ever see this again (e.g. an old config): `docker exec smart-trading-v2-frontend nginx -s reload`.
  Diagnose via `docker logs --tail 30 smart-trading-v2-frontend | grep upstream`.
- **Wrong docker account on push** → `denied`. Always use `build-and-push.sh` (it sets
  `DOCKER_CFG=$HOME/.docker-account2`).
- **`.env` not reloaded on `restart`** — use `up -d <svc>` to pick up new env.
- **work-pc infra dir is not a git repo** — it's pull-only. Config/compose/SQL changes made
  on the dev PC must be copied over manually (they are **not** `git pull`-ed). To ship a new
  compose/nginx/SQL file:
  `scp infra/scripts/hygiene-prune-losers.sql work-pc:/home/work/workspace/smart-trading-v2/infra/scripts/`
- **scanner + scheduler = engine image** — updating the engine also updates both; all three
  need `up -d` to take a new image.
- **Historically:** scanner/scheduler used to be behind a `profiles: ["live"]` gate that made
  a plain `up -d` silently skip them (app looked live, took zero trades). That gate was
  **removed 2026-07-02** — no `--profile live` needed anymore.
