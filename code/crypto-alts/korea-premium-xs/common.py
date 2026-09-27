"""korea-premium-xs: coin-specific Upbit (KRW) premium over Binance (USDT), cross-sectionally
demeaned so that USDKRW, the USDT basis and the market-wide kimchi premium all cancel."""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
import research_lib as rl  # noqa
import study as S  # noqa
import venues as V  # noqa


def premium_panel(tickers, index):
    """log(Upbit KRW close / Binance USDT close) per coin, minus the same-day cross-sectional
    median over all coins quoted on both venues (BTC and ETH included as anchors).
    Bars are UTC-day aligned on both venues (close at D+1 00:00 UTC = yfinance close D)."""
    up = V.panel(V.upbit_daily, tickers, "Close").reindex(index)
    bn = V.panel(V.binance_daily, tickers, "Close").reindex(index)
    upq = V.panel(V.upbit_daily, tickers, "QuoteVolume").reindex(index)
    raw = np.log(up / bn)
    # guard against stale / suspended prints: need volume on Upbit that day
    raw = raw.where(upq > 0)
    xs = raw.sub(raw.median(axis=1), axis=0)
    xs = xs.where(xs.abs() < 0.3)            # >30 % coin-specific gaps = halted deposits / bad prints
    return raw, xs, upq


def ic_table(sig, fwd, mask, min_n=6):
    s = sig.where(mask); ok = s.notna() & fwd.notna(); n = ok.sum(axis=1)
    rs = s.where(ok).rank(axis=1); rf = fwd.where(ok).rank(axis=1)
    rs = rs.sub(rs.mean(axis=1), axis=0); rf = rf.sub(rf.mean(axis=1), axis=0)
    ic = ((rs * rf).sum(axis=1) / np.sqrt((rs ** 2).sum(axis=1) * (rf ** 2).sum(axis=1))).where(n >= min_n).dropna()
    out = {"n_days": len(ic), "avg_n": n[n >= min_n].mean()}
    for k, (a, b) in S.SPLITS.items():
        x = ic.loc[a:b]; out[f"IC_{k}"] = x.mean(); out[f"t_{k}"] = rl.newey_west_t(x.values, 21)
    return out
