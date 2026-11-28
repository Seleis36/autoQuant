"""Validate intl-rebalance-flow strategy.py (EFA vs SPY, last session): reproduce the 08
book, vectorbt cross-check at weights/4 (vectorbt cannot borrow), truncation test, lag,
cost ladder, bootstrap, DSR, concentration, correlation with global-rebalance-pressure."""
import os, sys, importlib.util
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared")); sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
import data as D, research_lib as rl
spec = importlib.util.spec_from_file_location("irf_strategy", os.path.join(_HERE, "strategy.py"))
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)

SPL = {"FULL": ("2002-01-01", "2026-12-31"), "IS": ("2002-01-01", "2012-12-31"), "OOS": ("2013-01-01", "2026-12-31")}
COST = {"SPY": 1.0, "EFA": 2.0}
close = D.load_panel(["SPY", "EFA"], "Close", start="1998-12-01")
W = S.target_weights(close)

def run(W, cost_mult=1.0, lag=0):
    ret = close[W.columns].pct_change().fillna(0.0)
    We = W.shift(1 + lag).fillna(0.0)
    dW = (We - We.shift(1).fillna(0.0)).abs()
    net = (We * ret).sum(axis=1) - (dW * pd.Series(COST) * cost_mult / 1e4).sum(axis=1)
    return net, dW.sum(axis=1), We

def sr(x, a=None, b=None):
    x = x.loc[a:b]; return x.mean() / x.std() * np.sqrt(252)

net, turn, We = run(W)
f = net.loc[SPL["FULL"][0]:]; eq = (1 + f).cumprod()
print("strategy.py net Sharpe:", {k: round(sr(net, a, b), 3) for k, (a, b) in SPL.items()})
print(f"CAGR {eq.iloc[-1] ** (252 / len(f)) - 1:.4f}  vol {f.std() * np.sqrt(252):.4f}  MaxDD {(eq / eq.cummax() - 1).min():.4f}  "
      f"turn/yr {turn.loc[f.index].sum() / (len(f) / 252):.2f}  avg gross {We.abs().sum(axis=1).loc[f.index].mean():.3f}  "
      f"max gross {We.abs().sum(axis=1).max():.2f}  active {(We.abs().sum(axis=1).loc[f.index] > 0).mean():.3f}  t_NW {rl.newey_west_t(f.values, 21):.2f}")

import vectorbt as vbt
c = close[W.columns].loc["2002-01-01":].ffill(); w = W.loc[c.index] / 4.0
pf = vbt.Portfolio.from_orders(c, size=w, size_type="targetpercent", direction="both", group_by=True, cash_sharing=True,
                               fees=pd.Series(COST)[c.columns].values / 1e4, freq="1D", init_cash=1e6, call_seq="auto")
n4, *_ = run(W / 4.0)
print(f"vectorbt (w/4) Sharpe {sr(pf.returns()):.3f} vs strategy w/4 {sr(n4.loc[c.index]):.3f}; corr {pf.returns().corr(n4.loc[c.index]):.4f}")

dl = S.next_session_days_left(close.index)
act = dl[dl == 0].index
tests = [act[act > "2008-01-01"][9], act[act > "2016-01-01"][3], act[act > "2025-01-01"][2], close.index[-1], close.index[-2]]
worst = 0.0
for d in tests:
    diff = (S.target_weights(close.loc[:d]).loc[d] - W.loc[d]).abs().max(); worst = max(worst, diff)
    print(f"truncate at {d.date()}: {W.loc[d].round(4).to_dict()} |diff| {diff:.2e}")
print("truncation worst |diff|:", worst)
for lag in [1, 2]:
    n_, *_ = run(W, lag=lag); print(f"+{lag} lag: " + str({k: round(sr(n_, a, b), 2) for k, (a, b) in SPL.items()}))
for m in [0, 2.5]:
    n_, *_ = run(W, cost_mult=m); print(f"cost x{m}: " + str({k: round(sr(n_, a, b), 2) for k, (a, b) in SPL.items()}))
rng = np.random.default_rng(7); x = f.values; L = 63; nb = int(np.ceil(len(x) / L)); out = []
for _ in range(2000):
    st = rng.integers(0, len(x) - L, nb); s = np.concatenate([x[i:i + L] for i in st])[:len(x)]
    out.append(s.mean() / s.std() * np.sqrt(252))
out = np.array(out)
print(f"bootstrap: median {np.median(out):.2f} 5% {np.percentile(out, 5):.2f} P>0 {(out > 0).mean():.3f} P>0.5 {(out > 0.5).mean():.3f}")
from scipy.stats import skew, kurtosis
for N in [20, 60]:
    print(f"DSR N={N}: {rl.deflated_sharpe(sr(f), len(f), N, skew(f), kurtosis(f, fisher=False)):.3f}")
print("by sub-period:", {f"{a}-{b}": round(sr(f, a, b), 2) for a, b in [("2002", "2007"), ("2008", "2012"), ("2013", "2019"), ("2020", "2026"), ("2024", "2026")]})
grp = pd.read_parquet(os.path.join(_HERE, "..", "global-rebalance-pressure", "nets_04.parquet"))["grp"]
j = pd.concat([f, grp], axis=1).dropna().loc["2002-08":]
print("daily corr with global-rebalance-pressure:", round(j.corr().iloc[0, 1], 3),
      "| corr to SPY:", round(f.corr(close.SPY.pct_change().loc[f.index]), 3))
net.rename("irf").to_frame().to_parquet(os.path.join(_HERE, "nets_09.parquet"))
W.to_parquet(os.path.join(_HERE, "spec_weights.parquet"))
