"""calendar-flow-ensemble: combine pre-specified calendar/flow sleeves on the G10 basket.

Bar convention (verified in screens/probe_timing2.py): the yfinance row stamped D closes at
00:00 UTC on D and covers UTC calendar day D-1 ("session" D-1). Macro rows stamped <= D-1
(US close 20:00/21:00 UTC) are known before the FX row D closes, so a weight set at row D may
use macro data stamped <= D-1. Weight at row D earns the FX return of row D+1.
"""
import sys, os, json, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "screens")); from common import *   # noqa
sys.path.insert(0, HERE); from strategy import sleeve_weights, target_weights, DEFAULTS   # noqa
from research_lib import deflated_sharpe
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

COST = 2.0
fx_raw = load_fx_usd_per_ccy()
mac_raw = load_closes(["SPY", "TLT"])
sl = sleeve_weights(fx_raw, mac_raw)
print("sleeves:", list(sl))
rows = {}
for k, W in sl.items():
    net, st = bt(W.reindex(idx).fillna(0), r, COST, k); v = vs(net)
    rows[k] = dict(Sharpe=st["Sharpe"], Gross=st["GrossSharpe"], IS=v["IS"], OOS=v["OOS"], t=st["t_NW"], Turn=st["Turn"], Expo=st["Gross"])
Wt = target_weights(fx_raw, mac_raw).reindex(idx).fillna(0)
net, st = bt(Wt, r, COST, "ensemble"); v = vs(net)
rows["ENSEMBLE"] = dict(Sharpe=st["Sharpe"], Gross=st["GrossSharpe"], IS=v["IS"], OOS=v["OOS"], t=st["t_NW"], Turn=st["Turn"], Expo=st["Gross"])
tab = pd.DataFrame(rows).T.round(2); print(tab.to_string())
print("\nENSEMBLE full stats:\n", st.round(3).to_string())
print("max gross exposure:", Wt.abs().sum(axis=1).max().round(2), " mean:", Wt.abs().sum(axis=1).mean().round(2))
# cost sensitivity
for cb in [0, 2, 5, 10]:
    n2, s2 = bt(Wt, r, cb, "e"); print(f"cost {cb}bp: Sharpe {s2['Sharpe']:.2f} CAGR {s2['CAGR']*100:.2f}% MDD {s2['MaxDD']*100:.1f}%")
# yearly
print("\nby year Sharpe:", net.groupby(net.index.year).apply(lambda x: x.mean()/x.std()*np.sqrt(ANN)).round(2).to_dict())
# sleeve correlation
sn = pd.DataFrame({k: bt(W.reindex(idx).fillna(0), r, COST, k)[0] for k, W in sl.items()})
print("\nsleeve net-return correlations:\n", sn.corr().round(2).to_string())
# walk-forward: nothing is fitted except the LOYO seasonality sign (already out-of-sample by construction);
# so "walk-forward" == full sample. Report the 2020+ segment as the untouched OOS.
# bootstrap (block, 21d) of the OOS Sharpe
rng = np.random.default_rng(0); oos = net.loc["2020":].values; B = 21; nb = len(oos)//B
shs = []
for _ in range(2000):
    starts = rng.integers(0, len(oos)-B, nb); x = np.concatenate([oos[s:s+B] for s in starts]); shs.append(x.mean()/x.std()*np.sqrt(ANN))
shs = np.array(shs); print(f"\nOOS Sharpe bootstrap: mean {shs.mean():.2f}  5% {np.percentile(shs,5):.2f}  95% {np.percentile(shs,95):.2f}  P(>0) {(shs>0).mean():.2f}  P(>1) {(shs>1).mean():.2f}  P(>2) {(shs>2).mean():.3f}")
n_trials = int(sys.argv[1]) if len(sys.argv) > 1 else 200
print(f"deflated Sharpe prob (full, n_trials={n_trials}):", round(deflated_sharpe(st["Sharpe"], len(net), n_trials, st["Skew"], st["Kurt"]+3, ANN), 3))
# figures
eq = (1+net).cumprod(); eqs = (1+sn).cumprod()
fig, ax = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
ax[0].plot(eq, lw=2, color="k", label=f"ensemble (Sharpe {st['Sharpe']:.2f})")
for k in eqs: ax[0].plot(eqs[k], lw=0.8, alpha=0.7, label=k)
ax[0].axvline(pd.Timestamp("2020-01-01"), color="r", ls="--", lw=0.8); ax[0].legend(fontsize=8); ax[0].set_title("calendar-flow-ensemble, 2 bp/side, IS | OOS split at 2020")
ax[1].plot(eq/eq.cummax()-1, color="k"); ax[1].set_title("drawdown"); plt.tight_layout(); plt.savefig(os.path.join(HERE, '..', '..', '..', 'past_research', 'fx-majors', 'calendar-flow-ensemble', 'ensemble_equity.png'), dpi=110)
fig, ax = plt.subplots(figsize=(9, 4)); tab[["IS", "OOS"]].plot.bar(ax=ax); ax.axhline(2.0, color="r", ls="--", label="target 2.0"); ax.axhline(0, color="k", lw=0.5); ax.legend(); ax.set_ylabel("Sharpe"); plt.tight_layout(); plt.savefig(os.path.join(HERE, '..', '..', '..', 'past_research', 'fx-majors', 'calendar-flow-ensemble', 'sleeves_sharpe.png'), dpi=110)
