"""Calendar books: long the chosen equity basket on days inside pre-specified windows,
flat otherwise. The weight set at close t uses the features of day t+1 (known at t:
month-end position, scheduled FOMC calendar, holiday calendar).
Windows (all literature-fixed, not fitted):
  TOM13   tdom in [-1, +3]          Lakonishok-Smidt 1988, McConnell-Xu 2008
  TOM33   tdom in [-3, +3]          Etula-Rinne-Suominen-Vaittinen 2020 (dash for cash)
  PREF    FOMC statement day and the day before  (Lucca-Moench 2015 pre-FOMC drift)
  PREH    last trading day before a weekday holiday (Ariel 1990)
  EVEN    CMVJ 2019 even FOMC-cycle weeks (0, 2, 4, 6)
Baskets: SPY, EW sectors, the 4 highest-beta sectors (EWM-126 beta, lagged).
"""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
import data, sxlib as sx, cal

c = data.load_panel()
S = data.SECTORS
r = c.pct_change()
fn = cal.next_day_features(c.index)              # features of day t+1, on row t
# the last row's "next day" is unknown to shift(-1); rebuild it from a synthetic next bday
fl = cal.features(c.index.append(pd.DatetimeIndex([c.index[-1] + pd.offsets.BDay(1)])))
fn.iloc[-1] = fl.iloc[-1]

td = fn["tdom"]; fo = fn["fomc_off"]; tf = fn["to_fomc"]
win = {
    "TOM13": td.between(-1, 3) & (td != 0),
    "TOM33": td.between(-3, 3) & (td != 0),
    "PREF": (fo == 0) | (tf == -1),
    "PREH": fn["pre_hol"].astype(bool),
    "EVEN": pd.Series(np.floor((fo + 1) / 5), index=fn.index).isin([0, 2, 4, 6]),
}
beta = sx.beta_to(r[S], r["SPY"], 126)
hib = (beta.rank(axis=1, ascending=False) <= 4) & c[S].notna()

def basket(name):
    if name == "SPY":
        w = pd.DataFrame(0.0, index=c.index, columns=S + ["SPY"]); w["SPY"] = 1.0; return w
    if name == "EW":
        m = c[S].notna().astype(float)
    else:
        m = hib.astype(float)
    w = m.div(m.sum(axis=1), axis=0).fillna(0); w["SPY"] = 0.0
    return w

combos = {
    "TOM13": ["TOM13"], "TOM33": ["TOM33"], "PREF": ["PREF"], "PREH": ["PREH"], "EVEN": ["EVEN"],
    "TOM13+PREF": ["TOM13", "PREF"], "TOM33+PREF": ["TOM33", "PREF"],
    "TOM13+PREF+PREH": ["TOM13", "PREF", "PREH"], "TOM33+PREF+PREH": ["TOM33", "PREF", "PREH"],
    "ALL": ["TOM33", "PREF", "PREH", "EVEN"],
}
rows = []
for bk in ["SPY", "EW", "HIBETA"]:
    B = basket(bk)
    bh, _ = sx.summary(B, c, name=f"{bk}|buyhold"); bh["TimeIn"] = 1.0; rows.append(bh)
    for cn, parts in combos.items():
        on = pd.concat([win[p] for p in parts], axis=1).any(axis=1).astype(float)
        W = B.mul(on, axis=0)
        st, net = sx.summary(W, c, name=f"{bk}|{cn}")
        st["TimeIn"] = on.loc["1999":].mean()
        rows.append(st)
        # complement (out-of-window) for reference
        Wc = B.mul(1 - on, axis=0)
        stc, _ = sx.summary(Wc, c, name=f"{bk}|NOT {cn}")
        stc["TimeIn"] = 1 - on.loc["1999":].mean()
        if cn in ("TOM33+PREF+PREH", "ALL"):
            rows.append(stc)
df = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
print(sx.fmt(df))
df.to_csv(os.path.join(os.path.dirname(__file__), "books.csv"))
