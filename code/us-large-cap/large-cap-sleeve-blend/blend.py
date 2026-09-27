"""Equal-risk blend of this session's us-large-cap sleeves (daily net returns at 5 bp/side,
each already charged its own costs -- blending at the return level forgoes the netting of
opposite trades, so it is conservative).

Sleeves, all defined before OOS was looked at, except where noted:
  RM   residual-momentum SPEC (strategy.py, 10 % vol)                         -- literature spec
  QVC  quality-value-composite IS-selected 5-sleeve fundamental blend          -- IS selection
  TXT  filing-text-changes: Jaccard similarity, all forms, quintile, beta-hedged -- best IS level metric
  REC  index-reconstitution: short additions over bars [+1,+5] after the effective date (leg B)
Sleeve returns come from the deployable strategy functions (nets_0_sleeves.parquet, calibrate.py).
Weights: inverse IS (2011-2017) vol, i.e. equal risk; nothing is fitted on 2018+.
Also: every subset of sleeves (to show which ones carry the blend) and the text-residual
sensitivity (TXT_res, chosen after an OOS-informed diagnostic -- NOT used in the headline)."""
import os, sys, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
U = os.path.join(HERE, "..")
D = pd.read_parquet(os.path.join(HERE, "nets_0_sleeves.parquet"))       # deployable sleeves (calibrate.py)
S = pd.concat({
    "RM": D["RM"], "QVC": D["QVC"], "TXT": D["TXT"], "REC": D["REC"],
    "TXT_res": pd.read_parquet(os.path.join(U, "filing-text-changes", "nets_0_text.parquet"))["text_resid"],
}, axis=1).loc["2011-01-01":].fillna(0.0)
SPL = {"FULL": ("2011", "2026"), "IS": ("2011", "2017"), "OOS": ("2018", "2026")}
sh = lambda x: x.mean() / x.std() * np.sqrt(252)


def stats(x):
    r = {k: sh(x.loc[a:b]) for k, (a, b) in SPL.items()}
    eq = (1 + x).cumprod(); r["MaxDD"] = (eq / eq.cummax() - 1).min(); r["vol"] = x.std() * np.sqrt(252)
    r["CAGR"] = eq.iloc[-1] ** (252 / len(x)) - 1
    return r


print("sleeve Sharpe:"); print(pd.DataFrame({k: stats(S[k]) for k in S}).T.round(3).to_string())
print("\ndaily correlation FULL:"); print(S.corr().round(2).to_string())
print("\ndaily correlation OOS:"); print(S.loc["2018":].corr().round(2).to_string())

rows = []
base = ["RM", "QVC", "TXT", "REC"]
for n in range(1, 5):
    for combo in itertools.combinations(base, n):
        c = list(combo)
        iv = 1 / S.loc[:"2017", c].std(); w = iv / iv.sum()
        b = (S[c] * w).sum(axis=1)
        b = b * (0.10 / (b.loc[:"2017"].std() * np.sqrt(252)))          # 10 % vol on IS
        r = stats(b); r["sleeves"] = "+".join(c); r["weights"] = w.round(3).to_dict(); rows.append(r)
d = pd.DataFrame(rows).set_index("sleeves")
pd.set_option("display.width", 220); pd.set_option("display.max_colwidth", 80)
print("\nequal-risk blends (10 % IS vol, net 5 bp):"); print(d.round(3).to_string())
d.to_csv(os.path.join(HERE, "blend_results.csv"))

# headline = all four; sensitivity with TXT_res instead of TXT
for c in (base, ["RM", "QVC", "TXT_res", "REC"]):
    iv = 1 / S.loc[:"2017", c].std(); w = iv / iv.sum()
    b = (S[c] * w).sum(axis=1); lev = 0.10 / (b.loc[:"2017"].std() * np.sqrt(252)); b = b * lev
    print("\n", "+".join(c), "weights (unlevered)", w.round(3).to_dict(), "sleeve leverage x%.2f" % lev)
    print("  ", {k: round(v, 3) for k, v in stats(b).items()})
    print("   yearly Sharpe:", b.groupby(b.index.year).apply(sh).round(2).to_dict())
    if c == base:
        b.to_frame("blend4").to_parquet(os.path.join(HERE, "nets_0_blend4.parquet"))
        wts, levx = w, lev
# per-sleeve capital multipliers in the headline blend (units: each sleeve's own book as backtested)
print("\nheadline blend = sum_k m_k * sleeve_k with m =", (wts * levx).round(3).to_dict())
