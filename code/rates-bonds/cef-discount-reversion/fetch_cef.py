"""Bond closed-end fund panel: market price, published NAV, volume.

Universe  : CEFConnect `api/v3/DailyPricing` (every US-listed CEF alive today, with its
            Morningstar category and NAV ticker). Snapshot kept next to this file as
            `cef_universe.csv` so the backtest universe is reproducible.
Prices    : yfinance, UNADJUSTED close + Adj Close + volume, 2000+.
NAV       : yfinance NAV ticker (`X<TICKER>X`, e.g. NAD -> XNADX), close = NAV per share.

Output    : data/CEF_BOND_panel_d.parquet, long format
            [date, ticker, open, high, low, close, adj_close, volume, nav]
            (open/high/low/close are unadjusted)

Traps
  * Survivors only. yfinance and CEFConnect carry no merged / liquidated funds, so the panel
    is the set of funds alive on the snapshot date. Stated in the report; not fixable here.
  * NAV is struck at the close and published in the evening (CEFConnect shows NAVPublished
    one session behind the price). Anything that uses nav[t] must not trade before t+1.
  * The discount needs the UNADJUSTED close: Adj Close is total-return, the NAV is not, so
    Adj Close / NAV steps up by the distribution on every ex-date.
"""
import json
import os
import sys
import time
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
import research_lib as rl  # noqa: E402

UNIVERSE_CSV = os.path.join(HERE, "cef_universe.csv")
PANEL = os.path.join(rl.DATA_DIR, "CEF_BOND_panel_d.parquet")
API = "https://www.cefconnect.com/api/v3/DailyPricing"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36")

# Fixed-income categories, fixed before any return was looked at. Preferreds and convertibles
# are left out as equity hybrids.
MUNI = ["Municipal", "Municipal-Single State", "Municipal-CA", "Municipal-NY"]
TAXABLE = ["High Yield", "Senior Loans", "Investment Grade", "Multi-Sector", "Global Income",
           "Limited Duration", "Emerging Market Income", "Taxable Muni"]
PREFIX = "Morningstar US CEF "


def fetch_universe():
    req = urllib.request.Request(API, headers={"User-Agent": UA, "Accept": "application/json"})
    rows = json.loads(urllib.request.urlopen(req, timeout=60).read())
    df = pd.DataFrame(rows)
    df["category"] = df["CategoryName"].str.replace(PREFIX, "", regex=False)
    df = df[df["category"].isin(MUNI + TAXABLE)].copy()
    df["group"] = df["category"].map(lambda c: "muni" if c in MUNI else "taxable")
    keep = {"Ticker": "ticker", "NavTicker": "nav_ticker", "Name": "name", "category": "category",
            "group": "group", "SponsorName": "sponsor", "InceptionDateString": "inception",
            "MarketCapUSDm": "mcap_musd", "AvgDailyVolume": "adv_shares", "Price": "price",
            "IsLeveraged": "leveraged", "Term": "term"}
    df = df[list(keep)].rename(columns=keep).sort_values("ticker").reset_index(drop=True)
    df.to_csv(UNIVERSE_CSV, index=False)
    return df


def _download(tickers, start):
    import yfinance as yf
    out = {}
    for i in range(0, len(tickers), 40):
        chunk = tickers[i:i + 40]
        for attempt in range(3):
            try:
                d = yf.download(chunk, start=start, auto_adjust=False, progress=False,
                                group_by="ticker", threads=True)
                break
            except Exception as e:  # noqa: BLE001
                print("retry", i, repr(e)[:80])
                time.sleep(5)
        for t in chunk:
            try:
                x = d[t].dropna(how="all")
            except KeyError:
                continue
            if len(x):
                out[t] = x
        time.sleep(1)
    return out


def build_panel(start="2000-01-01"):
    uni = pd.read_csv(UNIVERSE_CSV) if os.path.exists(UNIVERSE_CSV) else fetch_universe()
    px = _download(uni["ticker"].tolist(), start)
    nav = _download(uni["nav_ticker"].dropna().tolist(), start)
    frames = []
    for _, u in uni.iterrows():
        t, n = u["ticker"], u["nav_ticker"]
        if t not in px or n not in nav:
            continue
        p = px[t]
        f = pd.DataFrame({"open": p["Open"], "high": p["High"], "low": p["Low"], "close": p["Close"],
                          "adj_close": p["Adj Close"], "volume": p["Volume"]})
        f["nav"] = nav[n]["Close"].reindex(f.index)
        f["ticker"] = t
        f.index = pd.to_datetime(f.index).tz_localize(None)
        frames.append(f.rename_axis("date").reset_index())
    panel = pd.concat(frames, ignore_index=True)
    rl._atomic_parquet(panel, PANEL)
    return panel


if __name__ == "__main__":
    if "--universe" in sys.argv or not os.path.exists(UNIVERSE_CSV):
        u = fetch_universe()
        print(u.groupby(["group", "category"]).size())
    p = build_panel()
    print(p.shape, p["ticker"].nunique(), p["date"].min(), p["date"].max())
    print("rows with NAV:", p["nav"].notna().mean().round(3))
