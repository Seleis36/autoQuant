"""Evaluate trend-flow-blend from strategy.py: full / IS / OOS, vs the deployed
global-etf-sleeve-blend, sleeve correlations and contributions, costs, lag, gross stats,
truncation look-ahead test, vectorbt cross-check, bootstrap, DSR, calendar years."""
import os, sys, importlib.util
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared")); sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
import data as D, research_lib as rl
def _load(name, rel):
    s = importlib.util.spec_from_file_location(name, os.path.join(_HERE, rel)); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
S = _load("tfb", "strategy.py"); OLD = _load("old_blend", "../global-etf-sleeve-blend/strategy.py")
COLS = S.COLUMNS
COST = pd.Series({**{c: 5.0 for c in S.COUNTRIES}, "SPY": 1.0, "EFA": 2.0})
SPL = {"FULL": ("2003-03-01", "2026-12-31"), "IS": ("2003-03-01", "2012-12-31"), "OOS": ("2013-01-01", "2026-12-31")}
close = D.load_panel(COLS + ["IEF"], "Close", start="1998-12-01")

def run(W, cost_mult=1.0, lag=0):
    W = W.reindex(columns=COLS).fillna(0.0)
    ret = close[COLS].pct_change().fillna(0.0); We = W.shift(1 + lag).fillna(0.0)
    dW = (We - We.shift(1).fillna(0.0)).abs()
    return (We * ret).sum(axis=1) - (dW * COST * cost_mult / 1e4).sum(axis=1), dW.sum(axis=1), We
def sr(x, a=None, b=None):
    x = x.loc[a:b]; return x.mean() / x.std() * np.sqrt(252)
def stats(net, turn=None, We=None):
    f = net.loc[SPL["FULL"][0]:]; eq = (1 + f).cumprod()
    o = {k: round(sr(net, a, b), 3) for k, (a, b) in SPL.items()}
    o.update({"2020-26": round(sr(net, "2020", "2026"), 2), "2024-26": round(sr(net, "2024", "2026"), 2),
              "CAGR": round(eq.iloc[-1] ** (252 / len(f)) - 1, 4), "Vol": round(f.std() * np.sqrt(252), 4),
              "MaxDD": round((eq / eq.cummax() - 1).min(), 4), "t_NW": round(rl.newey_west_t(f.values, 21), 2)})
    if turn is not None: o["Turn/yr"] = round(turn.loc[f.index].sum() / (len(f) / 252), 1)
    if We is not None:
        g = We.abs().sum(axis=1).loc[f.index]; o.update({"AvgGross": round(g.mean(), 2), "p99Gross": round(g.quantile(.99), 2), "MaxGross": round(g.max(), 2)})
    return o

W = S.target_weights(close)
net, turn, We = run(W)
rows = {"trend-flow-blend (spec)": stats(net, turn, We)}
Wold = OLD.target_weights(close[OLD.COLUMNS]); n_old, t_old, We_old = run(Wold)
rows["deployed global-etf-sleeve-blend"] = stats(n_old, t_old, We_old)
SW = S.sleeve_weights(close); sn = {}
for k, w in SW.items():
    n_, t_, W_ = run(S.MULT[k] * w.reindex(columns=COLS).fillna(0.0)); sn[k] = n_; rows[f"sleeve {k} (x mult)"] = stats(n_, t_, W_)
nocap, _, _ = run(sum(S.MULT[k] * SW[k].reindex(columns=COLS).fillna(0.0) for k in SW)); rows["no gross cap"] = stats(nocap)
for drop in ["intl_flow", "rebalance"]:
    m = dict(S.MULT); m[drop] = 0.0
    n_, *_ = run(S.target_weights(close, mult=m)); rows[f"without {drop} (same mults)"] = stats(n_)
for cm in [2.0]:
    n_, *_ = run(W, cost_mult=cm); rows[f"costs x{cm:.0f}"] = stats(n_)
n_, *_ = run(W, lag=1); rows["+1 session lag"] = stats(n_)
pd.set_option("display.width", 250)
print(pd.DataFrame(rows).T.to_string())
SN = pd.DataFrame(sn).loc[SPL["FULL"][0]:]
print("\nsleeve daily correlations:\n", SN.corr().round(3).to_string())
print("share of total P&L by sleeve:", (SN.sum() / SN.sum().sum()).round(3).to_dict())
print("corr blend vs SPY:", round(net.loc[SPL['FULL'][0]:].corr(close.SPY.pct_change().loc[SPL['FULL'][0]:]), 3),
      "| vs deployed blend:", round(net.loc[SPL['FULL'][0]:].corr(n_old.loc[SPL['FULL'][0]:]), 3))
print("rows hitting the gross cap:", int((We.abs().sum(axis=1) >= 3.999).sum()))

# truncation test
dl = S.GRP.next_session_days_left(close.index)
tests = [pd.Timestamp("2008-10-27"), pd.Timestamp("2015-06-25"), dl[dl == 0].index[-3], pd.Timestamp("2026-09-15"),
         close.index[-1], close.index[-2]]
worst = 0.0
for d in tests:
    diff = (S.target_weights(close.loc[:d]).loc[d] - W.loc[d]).abs().max(); worst = max(worst, diff)
    print(f"truncate {d.date()}: gross {W.loc[d].abs().sum():.3f}  |diff| {diff:.2e}")
print("truncation worst |diff|:", worst)

# vectorbt cross-check at weights/4 (vectorbt cash account cannot borrow)
import vectorbt as vbt
c = close[COLS].loc["2003-03-01":].ffill().bfill(); w4 = W.loc[c.index] / 4.0
pf = vbt.Portfolio.from_orders(c, size=w4, size_type="targetpercent", direction="both", group_by=True, cash_sharing=True,
                               fees=COST[c.columns].values / 1e4, freq="1D", init_cash=1e7, call_seq="auto")
n4, *_ = run(W / 4.0)
print(f"vectorbt w/4 Sharpe {sr(pf.returns()):.3f} vs strategy w/4 {sr(n4.loc[c.index]):.3f}; corr {pf.returns().corr(n4.loc[c.index]):.4f}")

f = net.loc[SPL["FULL"][0]:]; rng = np.random.default_rng(11); x = f.values; L = 63; nb = int(np.ceil(len(x) / L)); out = []
for _ in range(2000):
    st = rng.integers(0, len(x) - L, nb); s = np.concatenate([x[i:i + L] for i in st])[:len(x)]; out.append(s.mean() / s.std() * np.sqrt(252))
out = np.array(out)
print(f"bootstrap: median {np.median(out):.2f} 5% {np.percentile(out, 5):.2f} P>0.5 {(out > 0.5).mean():.3f} P>1 {(out > 1).mean():.3f}")
from scipy.stats import skew, kurtosis
for N in [100, 300]:
    print(f"DSR N={N}: {rl.deflated_sharpe(sr(f), len(f), N, skew(f), kurtosis(f, fisher=False)):.3f}")
yr = f.groupby(f.index.year).sum() * 100
print("calendar years (%):", yr.round(1).to_dict())
print("positive years:", int((yr > 0).sum()), "of", len(yr))
net.rename("tfb").to_frame().join(n_old.rename("old")).to_parquet(os.path.join(_HERE, "nets_02.parquet"))
W.to_parquet(os.path.join(_HERE, "spec_weights.parquet"))
