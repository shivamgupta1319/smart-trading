#!/usr/bin/env bash
# End-to-end smoke of the API against a THROWAWAY Postgres (container st-e2e-db on
# port 5499, removed at the end). It never touches a real database.
#
#   npx nx build api --prod && infra/scripts/e2e-smoke.sh
#
# Checks: a trade one share cannot fit is rejected; a trade whose costs dwarf its
# risk is rejected; sizing of a normal trade; a cell is PAUSED after 20 losing
# trades and its next trade goes to the test book; the digest reports the two books
# apart and cannot be sent twice.
set -u
cd "$(dirname "$0")/../.."
export DATABASE_URL="postgresql://trader:trader@localhost:5499/smart_trading"
docker rm -f st-e2e-db >/dev/null 2>&1
docker run -d --name st-e2e-db -e POSTGRES_USER=trader -e POSTGRES_PASSWORD=trader -e POSTGRES_DB=smart_trading -p 5499:5432 postgres:16-alpine >/dev/null
for i in $(seq 1 30); do docker exec st-e2e-db pg_isready -U trader -q && break; sleep 1; done
npx prisma db push --schema=apps/api/prisma/schema.prisma --accept-data-loss 2>&1 | grep -E "in sync|Error|error" | head -3
API_KEY= APP_PIN= TELEGRAM_BOT_TOKEN= PORT=3099 TELEGRAM_ENABLED=false node apps/api/dist/main.js > /tmp/st-e2e-api.log 2>&1 &
API_PID=$!
for i in $(seq 1 30); do curl -sf localhost:3099/api/stocks >/dev/null && break; sleep 1; done
J='-H Content-Type:application/json'
SID=$(curl -s -X POST localhost:3099/api/stocks $J -d '{"symbol":"TESTCO"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
echo "stock id=$SID"
curl -s -X POST localhost:3099/api/configs/toggle $J -d '{"symbol":"TESTCO","strategyName":"RVOL_ORB","timeframe":"15m"}' | cut -c1-60; echo
echo "--- rejections"
curl -s -o /dev/null -w "unsizable (Rs 33,980 share, swing): HTTP %{http_code}\n" -X POST localhost:3099/api/signals/new $J -d "{\"stockId\":$SID,\"strategyName\":\"RVOL_ORB\",\"signalType\":\"BUY\",\"entryPrice\":33980,\"stopLoss\":32000,\"target\":40000,\"holdDuration\":\"SHORT_SWING\"}"
curl -s -X POST localhost:3099/api/signals/new $J -d "{\"stockId\":$SID,\"strategyName\":\"RVOL_ORB\",\"signalType\":\"BUY\",\"entryPrice\":817.5,\"stopLoss\":816.3,\"target\":820,\"holdDuration\":\"INTRADAY\"}" | cut -c1-200; echo
echo "--- 21 losing intraday trades (entry 100, stop 98, exit 98)"
for n in $(seq 1 21); do
  ID=$(curl -s -X POST localhost:3099/api/signals/new $J -d "{\"stockId\":$SID,\"strategyName\":\"RVOL_ORB\",\"signalType\":\"BUY\",\"entryPrice\":100,\"stopLoss\":98,\"target\":104,\"holdDuration\":\"INTRADAY\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("id"))')
  curl -s -o /dev/null -X PATCH localhost:3099/api/signals/$ID/close $J -d '{"exitPrice":98}'
  if [ "$n" = 19 ] || [ "$n" = 20 ] || [ "$n" = 21 ]; then
    curl -s localhost:3099/api/configs/scorecard | python3 -c "
import sys,json
c=json.load(sys.stdin)[0]; l=c['live']
print('after trade $n: status=%s | live trades=%d avgR=%.3f net=%.0f | main book %d trades, test book %d trades | reason=%s' % (c['status'], l['trades'], l['avgR'], l['netPnl'], c['mainBook']['trades'], c['testBook']['trades'], c['statusReason']))"
  fi
done
echo "--- digest preview (nothing is sent)"
curl -s "localhost:3099/api/reports/digest-preview?period=DAILY" | python3 -c "
import sys,json
d=json.load(sys.stdin); x=d['data']
print('main book %d trades %.0f | test book %d trades %.0f | status changes %d | cells %s' % (x['main']['trades'], x['main']['netPnl'], x['test']['trades'], x['test']['netPnl'], len(x['statusChanges']), x['cells']))
print(d['text'])"
docker exec st-e2e-db psql -U trader -d smart_trading -tA -c "INSERT INTO \"SentDigest\"(period,\"periodKey\") VALUES ('DAILY','2026-01-01')" >/dev/null
docker exec st-e2e-db psql -U trader -d smart_trading -tA -c "INSERT INTO \"SentDigest\"(period,\"periodKey\") VALUES ('DAILY','2026-01-01')" 2>&1 | grep -q "duplicate key" && echo "second copy of the same digest is refused by the database"
echo "--- market condition label"
ID=$(curl -s -X POST localhost:3099/api/signals/new $J -d "{\"stockId\":$SID,\"strategyName\":\"MACD_Zero\",\"signalType\":\"SELL\",\"entryPrice\":100,\"stopLoss\":102,\"target\":96,\"holdDuration\":\"INTRADAY\",\"marketRegime\":\"TRENDING_DOWN\",\"marketDirection\":\"DOWN\",\"marketBreadthPct\":22.5,\"alignedWithMarket\":true}" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("id"))')
docker exec st-e2e-db psql -U trader -d smart_trading -tA -c "SELECT \"regimeAtEntry\", \"marketDirectionAtEntry\", \"breadthAtEntry\", \"alignedWithMarket\" FROM \"Trade\" WHERE \"signalId\" = $ID"
curl -s -o /dev/null -w "a made-up market direction is refused: HTTP %{http_code}\n" -X POST localhost:3099/api/signals/new $J -d "{\"stockId\":$SID,\"strategyName\":\"Inside_Bar\",\"signalType\":\"BUY\",\"entryPrice\":100,\"stopLoss\":98,\"target\":104,\"holdDuration\":\"INTRADAY\",\"marketDirection\":\"SIDEWAYS\"}"
echo "--- first trade sizing"
docker exec st-e2e-db psql -U trader -d smart_trading -tA -c "SELECT quantity, \"capitalUsed\", \"riskAmount\", pnl, \"cellStatusAtEntry\" FROM \"Trade\" ORDER BY id LIMIT 1; SELECT \"cellStatusAtEntry\", COUNT(*) FROM \"Trade\" GROUP BY 1 ORDER BY 1;"
curl -s -X POST localhost:3099/api/configs/evaluate; echo
grep -E "Cell TESTCO|Signal rejected" /tmp/st-e2e-api.log | sed 's/\x1b\[[0-9;]*m//g' | cut -c40-230 | head -5
kill $API_PID 2>/dev/null; docker rm -f st-e2e-db >/dev/null 2>&1
