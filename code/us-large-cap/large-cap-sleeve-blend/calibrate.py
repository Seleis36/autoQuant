"""Fix the blend's sleeve multipliers on IS (2011-2017) only, from the deployable sleeve
functions: m_k = (1/IS vol_k) / sum(1/IS vol) * L, with L putting the return-level blend at 10 %
IS vol. Then backtest the WEIGHT-level blend (trades net across sleeves) and every leave-one-out
blend. Writes sleeve nets to nets_0_sleeves.parquet (gitignored)."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
U = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(U, "shared")); sys.path.insert(0, os.path.join(U, "quality-value-composite"))
from modload import load
from xs_lib import xs_backtest
from common import splits_row

rm = load(os.path.join(U, "residual-momentum", "strategy.py"))
qvc = load(os.path.join(U, "quality-value-composite", "strategy.py"))
txt = load(os.path.join(U, "filing-text-changes", "strategy.py"))
rec = load(os.path.join(U, "index-reconstitution", "strategy.py"))
X = rm._panel_inputs()
ret = X["close"].pct_change(fill_method=None).loc["2011-01-01":]
W = {"RM": rm.residual_momentum_weights(X).loc["2011-01-01":],
     "QVC": qvc.qvc_weights(X), "TXT": txt.text_weights(X), "REC": rec.recon_weights(X)}
N = {}
for k, w in W.items():
    N[k], st = xs_backtest(w, ret, cost_bps=5.0)
    print(k, {a: round(b, 3) for a, b in splits_row(N[k], st).items()}, "avg gross %.2f" % st["AvgGross"])
N = pd.DataFrame(N)
N.to_parquet(os.path.join(HERE, "nets_0_sleeves.parquet"))
iv = 1 / N.loc[:"2017"].std(); w = iv / iv.sum()
b = (N * w).sum(axis=1)
L = 0.10 / (b.loc[:"2017"].std() * np.sqrt(252))
m = (w * L).round(3)
print("\nIS equal-risk weights", w.round(3).to_dict(), " leverage x%.2f" % L)
print("MULT =", m.to_dict())
print("return-level blend:", {a: round(v, 3) for a, v in splits_row(b * L).items()})


def wblend(mult):
    cols = sorted(set().union(*[W[k].columns for k in mult]))
    return sum(W[k].reindex(columns=cols).fillna(0.0) * v for k, v in mult.items())


rows = []
for drop in [None, "RM", "QVC", "TXT", "REC"]:
    keep = [k for k in W if k != drop]
    iv_ = 1 / N.loc[:"2017", keep].std(); w_ = iv_ / iv_.sum()
    L_ = 0.10 / ((N[keep] * w_).sum(axis=1).loc[:"2017"].std() * np.sqrt(252))
    mult = (w_ * L_).to_dict()
    Wb = wblend(mult)
    net, st = xs_backtest(Wb, ret.reindex(columns=Wb.columns), cost_bps=5.0)
    r = splits_row(net, st); r.update({"blend": "all four" if drop is None else f"without {drop}", "avg_gross": st["AvgGross"],
                                       "max_gross": Wb.abs().sum(axis=1).max(), "oos_vol": net.loc["2018":].std() * np.sqrt(252)})
    rows.append(r)
    if drop is None:
        net.to_frame("blend").to_parquet(os.path.join(HERE, "nets_0_blend_weightlevel.parquet"))
        for c in (2.0, 10.0):
            n2, s2 = xs_backtest(Wb, ret.reindex(columns=Wb.columns), cost_bps=c)
            print(f"all four @ {c} bp:", {a: round(v, 3) for a, v in splits_row(n2, s2).items()})
        yr = net.groupby(net.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(252)).round(2)
        print("yearly Sharpe:", yr.to_dict())
d = pd.DataFrame(rows).set_index("blend")
pd.set_option("display.width", 220)
print("\nweight-level blends, 5 bp:"); print(d.round(3).to_string())
d.round(4).to_csv(os.path.join(HERE, "calibrate_results.csv"))
print("\nsleeve corr FULL / OOS:"); print(N.corr().round(2).to_string()); print(N.loc["2018":].corr().round(2).to_string())
