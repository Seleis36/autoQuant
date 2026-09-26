"""fx-majors panel, cost model and a ticker-space backtest that matches the sim book.

Conventions (load-bearing):
  * Research signals live in CURRENCY space: a DataFrame with columns EUR GBP JPY AUD CAD
    CHF NZD, positive = long that currency / short USD.
  * The book trades the `=X` TICKERS. `to_tickers` flips the sign for USD-based quotes
    (USDJPY=X, USDCAD=X, USDCHF=X), and the backtest charges and earns on the tickers'
    own pct returns -- exactly what SimPortfolioBroker marks -- not on the inverted rate.
  * `=X` row D is the 00:00 UTC quote on D (covers UTC day D-1). A weight at row D is held
    from that close to the next row's close. Anything stamped on a US-session clock on D
    (equity closes, US yields, policy-rate changes announced during D) is NOT known at row
    D; use it from row D+1 (`lag_to_fx`).
  * Costs: per ticker, per side, in bp of traded notional, from `cost_table()` -- half the
    Dukascopy ask-bid gap at the 00:00 UTC print (the fill time), median by pair and year.
  * Carry is NOT accrued by the sim book. `carry_return` exists only to report what a
    real forward/swap book would have earned on top; deployable Sharpe is spot-only.
"""
import os
import sys

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
DATA = os.path.join(REPO, "data")
sys.path.insert(0, os.path.join(REPO, "code", "shared"))
from research_lib import load_series, perf_stats  # noqa: E402

CCYS = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
TICKER = {"EUR": ("EURUSD=X", 1), "GBP": ("GBPUSD=X", 1), "JPY": ("USDJPY=X", -1),
          "AUD": ("AUDUSD=X", 1), "CAD": ("USDCAD=X", -1), "CHF": ("USDCHF=X", -1),
          "NZD": ("NZDUSD=X", 1)}
TICKERS = [TICKER[c][0] for c in CCYS]
DUKA = {"EURUSD=X": "EURUSD", "GBPUSD=X": "GBPUSD", "USDJPY=X": "USDJPY", "AUDUSD=X": "AUDUSD",
        "USDCAD=X": "USDCAD", "USDCHF=X": "USDCHF", "NZDUSD=X": "NZDUSD"}
ANN = 252.0
IS_END, OOS_START = "2019-12-31", "2020-01-01"      # fixed before any result was seen


def load_px(start="2010-01-01"):
    """Closes of the seven =X tickers, rows where at least one quote moved."""
    px = pd.DataFrame({t: load_series(t)["Close"] for t in TICKERS}).sort_index()
    px = px.loc[start:].ffill()
    moved = px.pct_change().abs().sum(axis=1) > 0
    moved.iloc[0] = True
    return px[moved]


def usd_per_ccy(px):
    """Ticker closes -> USD per unit of each currency (positive return = ccy up)."""
    return pd.DataFrame({c: px[t] if s > 0 else 1.0 / px[t] for c, (t, s) in TICKER.items()})[CCYS]


def to_tickers(Wc):
    return pd.DataFrame({TICKER[c][0]: TICKER[c][1] * Wc[c] for c in CCYS})[TICKERS]


def lag_to_fx(series_or_frame, fx_index, lag=1):
    """Align a US-clock series (stamped by its own trading day) to =X rows so that row D
    only sees values stamped <= D - lag calendar days."""
    s = series_or_frame.copy()
    s.index = s.index + pd.Timedelta(days=lag)
    return s.reindex(s.index.union(fx_index)).ffill().reindex(fx_index)


def month_end_rows(idx):
    """Boolean Series: True on the last =X row of each calendar month."""
    s = pd.Series(idx, index=idx)
    return s.groupby(idx.to_period("M")).transform("max").eq(s)


def hold_monthly(sig, idx):
    """Sample a daily signal on month-end rows and hold it until the next month-end."""
    me = month_end_rows(idx).values
    s = sig.reindex(idx)
    return s[me].reindex(idx).ffill().fillna(0.0)


# ------------------------------------------------------------------ cost model

def cost_table(hour=23, refresh=False):
    """Per-ticker, per-year cost per side in bp = median half-spread at the close of the
    `hour` UTC candle (23 -> the quote standing at 00:00 UTC, the =X print). Built from
    data/<SYM>_duka_1h.parquet (fetch_duka_hourly.py)."""
    path = os.path.join(DATA, f"fx_halfspread_h{hour:02d}.parquet")
    if os.path.exists(path) and not refresh:
        return pd.read_parquet(path)
    rows, complete = {}, True
    for t, sym in DUKA.items():
        f = os.path.join(DATA, f"{sym}_duka_1h.parquet")
        if os.path.exists(f):
            h = pd.read_parquet(f)
        else:                       # crawl still running: use the raw month files so far
            complete = False
            h = _raw_hourly(sym)
        h = h[h.index.hour == hour]
        mid = (h["AskClose"] + h["BidClose"]) / 2
        hs = (h["AskClose"] - h["BidClose"]) / mid * 1e4 / 2
        rows[t] = hs.groupby(hs.index.year).median()
    tab = pd.DataFrame(rows)
    if complete:
        tab.to_parquet(path)
    return tab


