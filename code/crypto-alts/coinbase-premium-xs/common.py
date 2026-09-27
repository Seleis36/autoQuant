"""coinbase-premium-xs: coin-specific Coinbase (USD) premium over Binance (USDT), demeaned across
coins so the USD/USDT basis and any market-wide US premium cancel."""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
import research_lib as rl  # noqa
import study as S  # noqa
import venues as V  # noqa


def premium_panel(tickers, index, venue_loader=V.coinbase_daily, vol_field="Volume"):
    """log(venue close / Binance USDT close) minus the same-day cross-sectional median over all
    coins quoted on both venues (BTC and ETH included as anchors). Both venues' daily bars
    close at D+1 00:00 UTC = the yfinance close stamped D. Rows with zero venue volume masked."""
    other = V.panel(venue_loader, tickers, "Close").reindex(index)
    bn = V.panel(V.binance_daily, tickers, "Close").reindex(index)
    ov = V.panel(venue_loader, tickers, vol_field).reindex(index)
    raw = np.log(other / bn).where(ov > 0)
    raw = raw.where(raw.abs() < 0.5)          # >50 % gaps are broken prints / halted markets
    xs = raw.sub(raw.median(axis=1), axis=0)
    return raw, xs, ov


def ic_table(sig, fwd, mask, min_n=6):
    s = sig.where(mask); ok = s.notna() & fwd.notna(); n = ok.sum(axis=1)
    rs = s.where(ok).rank(axis=1); rf = fwd.where(ok).rank(axis=1)
    rs = rs.sub(rs.mean(axis=1), axis=0); rf = rf.sub(rf.mean(axis=1), axis=0)
    ic = ((rs * rf).sum(axis=1) / np.sqrt((rs ** 2).sum(axis=1) * (rf ** 2).sum(axis=1))).where(n >= min_n).dropna()
    out = {"n_days": len(ic), "avg_n": n[n >= min_n].mean()}
    for k, (a, b) in S.SPLITS.items():
        x = ic.loc[a:b]; out[f"IC_{k}"] = x.mean(); out[f"t_{k}"] = rl.newey_west_t(x.values, 21)
    return out
