"""cross-asset-tsmom, round 2 -- correlation-regime-aware cross-asset signal.

PSV's negative equity->bond predictor is, economically, "the bond keeps moving the way the
equity move implies" -- which is the opposite direction once the stock-bond correlation turns
positive (2022-). Re-framing with the sign of the trailing beta:
    imp_L  = sign(beta_252d(bond on equity) x equity L-month return)   (implied-move continuation)
    combo2 = (own_L + imp_L) / 2
beta from daily returns over the trailing 252 days ending at the signal month-end.
Also a demeaned version of every signal (subtract its own expanding mean position) so the
drift of the 1985-2009 bond bull market does not count as timing skill.
Same book, split and costs as 01_screen.py.
"""
import os, sys
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, _HERE)
from importlib import import_module
s1 = import_module("01_screen")
pd.set_option("display.width", 220)

syn, etf, eq = s1.data()
rows = []
for name, bond in (("syn10", syn[10]), ("IEF", etf["IEF"]), ("TLT", etf["TLT"])):
    b = bond.dropna(); e = eq.reindex(b.index)
    beta_d = b.rolling(252, min_periods=200).cov(e) / e.rolling(252, min_periods=200).var()
    me_dates = b.groupby(b.index.to_period("M")).apply(lambda s: s.index.max())
    beta_m = beta_d.groupby(beta_d.index.to_period("M")).last()
    for L in (1, 3, 6, 12):
        own = np.sign(s1.cum(b, None, L))
        eqL = s1.cum(eq, None, L).reindex(own.index)
        imp = np.sign(beta_m.reindex(own.index) * eqL)
        psv = -np.sign(eqL)
        for sname, sig in (("psv_eq", psv), ("imp", imp), ("combo_psv", (own + psv) / 2),
                           ("combo_imp", (own + imp) / 2)):
            for dm in (False, True):
                sg = sig.copy()
                if dm:
                    sg = sg - sg.expanding(min_periods=36).mean().shift(1)
                sg = sg.reindex(me_dates.index); sg.index = me_dates.values
                net, we = s1.book(sg.dropna(), b)
                rows.append(dict(inst=name, L=L, sig=sname, demean=dm, IS=s1.sh(net.loc["1985":"2009"]),
                                 OOS=s1.sh(net.loc["2010":]), OOS18=s1.sh(net.loc["2018":]),
                                 y22_26=s1.sh(net.loc["2022":])))
t = pd.DataFrame(rows)
t.to_csv(os.path.join(_HERE, "02_beta_regime.csv"), index=False)
print(t.round(2).to_string(index=False))
print("\nshare of months with positive trailing stock-bond beta (syn10):")
b = syn[10].dropna(); e = eq.reindex(b.index)
bd = (b.rolling(252).cov(e) / e.rolling(252).var()).groupby(b.index.year).last()
print((bd > 0).astype(int).to_string())
