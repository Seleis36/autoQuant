"""Residual of VIXY's daily return vs SPY (rolling beta) -> forward VIXY / hedged returns.
Everything uses 16:00 ET closes (VIXY, VIXM, SPY): no index-timing issue."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
import vc_data as vc

P = vc.panel()
R = P[["VIXY", "VIXM", "SPY"]].pct_change()
def roll_beta(y, x, win=63):
    c = y.rolling(win).cov(x); v = x.rolling(win).var()
    return c / v
b = roll_beta(R["VIXY"], R["SPY"]).shift(1)            # beta known before day t
res = R["VIXY"] - b * R["SPY"]
sd = res.rolling(63).std().shift(1)
z = res / sd
# forward returns: next-day VIXY, next-day hedged (VIXY - beta*SPY)
b_now = roll_beta(R["VIXY"], R["SPY"])                  # beta known at close t for next-day hedge
fwd_vixy = R["VIXY"].shift(-1)
fwd_hedged = (R["VIXY"] - b_now.shift(0) * R["SPY"]).shift(-1)
fwd_hedged = R["VIXY"].shift(-1) - b_now * R["SPY"].shift(-1)
out = []
for k, (a, bnd) in {"IS": vc.IS, "OOS": vc.OOS}.items():
    for nm, f in (("vixy", fwd_vixy), ("hedged", fwd_hedged)):
        for lagsum in (1, 2, 3, 5):
            zz = z.rolling(lagsum).sum() / np.sqrt(lagsum)
            d = pd.concat([zz, f], axis=1).loc[a:bnd].dropna()
            ic = d.iloc[:, 0].corr(d.iloc[:, 1], method="spearman")
            q = pd.qcut(d.iloc[:, 0], 5, labels=False)
            m = d.iloc[:, 1].groupby(q).mean() * 1e4
            out.append({"win": k, "tgt": nm, "sum": lagsum, "ic": ic, **{f"q{i}": m.iloc[i] for i in range(5)}})
pd.set_option("display.width", 200)
print(pd.DataFrame(out).round(3))
# also: raw VIXY return reversal and SPY-return -> next-day VIXY
for k, (a, bnd) in {"IS": vc.IS, "OOS": vc.OOS}.items():
    d = pd.concat([R["VIXY"], R["SPY"], fwd_vixy.rename("f"), fwd_hedged.rename("fh")], axis=1).loc[a:bnd].dropna()
    print(k, "IC raw VIXY->next VIXY %.3f | SPY->next VIXY %.3f | SPY->next hedged %.3f" % (
        d["VIXY"].corr(d["f"], method="spearman"), d["SPY"].corr(d["f"], method="spearman"),
        d["SPY"].corr(d["fh"], method="spearman")))
print("beta describe", b.describe().round(2).to_dict())
