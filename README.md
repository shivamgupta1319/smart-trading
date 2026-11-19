# Smart Trading

A paper-trading lab for Indian stocks (NSE). It runs 28 trading strategies on 60 stocks
with pretend money, books every trade after real costs, and shows which
stock-and-strategy pairs keep earning. Real money is built in and switched off.

Live at **https://trading.pseo.cloud** (password, then PIN). One product, one branch
(`main`), one deployment.

## Where to start

| You want to | Read |
|---|---|
| Use the app and understand its numbers | [docs/user-guide.md](docs/user-guide.md) |
| Know what each strategy does and how it has done | [docs/strategies.md](docs/strategies.md) |
| See what is done and what is left | [docs/progress.md](docs/progress.md) |
| Deploy, check or operate it on work-pc | [docs/work-pc-deployment.md](docs/work-pc-deployment.md) |
| Understand how the code fits together | [docs/architecture.md](docs/architecture.md) |
| Turn on real money (off today) | [docs/real-money-trading.md](docs/real-money-trading.md), [docs/live-capabilities.md](docs/live-capabilities.md) |

## How it works, in short

- A **cell** is one stock with one strategy. Each cell has its own ₹10,000 of pretend
  money. Intraday trades may use 5 times that. No trade may risk more than 2% of what it
  may hold: ₹200 for swing, ₹1,000 for intraday.
- The **scanner** checks every cell during market hours, opens a paper trade when a
  strategy signals, and closes it at the stop, the target or 15:15.
- Every result is **after costs** (brokerage, taxes, slippage) and is measured in **R**:
  the profit or loss divided by the rupees the trade risked.
- Each cell has a **status** set from its own results: Testing, Proven or Paused. The
  Scorecard page shows it next to what the backtest promised.
- **Real money** needs two locks: the cell is Proven, and the owner switched it on. The
  whole layer is off (`DHAN_TRADING_MODE=off`).

## What is in the repo

```
apps/api        NestJS + Prisma: trades, sizing, costs, cell status, Telegram, real-money layer
apps/engine     Python + FastAPI: strategies, backtests, live scanner, data checks, scheduler
apps/frontend   React + Vite: the screens
config/         trading.json (capital, costs, status rules), known_price_actions.json
infra/          docker-compose.yml for work-pc, nginx, landing page, scripts
docs/           current docs; docs/archive/ holds history from the earlier apps
```

## Run it on your own machine

You need Docker, Node 20+ and Python 3.12.

```bash
cp .env.example .env            # fill in the values; never commit this file
docker compose up -d postgres
npm ci
npx prisma db push --schema=apps/api/prisma/schema.prisma
npx nx serve api                # http://localhost:3000
npx nx serve frontend           # http://localhost:5173
cd apps/engine && python -m venv venv && source venv/bin/activate \
  && pip install -r requirements.txt && uvicorn main:app --reload --port 8000
```

The scanner (`python scanner/live_scanner.py`) only opens trades in market hours,
09:30 to 15:00 IST on trading days.

## Tests

```bash
npx vitest run apps/api/src                      # API
npx nx build api --prod && npx nx build frontend # builds
# Engine tests run inside the engine image, from the repo root:
docker run --rm -v "$PWD:/repo" -w /repo/apps/engine shivam13gupta/smart-trading-engine:latest \
  sh -c "pip install -q pytest; python -m pytest test -q -p no:cacheprovider"
infra/scripts/e2e-smoke.sh                       # whole flow against a throwaway database
```

CI runs the engine tests, the API tests and both builds on every pull request.

## Working on it

Branch from `main`, open a pull request, wait for CI, merge, then build and deploy
(`infra/scripts/build-and-push.sh`, then the runbook). Update `docs/progress.md` and the
page that describes what you changed in the same pull request.

Secrets live only in `.env` files that git ignores. Do not put a key in a tracked file.
