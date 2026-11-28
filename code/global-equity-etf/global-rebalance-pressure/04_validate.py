"""Validate strategy.py: reproduce the research book, vectorbt cross-check, truncation
(look-ahead) test incl. dates inside the window, +1/+2 session lag, cost ladder, bootstrap,
deflated Sharpe, concentration."""
import os, sys, importlib.util
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared")); sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
import data as D, research_lib as rl
spec = importlib.util.spec_from_file_location("grp_strategy", os.path.join(_HERE, "strategy.py"))
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)

SPL = {"FULL": ("2002-08-01", "2026-12-31"), "IS": ("2002-08-01", "2012-12-31"), "OOS": ("2013-01-01", "2026-12-31")}
COST = {"SPY": 1.0, "EFA": 2.0}
close = D.load_panel(["SPY", "EFA", "IEF"], "Close", start="2001-06-01")
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
f = net.loc[SPL["FULL"][0]:]
eq = (1 + f).cumprod()
print("strategy.py net Sharpe:", {k: round(sr(net, a, b), 3) for k, (a, b) in SPL.items()})
print(f"CAGR {eq.iloc[-1] ** (252 / len(f)) - 1:.4f}  vol {f.std() * np.sqrt(252):.4f}  MaxDD {(eq / eq.cummax() - 1).min():.4f}  "
      f"turn/yr {turn.loc[f.index].sum() / (len(f) / 252):.2f}  avg gross {We.abs().sum(axis=1).loc[f.index].mean():.3f}  "
      f"max gross {We.abs().sum(axis=1).max():.2f}  active {(We.abs().sum(axis=1).loc[f.index] > 0).mean():.3f}  "
      f"avg net {We.sum(axis=1).loc[f.index].mean():+.4f}  t_NW {rl.newey_west_t(f.values, 21):.2f}")
old = pd.read_parquet(os.path.join(_HERE, "nets_03.parquet"))["grp_spec"]
print("max |strategy - research| daily diff:", float((net - old.reindex(net.index).fillna(0)).loc["2002-08":].abs().max()))

# ---- vectorbt cross-check (gross <= 1, no borrowing problem; short allowed)
import vectorbt as vbt
c = close[W.columns].loc["2002-08-01":].ffill()
w = W.loc[c.index]
pf = vbt.Portfolio.from_orders(c, size=w, size_type="targetpercent", direction="both", group_by=True,
                               cash_sharing=True, fees=pd.Series(COST)[c.columns].values / 1e4, freq="1D",
                               init_cash=1e6, call_seq="auto")
vr = pf.returns()
# vbt applies the target at the bar's close -> same timing as shift(1) on returns
print(f"vectorbt Sharpe {sr(vr):.3f}  vs strategy {sr(net.loc[c.index]):.3f};  corr {vr.corr(net.loc[c.index]):.4f}")

# ---- truncation test
dl = S.next_session_days_left(close.index)
in_win = dl[dl.isin(S.WINDOW)].index
tests = [pd.Timestamp("2008-10-27"), pd.Timestamp("2015-06-25"), pd.Timestamp("2020-03-26"),
         in_win[in_win > "2024-01-01"][5], close.index[-1], close.index[-2], close.index[-3]]
worst = 0.0
for d in tests:
    Wt = S.target_weights(close.loc[:d])
    diff = (Wt.loc[d] - W.loc[d]).abs().max()
    worst = max(worst, diff)
    print(f"truncate at {d.date()}: weights there {W.loc[d].round(4).to_dict()}  |diff| {diff:.2e}")
print("truncation worst |diff|:", worst)

# ---- lags and costs
for lag in [1, 2]:
    n_, *_ = run(W, lag=lag); print(f"+{lag} session lag: " + str({k: round(sr(n_, a, b), 2) for k, (a, b) in SPL.items()}))
for m in [0, 2, 5]:
    n_, *_ = run(W, cost_mult=m); print(f"cost x{m}: " + str({k: round(sr(n_, a, b), 2) for k, (a, b) in SPL.items()}))

# ---- block bootstrap, DSR, concentration
rng = np.random.default_rng(7); x = f.values; L = 63; nb = int(np.ceil(len(x) / L)); out = []
for _ in range(2000):
    st = rng.integers(0, len(x) - L, nb); s = np.concatenate([x[i:i + L] for i in st])[:len(x)]
    out.append(s.mean() / s.std() * np.sqrt(252))
out = np.array(out)
print(f"bootstrap: median {np.median(out):.2f}  5% {np.percentile(out, 5):.2f}  P(SR>0) {(out > 0).mean():.3f}  P(SR>0.5) {(out > 0.5).mean():.3f}")
from scipy.stats import skew, kurtosis
for N in [42, 100]:
    print(f"DSR N={N}: {rl.deflated_sharpe(sr(f), len(f), N, skew(f), kurtosis(f, fisher=False)):.3f}")
mo = f.groupby(f.index.to_period("M")).sum()
srt = mo.sort_values(ascending=False)
print(f"months active {int((mo != 0).sum())}, hit {(mo[mo != 0] > 0).mean():.2f}; top-5 months share of P&L {srt.iloc[:5].sum() / mo.sum():.2f}; "
      f"ex-2008 Sharpe {sr(f[f.index.year != 2008]):.2f}; ex-top-5-months Sharpe {sr(f[~f.index.to_period('M').isin(srt.index[:5])]):.2f}")
print("top 5 months:", (srt.iloc[:5] * 100).round(2).to_dict())
print("corr to SPY daily:", round(f.corr(close.SPY.pct_change().loc[f.index]), 3))
net.rename("grp").to_frame().to_parquet(os.path.join(_HERE, "nets_04.parquet"))
W.to_parquet(os.path.join(_HERE, "spec_weights.parquet"))
