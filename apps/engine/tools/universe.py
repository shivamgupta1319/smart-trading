"""Manage the stock lists (see universe.py). Run inside the engine container, from /app.

  python tools/universe.py add --csv config/universe/nifty500-2026-11-23.csv
        Add the symbols of an NSE index file that are not in the Stock table yet
        (daily candles only; sector taken from the file's Industry column).
  python tools/universe.py fetch-daily
        Download daily history for every active stock that has none. Slow and polite.
  python tools/universe.py measure
        Work out value traded per day and daily range for every active stock and store them.
  python tools/universe.py floor --min-cr 20 [--apply]
        Switch off stocks that trade less than the floor (never one with a cell on the roster).
  python tools/universe.py intraday --top 30 --min-cr 100 --min-price 50 --max-price 5000 [--apply]
        Choose the intraday list by measurement. A stock with an intraday cell on the
        roster always stays on it.

Without --apply, `floor` and `intraday` only print what they would do.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.client import engine  # noqa: E402
from luck_check import load_candles  # noqa: E402
import universe  # noqa: E402


def cmd_add(args) -> int:
    with open(args.csv, newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("Series") or "EQ").strip() == "EQ"]
    added = 0
    with engine.begin() as conn:
        have = {r[0] for r in conn.execute(text('SELECT symbol FROM "Stock"')).fetchall()}
        for r in rows:
            symbol = r["Symbol"].strip().upper()
            if not symbol or symbol in have:
                continue
            conn.execute(text(
                'INSERT INTO "Stock" (symbol, "isActive", sector, intraday, "createdAt") '
                'VALUES (:s, true, :sec, false, now())'
            ), {"s": symbol, "sec": (r.get("Industry") or "").strip() or None})
            added += 1
    print(f"{len(rows)} symbols in the file, {added} added, {len(rows) - added} already present")
    return 0


def cmd_fetch_daily(args) -> int:
    from routers.history import fetch_and_store

    with engine.connect() as conn:
        todo = [r[0] for r in conn.execute(text(
            'SELECT s.symbol FROM "Stock" s WHERE s."isActive" AND NOT EXISTS '
            '(SELECT 1 FROM "HistoricalData" h WHERE h."stockId" = s.id AND h.timeframe = \'1D\') ORDER BY 1'
        )).fetchall()]
    print(f"{len(todo)} stocks have no daily history", flush=True)
    ok = empty = failed = 0
    for n, symbol in enumerate(todo, 1):
        try:
            res = fetch_and_store(symbol, ["1D"])
            rows = (res.get("results") or {}).get("1D", {}).get("rows", 0)
            if rows:
                ok += 1
            else:
                empty += 1
                print(f"   no data: {symbol} {res.get('error') or (res.get('results') or {}).get('1D')}", flush=True)
        except Exception as exc:
            failed += 1
            print(f"   failed: {symbol} {type(exc).__name__}: {exc}"[:160], flush=True)
        if n % 25 == 0:
            print(f"[{n}/{len(todo)}] {ok} fetched, {empty} empty, {failed} failed", flush=True)
        time.sleep(args.pause)
    print(f"done: {ok} fetched, {empty} empty, {failed} failed")
    return 0


def _measured(conn) -> list[dict]:
    out = []
    for stock_id, symbol, on_list in universe.active_stocks(conn):
        fig = universe.figures(load_candles(conn, stock_id, "1D"))
        out.append({"id": stock_id, "symbol": symbol, "intraday": on_list, **(fig or {
            "traded_value_cr": None, "day_range_pct": None, "last_close": None})})
    return out


def cmd_measure(args) -> int:
    with engine.begin() as conn:
        rows = _measured(conn)
        for r in rows:
            conn.execute(text(
                'UPDATE "Stock" SET "tradedValueCr" = :v, "dayRangePct" = :d, "lastClose" = :c WHERE id = :id'
            ), {"v": r["traded_value_cr"], "d": r["day_range_pct"], "c": r["last_close"], "id": r["id"]})
    known = [r for r in rows if r["traded_value_cr"] is not None]
    print(f"{len(rows)} active stocks, {len(known)} measured, {len(rows) - len(known)} with too little daily history")
    return 0


def _stored(conn) -> list[dict]:
    rows = conn.execute(text(
        'SELECT id, symbol, intraday, "tradedValueCr", "dayRangePct", "lastClose" FROM "Stock" WHERE "isActive" ORDER BY symbol'
    )).fetchall()
    return [{"id": r[0], "symbol": r[1], "intraday": bool(r[2]), "traded_value_cr": r[3],
             "day_range_pct": r[4], "last_close": r[5]} for r in rows]


def _roster(conn, intraday_only: bool) -> set[str]:
    where = "WHERE ac.timeframe <> '1D'" if intraday_only else ""
    return {r[0] for r in conn.execute(text(
        f'SELECT DISTINCT s.symbol FROM "ActiveConfiguration" ac JOIN "Stock" s ON s.id = ac."stockId" {where}'
    )).fetchall()}


def cmd_floor(args) -> int:
    with engine.begin() as conn:
        rows, keep = _stored(conn), _roster(conn, intraday_only=False)
        drop = [r for r in rows if r["symbol"] not in keep
                and (r["traded_value_cr"] is None or r["traded_value_cr"] < args.min_cr)]
        unmeasured = sum(1 for r in drop if r["traded_value_cr"] is None)
        print(f"{len(rows)} active stocks; {len(drop)} under Rs {args.min_cr:g} crore a day "
              f"({unmeasured} of them have no usable daily history); {len(rows) - len(drop)} stay")
        print("   switched off:", ", ".join(r["symbol"] for r in drop) or "none")
        if args.apply:
            for r in drop:
                conn.execute(text('UPDATE "Stock" SET "isActive" = false, intraday = false WHERE id = :id'), {"id": r["id"]})
            print("applied")
    return 0


def cmd_intraday(args) -> int:
    with engine.begin() as conn:
        rows, must = _stored(conn), _roster(conn, intraday_only=True)
        chosen = universe.pick_intraday(rows, args.top, args.min_cr, args.min_price, args.max_price)
        names = {r["symbol"] for r in chosen}
        final = names | must
        print(f"{'stock':12} {'range %':>8} {'Rs cr/day':>10} {'price':>9}")
        for r in chosen:
            print(f"{r['symbol']:12} {r['day_range_pct']:8.2f} {r['traded_value_cr']:10.0f} {r['last_close']:9.2f}")
        print(f"kept because they have an intraday cell on the roster: {', '.join(sorted(must - names)) or 'none'}")
        now_on = {r["symbol"] for r in rows if r["intraday"]}
        print(f"joining the list: {', '.join(sorted(final - now_on)) or 'none'}")
        print(f"leaving the list: {', '.join(sorted(now_on - final)) or 'none'}")
        if args.apply:
            for r in rows:
                conn.execute(text('UPDATE "Stock" SET intraday = :on WHERE id = :id'), {"on": r["symbol"] in final, "id": r["id"]})
            print(f"applied: {len(final)} stocks on the intraday list")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("--csv", required=True); a.set_defaults(fn=cmd_add)
    f = sub.add_parser("fetch-daily"); f.add_argument("--pause", type=float, default=0.6); f.set_defaults(fn=cmd_fetch_daily)
    sub.add_parser("measure").set_defaults(fn=cmd_measure)
    fl = sub.add_parser("floor"); fl.add_argument("--min-cr", type=float, required=True); fl.add_argument("--apply", action="store_true"); fl.set_defaults(fn=cmd_floor)
    i = sub.add_parser("intraday")
    i.add_argument("--top", type=int, default=30); i.add_argument("--min-cr", type=float, default=100)
    i.add_argument("--min-price", type=float, default=50); i.add_argument("--max-price", type=float, default=5000)
    i.add_argument("--apply", action="store_true"); i.set_defaults(fn=cmd_intraday)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
