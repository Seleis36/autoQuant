"""Screen 5: reversal with earnings-window exclusion (signal set to NaN if an earnings
reaction bar falls inside the formation window or the next `ahead` bars)."""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
from panel import load_panel
from xs_lib import *
from earnings import load_earnings, reaction_day_matrix, window_matrix

P = load_panel()
C, M = P["close"], P["member"]
sec = P["sector"].fillna("UNK")
ret = C.pct_change(); logret = np.log(C).diff()
hist_ok = C.notna().rolling(60).sum().ge(55)
mask = M & hist_ok & C.notna()
E = load_earnings()
R = reaction_day_matrix(E, C.index, C.columns)
has_e = R.any()
print("tickers with earnings dates:", has_e.sum(), "of", len(has_e))
def cum(n): return (C / C.shift(n) - 1)
def sres(x): return group_demean(x, sec, mask)
Z = lambda s: zscore_xs(s, mask)
for excl_name, W in [("none", None),
                     ("excl formation[-5,0] & ahead 5", window_matrix(R, before=5, after=5)),
                     ("excl formation only", window_matrix(R, before=0, after=5)),
                     ("excl ahead only (next 5 bars)", window_matrix(R, before=5, after=0))]:
    m = mask & has_e                    # compare on the same universe
    if W is not None:
        m = m & ~W
    sig = (Z(-sres(cum(5))).where(m) + Z(-sres(cum(21))).where(m)) / 2
    for lab, w in [("dec1 rev5", decile_weights(Z(-sres(cum(5))).where(m), m, 0.1)),
                   ("lin3 rev5+21", smooth_weights(linear_weights(rank_xs(sig, m), m), 3))]:
        net, st = xs_backtest(w, ret, cost_bps=5.0); g, gs = xs_backtest(w, ret, cost_bps=0.0)
        sp = split_perf(net, SPLITS)
        print(f"{excl_name:34s} {lab:13s} gross {gs['Sharpe']:.2f} net {st['Sharpe']:.2f} IS {sp.loc['IS','Sharpe']:.2f} OOS {sp.loc['OOS','Sharpe']:.2f} turn {st['Turnover_ann']:.0f}")
