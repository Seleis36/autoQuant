"""Re-framings of the signed-volume flow proxy (SAV5 = AV5 x sign(hedged 5d return)):
(a) extreme events: z(SAV5) beyond +-1.5 (252d own history) -> fade the hedged spread for the
    next 5 sessions after a 1-session skip; per-name equal risk, 5 bp ETF / 1 bp SPY;
(b) weekly XS: every 5 sessions, rank-linear fade of SAV5 across the 11 ETFs (hedged);
(c) aggregate: abnormal $volume of the ex-US complex (sum over the 11) signed by the EW hedged
    5d return -> fade the EW basket vs SPY for 5 sessions."""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
import data as D

NAMES = ["EWJ", "EWG", "EWU", "EWZ", "EWY", "EWA", "EWC", "FXI", "INDA", "EFA", "EEM"]
SPL = {"FULL": ("2001-06-01", "2026-12-31"), "IS": ("2001-06-01", "2012-12-31"), "OOS": ("2013-01-01", "2026-12-31")}
C = D.load_panel(NAMES + ["SPY"], "Close", start="1998-12-01")
V = D.load_panel(NAMES + ["SPY"], "Volume", start="1998-12-01")
R = C.pct_change(); x = R["SPY"]
beta = pd.DataFrame({n: R[n].rolling(252, min_periods=126).cov(x) / x.rolling(252, min_periods=126).var() for n in NAMES})
H = R[NAMES] - beta.shift(1).mul(x, axis=0)
DV = (C * V)[NAMES]
AV5 = np.log(DV.rolling(5).mean() / DV.shift(5).rolling(63, min_periods=40).mean())
RV5 = np.log1p(H).rolling(5).sum()
SAV = AV5 * np.sign(RV5)
z = (SAV - SAV.rolling(252, min_periods=126).mean()) / SAV.rolling(252, min_periods=126).std()
hv = H.rolling(126, min_periods=60).std() * np.sqrt(252)

def spread_to_w(P):
    W = P.copy(); W["SPY"] = -(P * beta.reindex(P.index)[NAMES].fillna(1.0)).sum(axis=1); return W
def run(W, name):
    ret = C[W.columns].pct_change().fillna(0.0); We = W.shift(1).fillna(0.0)
    dW = (We - We.shift(1).fillna(0.0)).abs(); cst = pd.Series(5.0, index=W.columns); cst["SPY"] = 1.0
    net = (We * ret).sum(axis=1) - (dW * cst / 1e4).sum(axis=1); g = (We * ret).sum(axis=1)
    s = {pn: round(net.loc[a:b].mean() / net.loc[a:b].std() * np.sqrt(252), 2) for pn, (a, b) in SPL.items()}
    sg = round(g.loc["2001-06":].mean() / g.loc["2001-06":].std() * np.sqrt(252), 2)
    print(f"{name:45s} net {s}  gross_full {sg}  turn/yr {dW.sum(axis=1).loc['2001-06':].sum() / 25.5:.0f}")

# (a) events: position = -sign(z) * (0.10/hv)/n for 5 sessions after a 1-session skip
for thr in [1.5, 2.0]:
    ev = (-np.sign(z)).where(z.abs() > thr, 0.0).fillna(0.0)
    P = sum(ev.shift(k) for k in range(1, 6)) / 5.0          # weight set at close t+k (skip handled: entry at t+1 close)
    P = (P * 0.10 / hv).fillna(0.0) / 3.0
    run(spread_to_w(P), f"(a) events |z|>{thr}, fade 5d after 1-skip")
# (b) weekly XS rank fade
reb = C.index[::5]
rk = SAV.reindex(reb).rank(axis=1); rk = rk.sub(rk.mean(axis=1), axis=0); rk = rk.div(rk.abs().sum(axis=1), axis=0)
P = (-rk).reindex(C.index).ffill().shift(1).fillna(0.0)
run(spread_to_w(P), "(b) weekly XS rank fade of SAV5 (1-skip)")
# (c) aggregate ex-US flow proxy
agg_dv = DV.sum(axis=1, min_count=3)
aav = np.log(agg_dv.rolling(5).mean() / agg_dv.shift(5).rolling(63, min_periods=40).mean())
ew = H.mean(axis=1); s_agg = aav * np.sign(np.log1p(ew).rolling(5).sum())
za = (s_agg - s_agg.rolling(252, min_periods=126).mean()) / s_agg.rolling(252, min_periods=126).std()
pos = (-za.clip(-2, 2) / 2).reindex(reb).reindex(C.index).ffill().shift(1).fillna(0.0)
av = C[NAMES[:9]].notna(); wb = av.astype(float).div(av.sum(axis=1), axis=0)
P = wb.mul(pos, axis=0); P = P.reindex(columns=NAMES, fill_value=0.0)
run(spread_to_w(P), "(c) aggregate ex-US flow fade, weekly (1-skip)")
