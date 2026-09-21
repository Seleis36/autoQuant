"""exp02 -- multi-coin carry: per-coin rules, equal-weight portfolios, cross-sectional selection,
cost and capital-factor sensitivity. Returns on one-leg notional unless capital_factor given."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from carry_lib import *

SYMS = [s for s in ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","LINKUSDT"]
        if os.path.exists(os.path.join(DATA_DIR, f"{s}_fundingRate.parquet")) and os.path.isdir(os.path.join(DATA_DIR,"bars",f"{s}_PERP"))
        and (s in ("BTCUSDT","ETHUSDT") or os.path.isdir(os.path.join(DATA_DIR,"bars",s,"1h")))]
pairs_all = {}
print("symbols:", SYMS)
pairs = {s: load_pair(s, start="2020-01-01") for s in SYMS}
SYMS = [s for s in SYMS if len(pairs[s]) > 24*90]; pairs = {s: pairs[s] for s in SYMS}
print("symbols with >90d of paired data:", SYMS, {s: str(pairs[s].index[0].date()) for s in SYMS})
idx = pd.date_range("2020-01-01", max(p.index.max() for p in pairs.values()), freq="h")

def trailing_mean(df, k):
    fs = df["f"].where(df["f"] != 0).dropna()
    return fs.rolling(k).mean().reindex(df.index).ffill()

def hyst(m, hi, lo):
    st = pd.Series(np.nan, index=m.index); st[m > hi] = 1.0; st[m < lo] = 0.0
    return st.ffill().fillna(0.0)

RULES = {
    "always":      lambda df: pd.Series(1.0, index=df.index),
    "k9_hyst":     lambda df: hyst(trailing_mean(df, 9), 0.0001, -0.0001),
    "k21_gt0":     lambda df: (trailing_mean(df, 21) > 0).astype(float),
    "k21_hyst":    lambda df: hyst(trailing_mean(df, 21), 0.00005, -0.00005),
    "k3_gt0":      lambda df: (trailing_mean(df, 3) > 0).astype(float),
}

def coin_net(sym, rule, fee=15.0, slip=5.0):
    df = pairs[sym]
    net, we, turn = backtest_carry(df, RULES[rule](df), fee_bps=fee, slip_bps=slip)
    return net.reindex(idx).fillna(0.0), we.reindex(idx).fillna(0.0), turn.reindex(idx).fillna(0.0)

pd.set_option("display.width", 220)
cols = ["CAGR","Vol","Sharpe","Sharpe_IS","Sharpe_OOS","MaxDD","t_NW","TimeInMkt","Switches/yr"]

# --- per-coin per-rule table
rows = []
for s in SYMS:
    for r in RULES:
        net, we, turn = coin_net(s, r)
        st = summarize(net.loc[pairs[s].index[0]:], we, turn, name=f"{s}:{r}", splits=SPLITS)
        rows.append(st)
per = pd.DataFrame(rows)
print("\n=== per coin x rule"); print(per[cols].round(3).to_string())

# --- equal-weight portfolios (weight 1/n over coins *available* at the time)
def portfolio(syms, rule, fee=15.0, slip=5.0):
    nets, avail = [], []
    for s in syms:
        net, we, turn = coin_net(s, rule, fee, slip)
        nets.append(net); avail.append(pd.Series(1.0, index=idx).where(idx >= pairs[s].index[0], 0.0))
    N = pd.concat(nets, axis=1); A = pd.concat(avail, axis=1)
    port = (N * A).sum(axis=1) / A.sum(axis=1).replace(0, np.nan)
    return port.fillna(0.0)

rows = []
for name, syms in {"BTC": ["BTCUSDT"], "BTC+ETH": ["BTCUSDT","ETHUSDT"], "all": SYMS,
                   "majors3": [s for s in ["BTCUSDT","ETHUSDT","SOLUSDT"] if s in SYMS]}.items():
    for r in RULES:
        port = portfolio(syms, r)
        d = daily(port); st = perf_stats(d, name=f"{name}:{r}")
        for k,(a,b) in SPLITS.items():
            seg = d.loc[a:b]; st[f"Sharpe_{k}"] = seg.mean()/seg.std()*np.sqrt(365)
        rows.append(st)
pf = pd.DataFrame(rows)
print("\n=== equal-weight portfolios"); print(pf[["CAGR","Vol","Sharpe","Sharpe_IS","Sharpe_OOS","MaxDD","t_NW"]].round(3).to_string())

# --- cross-sectional: each hour hold the top-n coins by 21-settlement trailing funding (only if > 0), rebalanced at settlement stamps only
def xs_top(n, k=21, fee=15.0, slip=5.0):
    M = pd.concat({s: trailing_mean(pairs[s], k).reindex(idx) for s in SYMS}, axis=1)
    settle = pd.Series(idx.hour % 8 == 0, index=idx)
    Msett = M.where(settle, axis=0).ffill()
    rk = Msett.rank(axis=1, ascending=False)
    W = ((rk <= n) & (Msett > 0)).astype(float)
    W = W.div(W.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    tot = pd.Series(0.0, index=idx)
    for s in SYMS:
        df = pairs[s]
        net, we, turn = backtest_carry(df, W[s].reindex(df.index).fillna(0.0), fee_bps=fee, slip_bps=slip)
        tot = tot.add(net.reindex(idx).fillna(0.0), fill_value=0.0)
    return tot
rows = []
for n in (1, 2, 3):
    for k in (9, 21, 63):
        port = xs_top(n, k); d = daily(port); st = perf_stats(d, name=f"xs_top{n}_k{k}")
        for kk,(a,b) in SPLITS.items():
            seg = d.loc[a:b]; st[f"Sharpe_{kk}"] = seg.mean()/seg.std()*np.sqrt(365)
        rows.append(st)
xs = pd.DataFrame(rows)
print("\n=== cross-sectional top-n by trailing funding"); print(xs[["CAGR","Vol","Sharpe","Sharpe_IS","Sharpe_OOS","MaxDD","t_NW"]].round(3).to_string())

# --- cost sensitivity for BTC+ETH always-on and k21_hyst
rows = []
for r in ("always", "k21_hyst", "k9_hyst"):
    for fee, slip in ((15, 5), (15, 15), (30, 20), (50, 50)):
        port = portfolio(["BTCUSDT","ETHUSDT"], r, fee, slip); d = daily(port)
        st = perf_stats(d, name=f"BTC+ETH:{r}:fee{fee}+slip{slip}"); rows.append(st)
print("\n=== cost sensitivity (BTC+ETH)"); print(pd.DataFrame(rows)[["CAGR","Vol","Sharpe","MaxDD"]].round(3).to_string())

pd.concat([per, pf, xs]).to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "exp02_results.csv"))
