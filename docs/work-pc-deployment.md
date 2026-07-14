# work-pc Deployment Runbook — smart-trading (v1)

How the v1 stack is built, shipped, and run on **work-pc**. This is the live,
real-money host. The model is **build-on-dev-PC → push to Docker Hub → pull on
work-pc** — work-pc never compiles source, it only pulls prebuilt images.

> For the abandoned Oracle Cloud path see [deployment_guide.md](deployment_guide.md)
> (superseded). For live-trading / Dhan specifics see
> [handoff.md](handoff.md) and [dhan-live-execution.md](dhan-live-execution.md).

---

## Topology at a glance

| Piece | Value |
|---|---|
| Host / SSH | `ssh work-pc` (user `work`) |
| Compose project dir | `/home/work/workspace/smart-trading/infra` — **not a git repo**, pull-based |
| Compose file | [infra/docker-compose.yml](../infra/docker-compose.yml) (`name: smart-trading`) |
| Secrets | `/home/work/workspace/smart-trading/infra/.env` (gitignored, never committed) |
| Registry | Docker Hub `shivam13gupta/smart-trading-{api,engine,frontend}:latest` |
| Public URL | `https://trading.pseo.cloud` (HTTP Basic Auth gated) |

### Services (5 containers)

| Container | Image | Host port | Role |
|---|---|---|---|
| `smart-trading-db` | `postgres:16-alpine` | `5470` → 5432 | Postgres (`trader`/`trader`/`smart_trading`), volume `postgres_data` |
| `smart-trading-api` | `…/smart-trading-api` | `3000` | NestJS API + WebSocket + **Dhan execution adapter** + Telegram digests |
| `smart-trading-engine` | `…/smart-trading-engine` | `8000` | Python backtest/analysis engine |
| `smart-trading-scanner` | `…/smart-trading-engine` (same image, `python scanner/live_scanner.py`) | — | Live signal generator during NSE hours |
| `smart-trading-frontend` | `…/smart-trading-frontend` | `5173` | nginx SPA; proxies `/api` + `/socket.io` to api, HTTP Basic Auth gate |

> Note: v1 has **no scheduler** service (that is the separate **v2** stack, which
> runs on ports 8001/3001 from `smart-trading-v2/infra`). Don't confuse the two.

---

## Standard deploy (code change → live)

### 1. On the **dev PC** — build & push image(s)

```bash
cd /home/shivam/workspace/smart-trading
./infra/scripts/build-and-push.sh api          # or: engine | frontend | (none = all three)
```

- Builds `linux/amd64` (work-pc is x86_64) and pushes to Docker Hub.
- **Push account matters:** the script uses an isolated docker config
  `DOCKER_CFG=$HOME/.docker-account2` logged in as **shivam13gupta**. The default
  login on the dev PC (`wisfluxp`) has **no push rights** to these repos and fails
  with `denied: requested access to the resource is denied`.
- One-time setup if that config is missing:
  ```bash
  docker --config $HOME/.docker-account2 login -u shivam13gupta
  ```
- The `scanner` shares the **engine** image — rebuild/push `engine` to update the scanner.

### 2. On **work-pc** — pull & restart

```bash
ssh work-pc
cd /home/work/workspace/smart-trading/infra
./scripts/deploy.sh                 # = docker compose pull && docker compose up -d && ps
```

Or target a single service:

```bash
docker compose pull api && docker compose up -d api
```

The compose file sets `pull_policy: always`, so `up -d` re-pulls `:latest`.
`deploy.sh` aborts if `infra/.env` is missing.

### 3. Verify

```bash
docker compose ps                                   # all 5 Up (incl. scanner)
docker logs --since 2m smart-trading-api | tail
```

- Scanner only acts during **NSE hours 09:15–15:30 IST**; outside that it idles.
- Frontend reachable at `https://trading.pseo.cloud` (basic-auth) or
  `http://<work-pc>:5173` on the LAN.

---

## Secrets & configuration (`infra/.env`)

Copied from [infra/.env.example](../infra/.env.example); **never committed**.
The compose file reads everything via `${VAR}` with safe defaults, so an unset
var degrades gracefully (e.g. `DHAN_TRADING_MODE` defaults to `off` = pure sim).

Key groups:

