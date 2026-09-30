"""Shared data + helpers for retail-crowding-xs.

Pre-registered before any result was looked at (2026-09-30):
  data      Binance USD-M `metrics` archive, 2021-12-01+ for every perp except BTC; one value
            per day = last 5-minute stamp before 23:00 UTC of day D (1 h margin before the
            00:00 UTC close at which the weight is set).
  universe  point-in-time top-20 by trailing-90d median USD volume among the 64 coins of
            `funding_panel.PERP_OF` that have >= 60 days of metrics on that date (plus the
            funding-xs-crowding liquidity filters). BTC is eligible.
  P&L       spot yfinance XXX-USD closes (what the sim book prices), research_lib.backtest_xs
  IS        2022-03-01 .. 2023-12-31   (first 90 days of the archive are warm-up)
  OOS       2024-01-01 .. end
  cost      10 bp per side on traded notional
"""
import os
import sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "crypto-perps", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "crypto-alts", "shared"))
import research_lib as rl  # noqa: E402
import funding_panel as fp  # noqa: E402
import metrics_panel as mp  # noqa: E402
import universe as uv  # noqa: E402

IS = ("2022-03-01", "2023-12-31")
OOS = ("2024-01-01", "2026-12-31")
FULL = ("2022-03-01", "2026-12-31")
SPLITS = {"full": FULL, "IS": IS, "OOS": OOS}
COST = 10.0
TICKERS = list(fp.PERP_OF)
CACHE = os.path.join(_HERE, "_panel_cache.pkl")


def load(n_top=20, min_metric_days=60, refresh=False, start="2021-12-01"):
    """close, volume, metrics dict (column -> DataFrame[date x ticker]), mask."""
    cache = CACHE if start == "2021-12-01" else CACHE.replace(".pkl", f"_{start}.pkl")
    if os.path.exists(cache) and not refresh:
        return pd.read_pickle(cache)
    panel = uv.load_panel(TICKERS)
    close = uv.clean_close(panel["Close"])
    vol = panel["Volume"].reindex_like(close)
    sym_of = {t: fp.PERP_OF[t] for t in close.columns if t in fp.PERP_OF}
    met = mp.daily_metrics(list(sym_of.values()), cutoff_hour=23, how="last")
    inv = {v: k for k, v in sym_of.items()}
    met = {c: df.rename(columns=inv).reindex(index=close.index, columns=close.columns)
           for c, df in met.items()}
    has_m = met["count_long_short_ratio"].notna().cumsum() >= min_metric_days
    med = vol.rolling(90, min_periods=45).median()
    hist = close.notna().cumsum()
    elig = (hist >= 120) & (med >= 1e6) & close.notna() & has_m & met["count_long_short_ratio"].notna()
    mask = (med.where(elig).rank(axis=1, ascending=False) <= n_top) & elig
    out = (close.loc[start:], vol.loc[start:], {c: d.loc[start:] for c, d in met.items()},
           mask.loc[start:])
    pd.to_pickle(out, cache)
    return out


def btc_beta(close, halflife=60):
    ret = close.pct_change(fill_method=None)
    btc = ret["BTC-USD"]
    cov = ret.ewm(halflife=halflife, min_periods=60).cov(btc)
    return cov.div(btc.ewm(halflife=halflife, min_periods=60).var(), axis=0).clip(-0.5, 3.0)


def beta_neutral(w, beta):
    b = beta.reindex_like(w).fillna(1.0)
    lw, sw = w.clip(lower=0), w.clip(upper=0)
    bl, bs = (lw * b).sum(axis=1), -(sw * b).sum(axis=1)
    return (lw.mul(2 * bs / (bl + bs), axis=0) + sw.mul(2 * bl / (bl + bs), axis=0)).fillna(0.0)


def quantile_ls(sig, mask, q=0.3):
    s = sig.where(mask)
    k = (s.notna().sum(axis=1) * q).round().clip(lower=1)
    long = s.rank(axis=1, ascending=False).le(k, axis=0) & s.notna()
    short = s.rank(axis=1, ascending=True).le(k, axis=0) & s.notna()
    w = long.astype(float).div(long.sum(axis=1).replace(0, np.nan), axis=0) * 0.5 \
        - short.astype(float).div(short.sum(axis=1).replace(0, np.nan), axis=0) * 0.5
    return w.fillna(0.0)


def linear_ls(sig, mask):
    s = sig.where(mask).rank(axis=1, pct=True)
    s = s.sub(s.mean(axis=1), axis=0)
    return s.div(s.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)


def tranche(w, h):
    if h <= 1:
        return w
    parts = []
    for off in range(h):
        keep = pd.Series((np.arange(len(w)) - off) % h == 0, index=w.index)
        parts.append(w.where(keep, np.nan).ffill().fillna(0.0))
    return sum(parts) / h


def evaluate(w, close, name, cost=COST):
    net, st = rl.backtest_xs(w, close, cost_bps=cost, name=name)
    net = net.loc[FULL[0]:]
    row = {"name": name}
    for k, (a, b) in SPLITS.items():
        s = rl.perf_stats(net.loc[a:b], name=k)
        row[f"SR_{k}"] = s["Sharpe"]
        if k == "full":
            row["CAGR"] = s["CAGR"]
            row["MaxDD"] = s["MaxDD"]
    row["Turn"] = st["Turnover_ann"]
    row["Gross"] = st["AvgGross"]
    return net, row


def ic_table(sig, close, mask, horizons=(1, 7, 14)):
    """Mean daily cross-sectional Spearman IC of sig(D) with forward returns (D, D+h]."""
    ret = close.pct_change(fill_method=None)
    out = {}
    s = sig.where(mask)
    for h in horizons:
        fwd = close.shift(-h) / close - 1
        fwd = fwd.sub(fwd.where(mask).mean(axis=1), axis=0)
        ic = s.rank(axis=1).corrwith(fwd.where(mask).rank(axis=1), axis=1)
        out[h] = ic
    return pd.DataFrame(out)
