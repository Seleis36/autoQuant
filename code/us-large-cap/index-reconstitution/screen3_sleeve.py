"""Combined sparse event sleeve, fixed 0.25 of capital per event, sector-hedged, 5 bp:
  leg A: LONG quarterly-rebalance additions from the close of the first session after the
         first Friday of Mar/Jun/Sep/Dec (announcement already out) to the close of bar -1;
  leg B: SHORT every addition from the close of bar 0 (effective session) to the close of bar +5.
Both legs use only dates known before entry (quarterly schedule; effective date is announced)."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
import runpy
g = runpy.run_path(os.path.join(HERE, "screen2_quarterly.py"), run_name="q")
E, dates, A, nth_friday = g["E"], g["dates"], g["A"], g["nth_friday"]
es = runpy.run_path(os.path.join(HERE, "event_study.py"), run_name="es")
ret, mem, sec, tix = es["ret"], es["mem"], es["sec"], es["tix"]
from common import splits_row
from xs_lib import xs_backtest

secw = {}
for s, cols in sec.groupby(sec).groups.items():
    cols = [c for c in cols if c in tix]; m = mem[cols].astype(float)
    secw[s] = (cols, m.div(m.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0))
W = {"A": pd.DataFrame(0.0, index=dates, columns=tix), "B": pd.DataFrame(0.0, index=dates, columns=tix)}


def put(Wx, a, b, ticker, ci, sign, size=0.25):
    """hold `sign*size` of `ticker` at closes a..b-1 (earns bars a+1..b), hedged with its sector."""
    if b <= a:
        return
    Wx.iloc[a:b, ci] += sign * size
    s = sec.get(ticker, "UNK")
    if s in secw:
        cols, sw = secw[s]
        Wx.loc[Wx.index[a:b], cols] = Wx.loc[Wx.index[a:b], cols].values - sign * size * sw.iloc[a:b].values


for _, e in A.iterrows():
    if e.quarterly:
        f1 = nth_friday(e.eff.year, e.eff.month, 1)
        i_ann = dates.searchsorted(f1, side="right")
        put(W["A"], i_ann, e.ri - 1, e.ticker, e.ci, +1)
    put(W["B"], e.ri, min(e.ri + 5, len(dates) - 1), e.ticker, e.ci, -1)
W["A+B"] = W["A"] + W["B"]
rows = []; NET = {}
r = ret.fillna(0).loc["2011-01-01":]
for k, w in W.items():
    w = w.loc["2011-01-01":]
    for cost in (5.0, 0.0):
        net, st = xs_backtest(w, r, cost_bps=cost)
        row = splits_row(net, st); row.update({"leg": k, "cost": cost, "days_active": (w.abs().sum(axis=1) > 0).mean(),
                                               "max_gross": w.abs().sum(axis=1).max()})
        rows.append(row)
        if cost == 5.0:
            NET[k] = net
d = pd.DataFrame(rows).set_index(["leg", "cost"])
pd.set_option("display.width", 200)
print(d.round(3).to_string())
d.round(4).to_csv(os.path.join(HERE, "screen3_sleeve_results.csv"))
pd.DataFrame(NET).to_parquet(os.path.join(HERE, "nets_0_sleeve.parquet"))