def freeze_cost_table(hour=23, months=(1, 7)):
    """Build the cost table from the raw Dukascopy month files of the given calendar
    months only (a stratified sample: every pair, every year) and cache it, so research
    numbers do not drift while the full crawl is still filling in. Used for the 2026-09-26
    fx-majors cycle with months = January and July, 2010-2026."""
    rows = {}
    for t, sym in DUKA.items():
        h = _raw_hourly(sym, months)
        h = h[h.index.hour == hour]
        mid = (h["AskClose"] + h["BidClose"]) / 2
        hs = (h["AskClose"] - h["BidClose"]) / mid * 1e4 / 2
        rows[t] = hs.groupby(hs.index.year).median()
    tab = pd.DataFrame(rows)
    tab.to_parquet(os.path.join(DATA, f"fx_halfspread_h{hour:02d}.parquet"))
    return tab


def _raw_hourly(sym, months=None):
    import glob
    from fetch_duka_hourly import RAW, decode
    fr = []
    for f in sorted(glob.glob(os.path.join(RAW, f"{sym}_*_BID.bin"))):
        fa = f.replace("_BID.bin", "_ASK.bin")
        if not os.path.exists(fa):
            continue
        _, y, m, _ = os.path.basename(f).split("_")
        if months is not None and int(m) not in months:
            continue
        b = decode(open(f, "rb").read(), sym, int(y), int(m), "BID")
        a = decode(open(fa, "rb").read(), sym, int(y), int(m), "ASK")
        if len(b) and len(a):
            fr.append(b.join(a, how="inner"))
    h = pd.concat(fr).sort_index()
    return h[(h["BidVol"] + h["AskVol"]) > 0]


def cost_frame(index, hour=23, mult=1.0, floor=0.0):
    """Date x ticker cost per side (bp). Years outside the measured sample use the nearest
    measured year."""
    tab = cost_table(hour)
    yrs = pd.Index(index.year)
    tab = tab.reindex(range(min(yrs.min(), tab.index.min()), max(yrs.max(), tab.index.max()) + 1))
    tab = tab.ffill().bfill()
    out = pd.DataFrame(tab.loc[yrs].values, index=index, columns=tab.columns)
    return (out[TICKERS] * mult).clip(lower=floor)


# ------------------------------------------------------------------ backtest

def backtest(Wc, px, cost=None, name="strategy", carry=None):
    """Ticker-space backtest. Wc: currency-space target weights at row D (held D -> D+1).
    cost: None (measured table), a scalar bp per side, or a date x ticker frame.
    carry: optional date x ccy daily carry return (reported separately, never in `net`).
    Returns (net, gross, turnover, stats)."""
    Wt = to_tickers(Wc.reindex(px.index).fillna(0.0))
    ret = px.pct_change().fillna(0.0)
    w_eff = Wt.shift(1).fillna(0.0)
    gross = (w_eff * ret).sum(axis=1)
    dturn = (w_eff - w_eff.shift(1).fillna(0.0)).abs()
    if cost is None:
        cost = cost_frame(px.index)
    c = cost if np.isscalar(cost) else cost.reindex(index=px.index, columns=px.columns).ffill()
    tc = (dturn * c).sum(axis=1) / 1e4
    net = (gross - tc).rename(name)
    st = perf_stats(net, ann=ANN, name=name)
    st["Turnover_ann"] = dturn.sum(axis=1).sum() / (len(net) / ANN)
    st["AvgGross"] = w_eff.abs().sum(axis=1).mean()
    st["CostDrag_bp"] = tc.sum() / (len(net) / ANN) * 1e4
    if carry is not None:
        cr = (Wc.reindex(px.index).fillna(0.0).shift(1) * carry.reindex(px.index).fillna(0.0)).sum(axis=1)
        st["Sharpe_w_carry"] = perf_stats(net + cr, ann=ANN)["Sharpe"]
        st["Carry_ann"] = cr.mean() * ANN
    return net, gross, dturn.sum(axis=1), st


def carry_return(rates, idx, day_count=360.0):
    """Daily carry of long ccy / short USD using policy rates (percent), per =X row:
    (r_ccy - r_usd) * calendar days since previous row / 360. Reporting only."""
    r = rates.reindex(rates.index.union(idx)).ffill().reindex(idx)
    diff = r[CCYS].sub(r["USD"], axis=0) / 100.0
    days = pd.Series(idx, index=idx).diff().dt.days.fillna(1.0)
    return diff.mul(days / day_count, axis=0)


def split_table(net, name=None):
    rows = {"FULL": perf_stats(net, ann=ANN), "IS": perf_stats(net.loc[:IS_END], ann=ANN),
            "OOS": perf_stats(net.loc[OOS_START:], ann=ANN)}
    t = pd.DataFrame(rows).T[["Sharpe", "CAGR", "Vol", "MaxDD", "t_NW"]]
    if name:
        t.index = [f"{name}:{i}" for i in t.index]
    return t


def vol_scale(Wc, px, target=0.05, halflife=60, cap=3.0):
    """Scale a currency-space book to a target annual vol using the EWMA of the book's own
    past (unscaled) gross return. Uses only returns up to row D for the weight at D."""
    _, g, _, _ = backtest(Wc, px, cost=0.0)
    v = g.ewm(halflife=halflife, min_periods=40).std() * np.sqrt(ANN)
    k = (target / v).clip(upper=cap).fillna(0.0)
    return Wc.reindex(px.index).fillna(0.0).mul(k, axis=0)
