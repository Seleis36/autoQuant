"""Shared loaders/features for the term-structure-carry study (vol-complex)."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared"))
import research_lib as rl

ANN = 252
END = "2026-09-11"
IS_END = "2018-12-31"          # fixed before any OOS result was looked at
OOS_START = "2019-01-01"

def load_all(end=END):
    d = {}
    for t, k in [("^VIX", "vix"), ("^VIX3M", "vix3m"), ("^VIX9D", "vix9d"), ("^VVIX", "vvix"),
                 ("VIXY", "vixy"), ("SVXY", "svxy"), ("UVXY", "uvxy"), ("VXX", "vxx"), ("SPY", "spy")]:
        d[k] = rl.load_series(t).loc[:end]["Close"]
    idx = d["vixy"].dropna().index
    df = pd.DataFrame({k: v.reindex(idx) for k, v in d.items()})
    for k in ["vix", "vix3m", "vix9d", "vvix", "spy"]:
        df[k] = df[k].ffill()
    return df

def features(df):
    f = pd.DataFrame(index=df.index)
    f["slope"] = df.vix3m / df.vix                    # >1 contango
    f["slope9"] = df.vix / df.vix9d                   # >1 short-end contango
    f["lslope"] = np.log(f.slope)
    spyr = df.spy.pct_change()
    for w in [5, 10, 21]:
        f[f"rv{w}"] = spyr.rolling(w).std(ddof=1) * np.sqrt(ANN) * 100
        f[f"vrp{w}"] = df.vix - f[f"rv{w}"]
    f["vix_ma10"] = df.vix / df.vix.rolling(10).mean()
    f["vix_chg5"] = df.vix.pct_change(5)
    f["vvix"] = df.vvix
    f["vixy_ret"] = df.vixy.pct_change()
    f["vixy_vol"] = rl.ewm_vol(f.vixy_ret, halflife=10, ann=ANN)
    f["spy_ret"] = spyr
    return f

def rolling_beta(y, x, win=63):
    cov = y.rolling(win).cov(x); var = x.rolling(win).var()
    return cov / var

def bt_multi(weights: pd.DataFrame, closes: pd.DataFrame, costs: dict, ann=ANN, name="s"):
    """Multi-leg backtest; weights[t] held from close t to t+1; per-leg cost bps per side."""
    w = weights.reindex(closes.index).fillna(0.0)
    r = closes.pct_change().fillna(0.0)
    w_eff = w.shift(1).fillna(0.0)
    turn = (w_eff - w_eff.shift(1).fillna(0.0)).abs()
    gross = (w_eff * r).sum(axis=1)
    cost = sum(turn[c] * costs[c] / 1e4 for c in w.columns)
    net = (gross - cost).rename(name)
    st = rl.perf_stats(net, ann=ann, name=name)
    st["Turnover_ann"] = turn.sum(axis=1).sum() / (len(turn) / ann)
    st["GrossExp"] = w_eff.abs().sum(axis=1).mean()
    return net, st

def yearly_sharpe(net):
    return net.groupby(net.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(ANN) if x.std() > 0 else np.nan)

def report(net, name=""):
    full = rl.perf_stats(net, ANN, "full"); is_ = rl.perf_stats(net.loc[:IS_END], ANN, "IS")
    oos = rl.perf_stats(net.loc[OOS_START:], ANN, "OOS")
    t = pd.DataFrame([full, is_, oos])
    return t
