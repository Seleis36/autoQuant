"""Re-framing: Halloween sector rotation (Jacobsen & Visaltanachoti 2009), spec fixed by
the paper, not fitted: cyclicals {XLY, XLI, XLB, XLK, XLF} vs defensives {XLP, XLU, XLV}.
Nov-Apr long cyclicals / short defensives, May-Oct the reverse. Dollar-neutral and
beta-neutral (SPY hedge) versions; also the one-sided variant (Nov-Apr only, flat otherwise).
Checked on the French proxies 1946-1998 (holdout) and traded on the ETFs 1999-2026."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx, french

CYC = ["XLY", "XLI", "XLB", "XLK", "XLF"]
DEF = ["XLP", "XLU", "XLV"]
fr = french.sector_returns()
winter = lambda idx: np.isin(idx.month, [11, 12, 1, 2, 3, 4])

# proxies (monthly): weight for month m decided at end of m-1
spread = fr[CYC].mean(axis=1) - fr[DEF].mean(axis=1)
sgn = pd.Series(np.where(winter(fr.index), 1.0, -1.0), index=fr.index)
for a, b in [("1946", "1998"), ("1999", "2014"), ("2015", "2026")]:
    x = (sgn * spread).loc[a:b]; y = spread.loc[a:b][winter(spread.loc[a:b].index)]
    print(f"proxy {a}-{b}: two-sided Sh {x.mean()/x.std()*np.sqrt(12):.2f} ({x.mean()*1200:.1f}%/yr)"
          f" | winter-only Sh {y.mean()/y.std()*np.sqrt(12):.2f}  | spread winter-summer {spread.loc[a:b][winter(spread.loc[a:b].index)].mean()*100:.2f} vs {spread.loc[a:b][~winter(spread.loc[a:b].index)].mean()*100:.2f} %/mo")

# ETFs (daily): the position for day d+1 is known at close d; month of d+1 decides
c = data.load_panel()
r = c.pct_change()
beta = sx.beta_to(r[data.SECTORS], r["SPY"], halflife=126).fillna(1.0)
nxt = pd.Series(c.index, index=c.index).shift(-1).fillna(c.index[-1] + pd.Timedelta(days=1))
wint = pd.Series(winter(pd.DatetimeIndex(nxt.values)), index=c.index)
rows = []
for mode in ["two-sided", "winter-only"]:
    for hedge in ["dollar", "beta"]:
        w = pd.DataFrame(0.0, index=c.index, columns=data.SECTORS + ["SPY"])
        s = np.where(wint, 1.0, -1.0 if mode == "two-sided" else 0.0)
        for t in CYC: w[t] = 0.5 / len(CYC) * s
        for t in DEF: w[t] = -0.5 / len(DEF) * s
        if hedge == "beta":
            w["SPY"] = -(w[data.SECTORS] * beta).sum(axis=1)
        st, net = sx.summary(w, c, name=f"{mode}|{hedge}")
        rows.append(st)
print(sx.fmt(pd.DataFrame(rows)))
