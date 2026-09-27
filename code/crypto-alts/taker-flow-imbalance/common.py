"""taker-flow-imbalance: Binance spot taker-buy share as a cross-sectional alt signal."""
import os, sys
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
import research_lib as rl  # noqa
import study as S  # noqa
import venues as V  # noqa


def load_flow(tickers):
    """Wide Binance frames aligned on the yfinance calendar: QuoteVolume, TakerBuyQuote,
    Trades, Close (USDT)."""
    f = {k: V.panel(V.binance_daily, tickers, k) for k in ("QuoteVolume", "TakerBuyQuote", "Trades", "Close")}
    return f


def ic_table(sig, fwd, mask, min_n=8):
    """Mean daily Spearman IC and its t-stat (NW on the daily IC series) per split."""
    s = sig.where(mask)
    ok = s.notna() & fwd.notna()
    n = ok.sum(axis=1)
    rs = s.where(ok).rank(axis=1)
    rf = fwd.where(ok).rank(axis=1)
    rs = rs.sub(rs.mean(axis=1), axis=0); rf = rf.sub(rf.mean(axis=1), axis=0)
    ic = (rs * rf).sum(axis=1) / np.sqrt((rs ** 2).sum(axis=1) * (rf ** 2).sum(axis=1))
    ic = ic.where(n >= min_n).dropna()
    out = {}
    for k, (a, b) in S.SPLITS.items():
        x = ic.loc[a:b]
        out[f"IC_{k}"] = x.mean()
        out[f"t_{k}"] = rl.newey_west_t(x.values, lags=21)
    return out
