#!/usr/bin/env python3
"""Can this strategy's instruments actually be traded in the book it targets?

    python harness/check_symbols.py --book venue BTCUSDT ETHUSDT
    python harness/check_symbols.py --book sim   SPY XLK TLT EURUSD=X

Pass only the instruments the strategy actually TRADES.  Signal inputs that are
merely read do not need to be listed here -- they never reach a broker.

Exits non-zero if any instrument is untradable in that book, which is a hard blocker
for deployment rather than something to work around.

The two books answer to different rules, and asking the wrong one is how a perfectly
good equity strategy gets rejected for not being on a crypto exchange:

  venue -- Binance spot testnet.  Liquid crypto pairs only, long/flat, unlevered.
           Beware two traps, both reported as AMBIGUOUS and neither safe to accept:
           name collisions (several equity/ETF tickers are also unrelated crypto
           tokens) and vestigial tokenized-stock pairs (AAPLBUSDT, SPYBUSDT) that
           Binance delisted in production and that trade a few times a day here.
           They are not the equity, and a fill against one means nothing.

  sim   -- A self-contained simulated book priced from the shared `data/` cache.
           Anything the data vendor can price daily and deeply enough to backtest:
           equities, ETFs, FX, rates, commodity futures and crypto alike.  There is
           no order book, so the question is not "is it listed" but "is the series
           real, current and long enough to have meant something in the backtest".
"""
import argparse
import json
import os
import re
import sys
import urllib.request

BASE = "https://testnet.binance.vision"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Tickers whose crypto namesake on Binance is a completely different asset from
# the equity/ETF/FX/commodity instrument a research report would mean by them.
# This is a hazard of the VENUE book only: in the sim book `SPY` is priced from the
# equity series and there is no token to confuse it with.
COLLIDING = {
    "SPY", "QQQ", "IWM", "GLD", "SLV", "TLT", "HYG", "LQD", "USO", "GOLD", "OIL",
    "XLK", "XLE", "XLF", "XLV", "XLU", "XLP", "XLY", "XLI", "XLB", "XLRE", "XLC",
    "VIX", "UVXY", "SVXY", "VXX", "COIN", "MSTR", "GBTC", "NVDA", "TSLA", "AAPL",
    "MSFT", "AMZN", "META", "GOOG", "EUR", "JPY", "GBP", "AUD", "CHF", "CAD",
    "NZD", "SEK", "NOK", "DXY", "SPX", "NDX",
}

#: A simulated book still needs a series worth backtesting on, and one that has not
#: gone dark.  Both are advisory-to-blocking thresholds, not vendor limits.
MIN_SIM_BARS = 500          # ~2 years of trading days
STALE_SIM_DAYS = 10         # a live series prints more often than this, holidays included


def listed():
    info = json.load(urllib.request.urlopen(BASE + "/api/v3/exchangeInfo", timeout=25))
    return {s["symbol"] for s in info["symbols"] if s["status"] == "TRADING"}


def liquidity(symbol):
    """24h trade count on the venue -- a vestigial listing shows single digits."""
    try:
        t = json.load(urllib.request.urlopen(
            f"{BASE}/api/v3/ticker/24hr?symbol={symbol}", timeout=15))
        return int(t.get("count", 0))
    except Exception:  # noqa: BLE001
        return -1


def candidates(token: str):
    """Symbol spellings worth trying for a research ticker like 'BTC-USD'."""
    t = re.sub(r"[^A-Za-z0-9]", "", token).upper()
    t = re.sub(r"(USD|USDT|USDC|PERP)$", "", t) or t
    return [f"{t}USDT", f"{t}USDC", t]


def check_venue(tokens):
    """Binance spot testnet: is the pair listed, real, and unambiguous?"""
    avail = listed()
    bad = []
    for tok in tokens:
        root = re.sub(r"[^A-Za-z0-9]", "", tok).upper()
        root = re.sub(r"(USD|USDT|USDC|PERP)$", "", root) or root
        hit = next((c for c in candidates(tok) if c in avail), None)
        if hit and root in COLLIDING:
            bad.append(tok)
            print(f"AMBIGUOUS {tok:<14} -> {hit} exists, but it is a crypto token, "
                  f"NOT the {root} you mean. Treat as untradable.")
        elif hit:
            n = liquidity(hit)
            if 0 <= n < 500:
                bad.append(tok)
                print(f"AMBIGUOUS {tok:<14} -> {hit} lists, but only {n} trades in 24h. "
                      "Vestigial testnet listing, not a real market. Treat as untradable.")
            else:
                print(f"OK        {tok:<14} -> {hit} (spot, {n} trades/24h)")
        else:
            bad.append(tok)
            print(f"UNTRADED  {tok:<14} -> not listed on {BASE}")
    if bad:
        print(f"\nBLOCKER: {len(bad)} instrument(s) cannot be traded in the 'venue' book: "
              + ", ".join(sorted(set(bad))))
        print("That book is Binance spot testnet: liquid crypto pairs only. It has no "
              "ETFs, bonds, commodity futures or volatility products, and its "
              "tokenized-stock pairs are dead listings.")
        print("If the strategy does not need a real order book, deploy it to the 'sim' "
              "book instead: --book sim")
    return bad


def check_sim(tokens):
    """Simulated book: can the shared cache price this, deeply and recently enough?"""
    from datetime import datetime, timezone

    from live_lib import MarketData

    md = MarketData()
    bad = []
    for tok in tokens:
        try:
            df = md.daily(tok)
        except Exception as e:  # noqa: BLE001
            bad.append(tok)
            print(f"UNPRICED  {tok:<14} -> no daily series ({type(e).__name__}: {e})")
            continue
        if df.empty:
            bad.append(tok)
            print(f"UNPRICED  {tok:<14} -> the vendor returned an empty series")
            continue
        last = df.index[-1]
        age = (datetime.now(timezone.utc).replace(tzinfo=None) - last.to_pydatetime()).days
        if age > STALE_SIM_DAYS:
            bad.append(tok)
            print(f"STALE     {tok:<14} -> last bar {last.date()} is {age} days old. "
                  "Delisted, renamed, or the vendor has stopped covering it.")
        elif len(df) < MIN_SIM_BARS:
            bad.append(tok)
            print(f"THIN      {tok:<14} -> only {len(df)} bars ({df.index[0].date()} -> "
                  f"{last.date()}); needs {MIN_SIM_BARS} to have backtested honestly.")
        else:
            print(f"OK        {tok:<14} -> {len(df)} bars {df.index[0].date()} -> "
                  f"{last.date()}, last close {float(df['Close'].iloc[-1]):.4f}")
    if bad:
        print(f"\nBLOCKER: {len(bad)} instrument(s) cannot be traded in the 'sim' book: "
              + ", ".join(sorted(set(bad))))
        print("The sim book prices from the shared daily cache. An instrument it cannot "
              "price, or can only price thinly or stalely, is one the backtest could "
              "not have been honest about either.")
    return bad


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", choices=("venue", "sim"), default="venue",
                    help="which book the strategy will be deployed to (default: venue)")
    ap.add_argument("symbols", nargs="*", help="instruments the strategy TRADES")
    args = ap.parse_args(argv)
    if not args.symbols:
        ap.print_help()
        return 2
    bad = check_venue(args.symbols) if args.book == "venue" else check_sim(args.symbols)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
