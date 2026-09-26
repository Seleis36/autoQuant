"""Re-framing: hold pair A (short UVXY / long L*VIXY, 5- or 10-session static hold) only when VIX(t-1)
exceeds a threshold -- the drag edge scales with variance, borrow does not."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
import vc_data as vc

P = vc.panel().loc["2011-10-05":]
px = P[["UVXY", "VIXY"]]
chg = pd.Timestamp("2018-02-28")
Lu = pd.Series(np.where(P.index < chg, 2.0, 1.5), index=P.index)
vix1 = P["VIX"].shift(1)

def sim(H, gate, cost_bps=5.0, borrow=0.0):
    cap, sh, rets = 1.0, pd.Series(0.0, index=px.columns), []
    for i, t in enumerate(px.index):
        p = px.loc[t]
        if i > 0:
            prev = px.iloc[i - 1]
            pnl = (sh * (p - prev)).sum() - (-(sh.clip(upper=0)) * prev).sum() * borrow / 252
            rets.append(pnl / cap); cap += pnl
        if i % H == 0 or t == chg:
            on = bool(gate.loc[t])
            w = pd.Series({"UVXY": -1.0, "VIXY": Lu[t]}) / (1 + Lu[t]) if on else pd.Series({"UVXY": 0.0, "VIXY": 0.0})
            new = w * cap / p
            cap -= (abs(new - sh) * p).sum() * cost_bps / 1e4
            sh = new
    return pd.Series([0.0] + rets, index=px.index)

rows = {}
for H in (5, 10):
    for th in (0, 18, 22, 26):
        g = vix1 > th
        for b in (0.0, 0.05, 0.10):
            r = sim(H, g, borrow=b)
            rows[(H, th, b)] = vc.split_row(r, {"vol": r.std() * np.sqrt(252), "on": g.mean()})
res = pd.DataFrame(rows).T; res.index.names = ["H", "VIX>", "borrow"]
pd.set_option("display.width", 200); pd.set_option("display.max_rows", 100)
print(res.round(3))
