"""SPDR bond ETF panel: official NAV, shares outstanding, market price.

NAV + shares : State Street publishes every fund's full daily history as
               https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/navhist-us-en-<ticker>.xlsx
               (Date, NAV, Shares Outstanding, Total Net Assets; no login). iShares' equivalent
               download now returns the product page instead of the file, so this family is
               the long free history of bond-ETF NAVs.
Prices       : yfinance, unadjusted close + Adj Close + volume.
Output       : data/SPDR_BOND_panel_d.parquet  [date, ticker, close, adj_close, volume, nav, shares, tna]

Timing trap  : the file dated T is posted after the close of T (the copy pulled on a Saturday
               morning ended on Thursday). nav[t] and shares[t] are not usable before close t+1.

The spreadsheets are third-party files: they are saved to a fresh temp directory and read with
the stdlib zip/XML parser below, never with a spreadsheet engine. Run with `python -I`.
"""
import os
import re
import sys
import tempfile
import time
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
import research_lib as rl  # noqa: E402

PANEL = os.path.join(rl.DATA_DIR, "SPDR_BOND_panel_d.parquet")
URL = "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/navhist-us-en-{}.xlsx"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36")

# SPDR fixed-income ETFs. sector: what the fund holds; hedge: the liquid ETFs its return is
# regressed on (IEF = rates, HYG = credit).
FUNDS = {
    "BIL": "tbill", "SPTS": "treasury", "SPTI": "treasury", "SPTL": "treasury", "SPIP": "tips",
    "TIPX": "tips", "SPAB": "aggregate", "SPMB": "mbs", "SPSB": "ig", "SPIB": "ig", "SPLB": "ig",
    "SPBO": "ig", "FLRN": "ig_float", "JNK": "hy", "SJNK": "hy", "SPHY": "hy", "SRLN": "loans",
    "CWB": "convert", "PSK": "preferred", "TFI": "muni", "SHM": "muni", "HYMB": "muni_hy",
    "BWX": "intl", "BWZ": "intl", "IBND": "intl", "WIP": "intl", "EBND": "em", "EMHC": "em",
    "TOTL": "active", "STOT": "active",
}
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _col(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(path):
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(NS + "si"):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
    rows = []
    for row in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter(NS + "row"):
        out = []
        for c in row.findall(NS + "c"):
            i = _col(c.get("r"))
            out.extend([""] * (i + 1 - len(out)))
            v = c.find(NS + "v")
            if v is None:
                continue
            out[i] = shared[int(v.text)] if c.get("t") == "s" else v.text
        rows.append(out)
    return rows


def fetch_nav(ticker, folder):
    path = os.path.join(folder, f"{ticker}.xlsx")
    req = urllib.request.Request(URL.format(ticker.lower()), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())
    rows = read_xlsx(path)
    hdr = next(i for i, r in enumerate(rows) if r and r[0] == "Date")
    recs = []
    for r in rows[hdr + 1:]:
        if len(r) < 3 or not re.match(r"\d{2}-[A-Za-z]{3}-\d{4}$", r[0] or ""):
            continue
        try:
            recs.append((pd.to_datetime(r[0], format="%d-%b-%Y"), float(r[1]), float(r[2]),
                         float(r[3]) if len(r) > 3 and r[3] else float("nan")))
        except ValueError:
            continue
    df = pd.DataFrame(recs, columns=["date", "nav", "shares", "tna"]).sort_values("date")
    df["ticker"] = ticker
    return df


def build():
    import yfinance as yf
    folder = tempfile.mkdtemp(prefix="spdr_nav_")
    navs = []
    for t in FUNDS:
        try:
            navs.append(fetch_nav(t, folder))
            print(t, len(navs[-1]), navs[-1]["date"].min().date(), navs[-1]["date"].max().date())
        except Exception as e:  # noqa: BLE001
            print(t, "FAILED", repr(e)[:80])
        time.sleep(0.5)
    nav = pd.concat(navs, ignore_index=True)
    tick = sorted(nav["ticker"].unique())
    d = yf.download(tick, start="2007-01-01", auto_adjust=False, progress=False, group_by="ticker", threads=True)
    px = []
    for t in tick:
        x = d[t].dropna(how="all")
        f = pd.DataFrame({"close": x["Close"], "adj_close": x["Adj Close"], "volume": x["Volume"]})
        f.index = pd.to_datetime(f.index).tz_localize(None)
        f["ticker"] = t
        px.append(f.rename_axis("date").reset_index())
    px = pd.concat(px, ignore_index=True)
    panel = px.merge(nav, on=["date", "ticker"], how="left")
    panel["sector"] = panel["ticker"].map(FUNDS)
    rl._atomic_parquet(panel, PANEL)
    return panel


if __name__ == "__main__":
    p = build()
    print(p.shape, p["ticker"].nunique(), p["date"].min().date(), p["date"].max().date())
    print("rows with NAV:", round(p["nav"].notna().mean(), 3))
