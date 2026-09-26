"""Pre-declared trading rules on credit signals (VIXY, 5 bp), slope lagged 1 day."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "vix-cot-positioning"))
import numpy as np, pandas as pd
import vc_data as vc
from strategy import target_weight
from fetch_cot_vix import fetch_tff

P = vc.panel()
R = P[["HYG", "IEF", "VIXY"]].pct_change()
beta = (R["HYG"].rolling(252).cov(R["IEF"]) / R["IEF"].rolling(252).var()).shift(1)
hy = R["HYG"] - beta * R["IEF"]
cont = ((P["VIX3M"] / P["VIX"]).shift(1) > 1)
carry = pd.Series(np.where(cont, -1.0, 0), index=P.index)
dd = P["HYG"] / P["HYG"].rolling(63).max() - 1
cot = target_weight(P["VIXY"], P["VIX"], P["VIX3M"], fetch_tff())
rows = {}
def run(nm, w):
    net, st = vc.bt(w.fillna(0), P["VIXY"], 5)
    rows[nm] = vc.split_row(net, {"2022+": vc.sh(net.loc["2022":]), "Exp": st["AvgExposure"]}); return net
run("carry lag1", carry); cn = run("COT book", cot)
for w in (5, 21, 63):
    m = hy.rolling(w).sum()
    run(f"carry & HY{w}>0 (credit trend)", carry.where(m > 0, 0.0))
    run(f"carry & HY{w}<0 (credit contrarian)", carry.where(m < 0, 0.0))
    run(f"L/S sign(-HY{w})... long VIXY if credit falling", pd.Series(-np.sign(m) * -1, index=P.index) * -1)
for th in (-0.01, -0.02, -0.04):
    run(f"short VIXY if HYG dd63 < {th}", pd.Series(np.where(dd < th, -1.0, 0.0), index=P.index))
    run(f"carry OR HYG dd63 < {th}", pd.Series(np.where(cont | (dd < th), -1.0, 0.0), index=P.index))
n2 = run("COT & HY21>0", cot.where(hy.rolling(21).sum() > 0, 0.0))
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 60); pd.set_option("display.max_columns", 20)
print(pd.DataFrame(rows).T.round(2))
