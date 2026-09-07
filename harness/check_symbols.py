#!/usr/bin/env python3
"""Can this strategy's instruments actually be traded on the paper venue?

    python harness/check_symbols.py BTCUSDT ETHUSDT SPY HYG

Pass only the instruments the strategy actually TRADES.  Signal inputs that are
merely read (HYG, ^GSPC, DX-Y.NYB, ...) do not need to be listed here -- they come
from yfinance and never touch the venue.

Prints one line per instrument saying whether the Binance spot testnet lists it,
and suggests the spot symbol for a research ticker (BTC/USD -> BTCUSDT).
Exits non-zero if any instrument is untradable -- which is a hard blocker for
deployment, not something to work around.

Beware two traps, both reported as AMBIGUOUS and neither safe to accept:
  * name collisions -- several equity/ETF tickers are also unrelated crypto tokens;
  * vestigial tokenized-stock pairs (AAPLBUSDT, SPYBUSDT, ...) that Binance delisted
    in production and that trade a few times a day on testnet. They are not the
    equity, and a fill there means nothing.
"""
import json
import re
import sys
import urllib.request

BASE = "https://testnet.binance.vision"

# Tickers whose crypto namesake on Binance is a completely different asset from
# the equity/ETF/FX/commodity instrument a research report would mean by them.
COLLIDING = {
    "SPY", "QQQ", "IWM", "GLD", "SLV", "TLT", "HYG", "LQD", "USO", "GOLD", "OIL",
    "XLK", "XLE", "XLF", "XLV", "XLU", "XLP", "XLY", "XLI", "XLB", "XLRE", "XLC",
    "VIX", "UVXY", "SVXY", "VXX", "COIN", "MSTR", "GBTC", "NVDA", "TSLA", "AAPL",
    "MSFT", "AMZN", "META", "GOOG", "EUR", "JPY", "GBP", "AUD", "CHF", "CAD",
    "NZD", "SEK", "NOK", "DXY", "SPX", "NDX",
}


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


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    avail = listed()
    bad, ambiguous = [], []
    for tok in argv:
        root = re.sub(r"[^A-Za-z0-9]", "", tok).upper()
        root = re.sub(r"(USD|USDT|USDC|PERP)$", "", root) or root
        hit = next((c for c in candidates(tok) if c in avail), None)
        if hit and root in COLLIDING:
            ambiguous.append(tok)
            print(f"AMBIGUOUS {tok:<14} -> {hit} exists, but it is a crypto token, "
                  f"NOT the {root} you mean. Treat as untradable.")
        elif hit:
            n = liquidity(hit)
            if 0 <= n < 500:
                ambiguous.append(tok)
                print(f"AMBIGUOUS {tok:<14} -> {hit} lists, but only {n} trades in 24h. "
                      "Vestigial testnet listing, not a real market. Treat as untradable.")
            else:
                print(f"OK        {tok:<14} -> {hit} (spot, {n} trades/24h)")
        else:
            bad.append(tok)
            print(f"UNTRADED  {tok:<14} -> not listed on {BASE}")
    bad += ambiguous
    if bad:
        print(f"\nBLOCKER: {len(bad)} instrument(s) cannot be traded on the paper venue: "
              + ", ".join(sorted(set(bad))))
        print("The venue is Binance spot testnet: liquid crypto pairs only. It has no "
              "ETFs, bonds, commodity futures or volatility products, and its "
              "tokenized-stock pairs are dead listings.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