- **Telegram** — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (daily/weekly digests).
- **Engine LLM** — `OPENROUTER_API_KEY`, `GEMINI_API_KEY`.
- **CORS** — `CORS_ORIGINS` (defaults include `https://trading.pseo.cloud`).
- **Dhan real-money adapter** — see below.

After editing `.env`, apply with `docker compose up -d <service>` (recreates the
container with the new env). A plain `restart` does **not** reload `.env`.

---

## Dhan live-execution controls (api only)

Real-money order routing lives in the **api** container and is gated by env.

| Var | Meaning |
|---|---|
| `DHAN_TRADING_MODE` | `off` (sim) \| `log` \| `sandbox` \| `live` |
| `DHAN_CLIENT_ID` / `DHAN_PIN` / `DHAN_TOTP_SECRET` / `DHAN_ACCESS_TOKEN` | credentials (TOTP auto-mints a 24h token; manual token = fallback) |
| `DHAN_HTTP_PROXY` | **static-IP egress** — routes all Dhan calls through TrueIP.in IPv6 proxy so SEBI's static-IP mandate (`DH-905 Invalid IP`) is satisfied. Fails *safe* (no bypass if proxy down). |
| `DHAN_MAX_NOTIONAL` (base margin/trade) · `DHAN_INTRADAY_LEVERAGE` (MIS multiplier, e.g. 5) · `DHAN_MAX_RISK` (₹ risk cap = 2% of account) · `DHAN_MAX_QTY` · `DHAN_MAX_ORDERS_PER_DAY` · `DHAN_MAX_DAILY_LOSS` | sizing caps + kill-switch — see [real-money-trading.md](real-money-trading.md) for the live values and the add-a-pair runbook |

**Go live:** in `infra/.env` set `DHAN_TRADING_MODE=live` (+ desired caps), then
`docker compose up -d api`.

**Instant kill:** set `DHAN_TRADING_MODE=off` in `infra/.env`, then
`docker compose up -d api`. The −₹1,000/day loss kill-switch also auto-reverts to
`off` and pings Telegram.

> The static-IP requirement (SEBI, since 1 Apr 2026) is solved for free via a
> TrueIP dedicated static IPv6 proxy — details in [handoff.md](handoff.md).
> `setIP` **locks the IP for 7 days**, so never register a dynamic IP.

---

## Edge / public access

- The frontend nginx ([infra/nginx/default.conf](../infra/nginx/default.conf))
  listens on `5173`, serves the SPA, proxies `/api/` and `/socket.io/` to the api,
  and enforces **HTTP Basic Auth** via a shared `.htpasswd`
  (mounted from `${HTPASSWD_FILE:-../../edge/.htpasswd}`).
- Public HTTPS at `https://trading.pseo.cloud` is fronted separately (edge reverse
  proxy / DNS) — not part of this compose project.

---

## Common operations

```bash
# Status / logs
ssh work-pc 'cd /home/work/workspace/smart-trading/infra && docker compose ps'
ssh work-pc 'docker logs -f --since 1m smart-trading-scanner'

# DB query
ssh work-pc 'docker exec smart-trading-db psql -U trader -d smart_trading -c "SELECT MAX(\"createdAt\") FROM \"Signal\";"'

# Restart a service after an .env change
ssh work-pc 'cd /home/work/workspace/smart-trading/infra && docker compose up -d api'

# Watch for the first real Dhan order (market hours)
ssh work-pc 'timeout 21600 docker logs -f --since 1m smart-trading-api 2>&1 | grep -m1 -E "\[dhan:live\] (ENTRY|EXIT) (placed|FAILED)"'
```

---

## Gotchas

- **Wrong docker account on push** → `denied`. Always use `build-and-push.sh`
  (it sets `DOCKER_CFG=$HOME/.docker-account2`).
- **`.env` not reloaded on `restart`** — use `up -d <svc>` to pick up new env.
- **work-pc infra dir is not a git repo** — it's pull-only. Config/compose changes
  made on the dev PC must be copied over manually (they are not `git pull`-ed).
- **scanner = engine image** — updating the engine also updates the scanner; both
  need `up -d` to take a new image.
- **Scanner silence outside 09:15–15:30 IST is normal**, not a failure.
- **Sizing caps are independent of the sim** — the adapter computes its own capped
  qty regardless of `Trade.quantity`.
