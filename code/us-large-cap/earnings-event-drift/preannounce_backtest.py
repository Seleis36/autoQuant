"""Upper-bound backtest of the pre-announcement run-up: long every stock in the 5 bars
before its earnings reaction bar, sector-hedged (short equal notional spread over the
other names in the sector), dollar-neutral, gross 1.0 when >= 20 events, else scaled.
Uses the *actual* announcement date as the expected date (mild lookahead: dates are
usually confirmed 2-4 weeks ahead, so this is an upper bound on what is tradable)."""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from panel import load_panel
from xs_lib import *
from earnings import load_earnings, reaction_day_matrix, window_matrix

P = load_panel()
C, M = P["close"], P["member"]
sec = P["sector"].fillna("UNK")
ret = C.pct_change()
mask = M & C.notna()
E = load_earnings()
R = reaction_day_matrix(E, C.index, C.columns) & mask

def sector_hedge(w_event):
    out = w_event.copy()
    for g, cols in sec.reindex(C.columns).groupby(sec.reindex(C.columns)).groups.items():
        cols = [c for c in cols if c in C.columns]
        sub = w_event[cols]; tot = sub.sum(axis=1)
        m = mask[cols] & (sub == 0); n = m.sum(axis=1).replace(0, np.nan)
        out[cols] = sub - m.astype(float).mul(tot / n, axis=0).fillna(0.0)
    return out.fillna(0.0)

rows = []; series = {}
for before, after in [(5, -1), (3, -1), (5, 0), (1, -1), (10, -1)]:
    # position held at close t if reaction bar is in (t+1 .. t+before) i.e. we hold the bars [-before, -1] ... after=-1
    # window_matrix flags bars within [-before,+after] of R; we want to HOLD from close of bar -before-1? Simpler:
    # weight at close t = 1 if bar t+1 is within [-before, after] of a reaction bar (so return of t+1 is earned).
    W = window_matrix(R, before=before, after=max(after, 0)) if after >= 0 else window_matrix(R, before=before, after=0) & ~R
    hold = W.shift(-1, fill_value=False)       # bar t+1 in window  -> lookahead of the calendar only
    n = hold.sum(axis=1)
    w_ev = hold.astype(float).div(n.replace(0, np.nan), axis=0).fillna(0.0) * 0.5
    w_ev = w_ev.mul((n / 20).clip(upper=1.0), axis=0)          # scale down thin days
    w = sector_hedge(w_ev)
    for cb in [5.0, 2.0, 0.0]:
        net, st = xs_backtest(w, ret, cost_bps=cb)
        sp = split_perf(net, SPLITS)
        rows.append({"window": f"[-{before},{after}]", "cost": cb, "Sharpe": st["Sharpe"], "IS": sp.loc["IS", "Sharpe"], "OOS": sp.loc["OOS", "Sharpe"],
                     "CAGR": st["CAGR"], "Vol": st["Vol"], "MaxDD": st["MaxDD"], "turn": st["Turnover_ann"], "avgGross": st["AvgGross"], "names": (w_ev != 0).sum(axis=1).mean()})
        if cb == 5.0: series[f"[-{before},{after}] net5bp"] = net
        if cb == 0.0 and before == 5 and after == -1: series["[-5,-1] gross"] = net
df = pd.DataFrame(rows).round(3); print(df.to_string()); df.to_csv(os.path.join(HERE, "preannounce_results.csv"), index=False)
fig, ax = plt.subplots(figsize=(9, 4.5))
for k, s in series.items(): ax.plot((1 + s).cumprod(), label=k, lw=1.2)
ax.set_title("Pre-announcement long, sector-hedged: growth of $1"); ax.legend(fontsize=8); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(HERE, "..", "..", "..", "alphas", "us-large-cap", "earnings-event-drift", "01_preannounce_equity.png"), dpi=110)
# event profile figure
prof = pd.read_csv(os.path.join(HERE, "event_profile.csv"), index_col=0)
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
ax[0].bar(prof.index, prof.mean_bp, color=np.where(prof.index == 0, "#c44", "#4a7")); ax[0].set_title("Mean sector-residual return by event day (bp)"); ax[0].axhline(0, c="k", lw=.5)
ax[1].plot(prof.index, prof.cumIS, label="IS 2010-17"); ax[1].plot(prof.index, prof.cumOOS, label="OOS 2018-26"); ax[1].plot(prof.index, prof.cum_bp, "k--", label="full")
ax[1].axvline(0, c="#c44", lw=.7); ax[1].set_title("Cumulative from k=-45 (bp)"); ax[1].legend(); ax[1].grid(alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(HERE, "..", "..", "..", "alphas", "us-large-cap", "earnings-event-drift", "02_event_profile.png"), dpi=110)
