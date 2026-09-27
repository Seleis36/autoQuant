"""Cross-sectional same-weekday seasonality (Long, Zaremba, Demir, Szczygielski & Vasenin 2020,
FRL 35). Signal for trading day D+1: mean of each coin's past XS-demeaned returns on the same
weekday as D+1 over the last L weeks (excluding the most recent occurrence optionally).
Weight set at close D, earns return of D+1. Daily rebalancing by construction."""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared")); sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
import research_lib as rl, study as S

d = S.load(); c, m, ret = d["c_alt"], d["mask"], d["ret"]
btc = d["btc"]; beta = S.ewm_beta(ret, btc.pct_change(), 60)
xr = ret.sub(ret.where(m).mean(axis=1), axis=0)         # XS-demeaned daily returns


def same_weekday_mean(L, skip=0):
    """At close D: average of xr on days D+1-7j, j=1..L (same weekday as D+1), past only."""
    acc = sum(xr.shift(7 * j - 1) for j in range(1 + skip, L + 1 + skip))
    return acc / L


rows = []
for L in (4, 8, 13, 26, 52):
    s = same_weekday_mean(L)
    # IC vs next-day xr
    fwd = xr.shift(-1)
    sm = s.where(m); ok = sm.notna() & fwd.notna()
    rs = sm.where(ok).rank(axis=1); rf = fwd.where(ok).rank(axis=1)
    rs = rs.sub(rs.mean(axis=1), axis=0); rf = rf.sub(rf.mean(axis=1), axis=0)
    ic = ((rs * rf).sum(axis=1) / np.sqrt((rs ** 2).sum(axis=1) * (rf ** 2).sum(axis=1))).dropna()
    for cost in (0, 10):
        for scheme in ("linear", "tercile"):
            w = rl.linear_weights(rl.rank_xs(s, m), m) if scheme == "linear" else rl.quantile_weights(s, m, 0.3)
            net, st = S.bt(w, c, cost=cost)
            r = S.row(net, f"L{L}|{scheme}|{cost}bp")
            r.update(IC_IS=ic.loc[S.IS[0]:S.IS[1]].mean(), IC_OOS=ic.loc[S.OOS[0]:].mean(),
                     tIC_full=rl.newey_west_t(ic.values, 5), turn=st["Turnover_ann"])
            rows.append(r)
res = pd.DataFrame(rows).set_index("name")
pd.set_option("display.width", 250)
print(res.round(3).to_string())
res.to_csv("screen_01.csv")
