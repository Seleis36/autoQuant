"""Data plumbing for credit-spread-trend.

Everything here is read from the shared flat daily cache in `data/`. The only
non-obvious piece is `hy_excess`: HYG carries both credit risk and ~3.5y of
duration, so a raw long-HYG signal is half a duration bet. We strip the duration
with a short IEF leg at a fixed hedge ratio, which keeps the traded object a pure
credit-risk premium and keeps the hedge ratio out of the fitted-parameter count.
"""
import os, sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(_ROOT, "code", "shared"))
import research_lib as rl  # noqa: E402

ANN = 252.0
# HYG effective duration ~3.4y, IEF ~7.3y (iShares fact sheets, stable over the sample).
# 3.4 / 7.3 = 0.47 -> 0.47 units of IEF short per unit of HYG long.
DUR_HEDGE = 0.47


def close(ticker, pre2010=False):
    path = rl.daily_cache_path(ticker)
    if pre2010:
        path = path.replace("_d.parquet", "_d_pre2010.parquet")
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    s = df["Close"]
    return s[~s.index.duplicated(keep="last")].sort_index()


def prices(tickers, start=None, end=None, include_pre2010=True):
    """Daily closes, splicing the *_d_pre2010.parquet copies on the front when present."""
    out = {}
    for t in tickers:
        s = close(t)
        if include_pre2010:
            p = rl.daily_cache_path(t).replace("_d.parquet", "_d_pre2010.parquet")
            if os.path.exists(p):
                pre = close(t, pre2010=True)
                # the two files are both auto-adjusted but from different downloads;
                # rescale the older one onto the newer one at the overlap date
                ov = pre.index.intersection(s.index)
                if len(ov):
                    k = s.loc[ov[-1]] / pre.loc[ov[-1]]
                    pre = pre * k
                s = pd.concat([pre[~pre.index.isin(s.index)], s]).sort_index()
        out[t] = s
    df = pd.DataFrame(out).sort_index()
    return df.loc[start:end]


def hy_excess(px, hedge=DUR_HEDGE):
    """Daily return of long 1 HYG / short `hedge` IEF -- the HY credit risk premium."""
    r = px.pct_change()
    return (r["HYG"] - hedge * r["IEF"]).rename("hy_excess")


def crypto_book(root=_ROOT):
    """Equal-weight daily net returns of the four live crypto alphas that publish a
    daily backtest series (bult is hourly and has none, so it is excluded).

    These are backtest series, not realised live P&L -- the live books are weeks old.
    They are the best available proxy for what this strategy has to diversify.
    """
    a = os.path.join(root, "alphas")
    s = {}
    d = pd.read_parquet(os.path.join(a, "spot-eth/eth-trend-filter/backtest_series.parquet"))
    s["eth_trend"] = d["ret_final"]
    d = pd.read_parquet(os.path.join(a, "crypto-alts/xs-momentum-neutral/backtest_series.parquet"))
    s["alts_xs"] = d["net_10bp"]
    d = pd.read_csv(os.path.join(a, "spot-btc/coinbase-premium/equity.csv"), parse_dates=["ts"]).set_index("ts")
    s["cb_prem"] = d["strategy"].pct_change()
    d = pd.read_csv(os.path.join(a, "spot-btc/weekday-trend/equity.csv"), parse_dates=["Date"]).set_index("Date")
    s["wk_trend"] = d["strategy"].pct_change()
    df = pd.DataFrame(s)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    book = df.mean(axis=1, skipna=True).dropna()
    return book.loc["2018-03-09":].rename("crypto_book")


def hedge_report(net, book=None, ann=ANN):
    """How well `net` hedges the crypto book: overall corr, corr on the book's worst
    decile days, and the strategy's return during the book's drawdown periods."""
    if book is None:
        book = crypto_book()
    # the book is a 365-day series; align on the strategy's trading calendar
    b = book.reindex(net.index).fillna(0.0)
    common = net.dropna().index.intersection(book.index)
    b, n = book.loc[common], net.loc[common]
    q = b.quantile(0.10)
    dn = b <= q
    eq = (1 + b).cumprod()
    in_dd = (eq / eq.cummax() - 1) < -0.05
    return pd.Series({
        "corr_all": n.corr(b),
        "corr_worst_decile": n[dn].corr(b[dn]),
        "strat_bp_on_book_worst_decile": n[dn].mean() * 1e4,
        "strat_bp_other_days": n[~dn].mean() * 1e4,
        "strat_ann_ret_in_book_dd": n[in_dd].mean() * ann,
        "strat_ann_ret_out_book_dd": n[~in_dd].mean() * ann,
        "days_worst_decile": int(dn.sum()),
        "days_in_book_dd": int(in_dd.sum()),
    })
