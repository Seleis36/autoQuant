"""Insider events for the S&P 500 panel.

    from events import load_events
    E = load_events()   # one row per (ticker, owner, filing_date, code): value, role, routine flag ...

* A Form 4 is public on its EDGAR filing date; the dataset carries no acceptance time and
  filings are accepted until 22:00 ET, so the event is tradeable at the close of the FIRST
  TRADING DAY AFTER `filing_date` (`entry`), and earns returns from the bar after that.
* Routine vs opportunistic (Cohen, Malloy & Pomorski 2012): an insider with trades (P or S, any
  panel issuer) in each of the three calendar years before the event year is ROUTINE if one
  calendar month hosts a trade in all three of those years, OPPORTUNISTIC otherwise; insiders
  with a shorter history are UNCLASSIFIED. Uses only trades filed before the event.
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from research_lib import DATA_DIR


def classify(tr):
    """tr: all P/S transactions. Returns Series (owner_cik, year) -> 'routine'/'opportunistic'/'unclassified'."""
    t = tr[["owner_cik", "trans_date"]].dropna().copy()
    t["y"] = t.trans_date.dt.year; t["m"] = t.trans_date.dt.month
    ym = t.drop_duplicates(["owner_cik", "y", "m"])
    years = ym.drop_duplicates(["owner_cik", "y"])[["owner_cik", "y"]]
    have = set(zip(years.owner_cik, years.y))
    months = set(zip(ym.owner_cik, ym.y, ym.m))
    out = {}
    for o, y in set(zip(t.owner_cik, t.y)):
        if all((o, y - k) in have for k in (1, 2, 3)):
            routine = any(all((o, y - k, m) in months for k in (1, 2, 3)) for m in range(1, 13))
            out[(o, y)] = "routine" if routine else "opportunistic"
        else:
            out[(o, y)] = "unclassified"
    return pd.Series(out)


def load_events(dates=None):
    tr = pd.read_parquet(os.path.join(DATA_DIR, "SP500_insider_trades.parquet"))
    tr = tr[tr.form.isin(["4", "4/A"])]
    tr = tr[(tr.shares > 0) & (tr.price > 0)]
    tr["val"] = tr.shares * tr.price
    cls = classify(tr)
    rel = tr.relationship.fillna("")
    tr["is_officer"] = rel.str.contains("Officer")
    tr["is_director"] = rel.str.contains("Director")
    tr["is_10pct_only"] = rel.str.contains("TenPercent") & ~tr.is_officer & ~tr.is_director
    title = tr.title.fillna("").str.upper()
    tr["is_ceo"] = title.str.contains("CEO|CHIEF EXECUTIVE")
    tr["is_cfo"] = title.str.contains("CFO|CHIEF FINANCIAL")
    g = tr.groupby(["ticker", "owner_cik", "filing_date", "code"])
    E = g.agg(val=("val", "sum"), shares=("shares", "sum"), price=("price", "mean"),
              shares_after=("shares_after", "last"), trans_date=("trans_date", "min"),
              is_officer=("is_officer", "max"), is_director=("is_director", "max"),
              is_10pct_only=("is_10pct_only", "min"), is_ceo=("is_ceo", "max"), is_cfo=("is_cfo", "max"),
              owner_name=("owner_name", "first")).reset_index()
    E["cls"] = [cls.get((o, y), "unclassified") for o, y in zip(E.owner_cik, E.trans_date.dt.year)]
    E["frac_holdings"] = E.shares / (E.shares_after.where(E.shares_after > 0))
    E = E[(E.filing_date - E.trans_date).dt.days.between(0, 60)]     # stale/late filings out
    if dates is not None:
        dates = pd.DatetimeIndex(dates)
        pos = dates.searchsorted(E.filing_date.values, side="right")  # first trading day > filing date
        E = E[pos < len(dates)].copy()
        E["entry"] = dates[pos[pos < len(dates)]]
    return E
