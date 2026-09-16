"""Screen 4: asymmetric event book -- short extreme sector-residual winners (and/or long
extreme losers), hold H days, hedged with the sector-neutralising long/short residual so
the book is dollar-neutral. Return per trade vs cost."""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
from panel import load_panel
from xs_lib import *

P = load_panel()
C, M = P["close"], P["member"]
sec = P["sector"].fillna("UNK")
ret = C.pct_change(); logret = np.log(C).diff()
hist_ok = C.notna().rolling(60).sum().ge(55)
mask = M & hist_ok & C.notna()
def cum(n): return (C / C.shift(n) - 1)
def sres(x): return group_demean(x, sec, mask)
vol20 = logret.rolling(20).std()
print("residual daily ret std (sanity):", sres(ret).where(mask).stack().std().round(4))

def sector_hedge(w_event):
    """Offset each event position with the opposite exposure spread equally over the
    other masked names in the same sector -> sector-neutral, dollar-neutral."""
    out = w_event.copy()
    for g, cols in sec.reindex(C.columns).groupby(sec.reindex(C.columns)).groups.items():
        cols = [c for c in cols if c in C.columns]
        sub = w_event[cols]
        tot = sub.sum(axis=1)
        m = mask[cols] & (sub == 0)
        n = m.sum(axis=1).replace(0, np.nan)
        out[cols] = sub - m.astype(float).mul(tot / n, axis=0).fillna(0.0)
    return out.fillna(0.0)

rows = []
for win in [1, 3, 5]:
    z = sres(cum(win)).div(vol20.shift(win) * np.sqrt(win)).where(mask)
    for thr in [1.5, 2.0, 2.5, 3.0]:
        for side in ["short_winners", "long_losers", "both"]:
            ev_s = (z > thr).astype(float); ev_l = (z < -thr).astype(float)
            raw = -ev_s if side == "short_winners" else (ev_l if side == "long_losers" else ev_l - ev_s)
            for hold in [3, 5, 10]:
                # each event held `hold` days, equal notional per event-day; scale book to gross 1 on average
                pos = raw.rolling(hold, min_periods=1).sum().clip(-1, 1)
                n = pos.abs().sum(axis=1).replace(0, np.nan)
                w_ev = pos.div(n, axis=0).fillna(0.0) * 0.5           # events = half the gross
                w = sector_hedge(w_ev)
                net, st = xs_backtest(w, ret, cost_bps=5.0); g, gs = xs_backtest(w, ret, cost_bps=0.0)
                sp = split_perf(net, SPLITS)
                rows.append({"win": win, "thr": thr, "side": side, "hold": hold, "gross": gs["Sharpe"], "net5": st["Sharpe"],
                             "IS": sp.loc["IS", "Sharpe"], "OOS": sp.loc["OOS", "Sharpe"], "turn": st["Turnover_ann"],
                             "vol": st["Vol"], "cagr": st["CAGR"], "names": (w_ev != 0).sum(axis=1).mean()})
    print("win", win, "done", flush=True)
df = pd.DataFrame(rows).round(3)
df.to_csv(os.path.join(HERE, "screen4_results.csv"), index=False)
print(df.sort_values("net5", ascending=False).head(25).to_string())
print(df[df.side == "short_winners"].sort_values("net5", ascending=False).head(10).to_string())
