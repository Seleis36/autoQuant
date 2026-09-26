"""Robustness of the ensemble (lag-1 slope): COT timing spot-check, extra-lag placebo,
cost sensitivity, block bootstrap, deflated Sharpe, vectorbt cross-check, rolling alpha."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
import vc_data as vc, research_lib as rl
import fetch_cot_vix as cot
from cot_lib import weekly_nets, zscore

P = vc.panel()
W, av = weekly_nets()
# 1. timing spot-check around Volmageddon / Aug-2024
feat = pd.DataFrame({"am": W["am_net"]})
mapped = cot.on_session_rows(pd.Series(W.index, index=W.index, name="asof"), P.index, av)
for d in ["2018-02-02", "2018-02-05", "2018-02-06", "2024-08-02", "2024-08-05", "2024-11-29", "2024-12-02", "2024-12-03"]:
    print(d, pd.Timestamp(d).day_name(), "uses report as-of", mapped.loc[d].date() if pd.notna(mapped.loc[d]) else None)

def ens_weights(extra_weeks=0, lag=1, ths=(-0.5, 0, 0.25, 0.5, 1.0)):
    Z = {}
    for w in (52, 104, 156):
        Z[f"am{w}"] = zscore(W["am_net"], w, int(w * .67))
    for w in (104, 156):
        Z[f"comp{w}"] = (zscore(W["am_net"], w, int(w * .67)) - zscore(W["lev_net"], w, int(w * .67))) / 2
    Z = pd.DataFrame(Z).shift(extra_weeks)
    S = cot.on_session_rows(Z, P.index, av)
    cont = (P["VIX3M"] / P["VIX"]).shift(lag) > 1
    ws = [np.where(cont & (S[c] > th), -1.0, 0.0) for c in S for th in ths]
    return pd.Series(np.mean(ws, axis=0), index=P.index)

rows = {}
for k in (0, 1, 2, 4, 8, 13, 26, 52):
    net, st = vc.bt(ens_weights(k), P["VIXY"], 5)
    rows[f"extra lag {k}w"] = vc.split_row(net)
print(pd.DataFrame(rows).T.round(2))

w = ens_weights(0)
for c in (0, 5, 10, 20, 40):
    net, st = vc.bt(w, P["VIXY"], c)
    print(f"cost {c}bp: Sh {vc.sh(net):.2f} OOS {vc.sh(net.loc[vc.OOS[0]:]):.2f}")
net, st = vc.bt(w, P["VIXY"], 5)
print(st.round(3).to_dict())

# block bootstrap of Sharpe (21-day blocks)
rng = np.random.default_rng(0)
x = net.loc["2011-01-01":].values
n, B = len(x), 21
sims = []
for _ in range(2000):
    starts = rng.integers(0, n - B, size=n // B + 1)
    s = np.concatenate([x[i:i + B] for i in starts])[:n]
    sims.append(s.mean() / s.std() * np.sqrt(252))
sims = np.array(sims)
print("bootstrap Sharpe 5/50/95: %.2f %.2f %.2f  P(>0.5) %.2f P(>1) %.2f" % (
    *np.percentile(sims, [5, 50, 95]), (sims > 0.5).mean(), (sims > 1).mean()))
stt = rl.perf_stats(net, ann=252)
for N in (1, 25, 100, 150):
    print("DSR N=%d: %.3f" % (N, rl.deflated_sharpe(stt["Sharpe"], len(net), N, skew=stt["Skew"], kurt=stt["Kurt"] + 3, ann=252)))

# vectorbt cross-check (short allowed; |w| <= 1 so no margin issue)
import vectorbt as vbt
px = P["VIXY"]
pf = vbt.Portfolio.from_orders(px, size=w, size_type="targetpercent", direction="both",
                               fees=5e-4, init_cash=1e6, freq="1D")
vr = pf.returns()
# research_lib applies w_t to r_{t+1}; vbt fills at close t -> same timing
print("vectorbt Sharpe %.3f vs research_lib %.3f, corr %.4f" % (vc.sh(vr), vc.sh(net), vr.corr(net)))
