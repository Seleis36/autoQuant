"""Screen 2: signal combination, weighting scheme, holding period (turnover) trade-off.
All numbers net of 5 bp/side unless labelled gross."""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
from panel import load_panel
from xs_lib import *

P = load_panel()
C, O, V, M = P["close"], P["open"], P["volume"], P["member"]
sec = P["sector"].fillna("UNK")
ret = C.pct_change(); logret = np.log(C).diff()
hist_ok = C.notna().rolling(60).sum().ge(55)
mask = M & hist_ok & C.notna()
mkt = ret.where(mask).mean(axis=1)
def cum(n): return (C / C.shift(n) - 1)
def sres(x): return group_demean(x, sec, mask)
on = np.log(O / C.shift(1)); intra = np.log(C / O)
vol20 = logret.rolling(20).std()
vol60 = logret.rolling(60).std()

Z = lambda s: zscore_xs(s, mask)
comp = {
    "rev5_sec": Z(-sres(cum(5))),
    "rev21_sec": Z(-sres(cum(21))),
    "rev1_sec": Z(-sres(cum(1))),
    "intra5_rev": Z(-sres(intra.rolling(5).sum())),
    "on5_rev": Z(-sres(on.rolling(5).sum())),
    "mom12_1": Z(C.shift(21) / C.shift(252) - 1),
}
combos = {
    "rev5_sec": ["rev5_sec"],
    "rev5+rev21": ["rev5_sec", "rev21_sec"],
    "rev5+rev21+mom": ["rev5_sec", "rev21_sec", "mom12_1"],
    "rev5+mom": ["rev5_sec", "mom12_1"],
    "rev1+rev5+rev21": ["rev1_sec", "rev5_sec", "rev21_sec"],
    "on5+intra5": ["on5_rev", "intra5_rev"],
    "all6": list(comp),
}
rows = []
for cname, parts in combos.items():
    sig = sum(comp[p] for p in parts) / len(parts)
    sig = sig.where(mask)
    for wscheme in ["decile", "linear", "linear_invvol"]:
        if wscheme == "decile":
            w0 = decile_weights(sig, mask, q=0.1)
        elif wscheme == "linear":
            w0 = linear_weights(rank_xs(sig, mask), mask)
        else:
            w0 = linear_weights(rank_xs(sig, mask).div(vol60 * np.sqrt(252)), mask)
        for hold in [1, 3, 5, 10]:
            w = smooth_weights(w0, hold)
            net, st = xs_backtest(w, ret, cost_bps=5.0)
            sp = split_perf(net, SPLITS)
            rows.append({"combo": cname, "w": wscheme, "hold": hold, "GrossSh": st["GrossSharpe"], "Net": st["Sharpe"],
                         "IS": sp.loc["IS", "Sharpe"], "OOS": sp.loc["OOS", "Sharpe"], "Turn": st["Turnover_ann"],
                         "Vol": st["Vol"], "CAGR": st["CAGR"]})
    print(cname, "done", flush=True)
df = pd.DataFrame(rows).round(3)
print(df.to_string())
df.to_csv(os.path.join(HERE, "screen2_results.csv"), index=False)
