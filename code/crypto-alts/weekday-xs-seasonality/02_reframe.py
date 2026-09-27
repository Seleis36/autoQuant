"""Re-framings with less turnover / more estimation data:
 (a) weekend-vs-weekday coin seasonality: signal = past mean XS return on Sat+Sun minus on
     Mon-Fri (L weeks); hold the signal during the weekend, its negative during the week;
 (b) expanding-window same-weekday mean of beta-residual returns (all history, min 26 obs);
 (c) turn-of-month coin seasonality (days 1-3 vs rest), expanding window.
Everything at 0 and 10 bp; also the weekday-seasonality IC by year."""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared")); sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
import research_lib as rl, study as S

d = S.load(); c, m, ret = d["c_alt"], d["mask"], d["ret"]
btc = d["btc"]; br = btc.pct_change(); beta = S.ewm_beta(ret, br, 60)
xr = ret.sub(ret.where(m).mean(axis=1), axis=0)
res_r = ret - beta.shift(1).mul(br, axis=0)                   # beta-residual return
res_r = res_r.sub(res_r.where(m).mean(axis=1), axis=0)
idx = c.index
dow = pd.Series(idx.dayofweek, index=idx)                    # Mon=0 .. Sun=6
wkend = dow.isin([5, 6])
nxt_wkend = wkend.shift(-1, fill_value=False)                 # is day D+1 a weekend day

rows = []
def add(w, name):
    for cost in (0, 10):
        net, st = S.bt(w, c, cost=cost)
        r = S.row(net, f"{name}|{cost}bp"); r["turn"] = st["Turnover_ann"]; rows.append(r)

# (a) weekend-minus-weekday
for L in (13, 26, 52, 104):
    we = xr.mul(np.where(wkend, 1.0, np.nan), axis=0).rolling(7 * L, min_periods=L).mean()
    wd = xr.mul(np.where(~wkend, 1.0, np.nan), axis=0).rolling(7 * L, min_periods=L).mean()
    spread = we - wd
    s = spread.mul(np.where(nxt_wkend, 1.0, -1.0), axis=0)
    add(rl.linear_weights(rl.rank_xs(s, m), m), f"wkend_vs_wkday L{L}")

# (b) expanding same-weekday mean of residual returns
for src, nm in ((xr, "xr"), (res_r, "resid")):
    acc = pd.DataFrame(0.0, index=idx, columns=c.columns); cnt = pd.DataFrame(0.0, index=idx, columns=c.columns)
    s = pd.DataFrame(np.nan, index=idx, columns=c.columns)
    for k in range(7):                                        # for each weekday of D+1
        sel = (dow == k)
        x = src.mul(np.where(sel, 1.0, np.nan), axis=0)                                    # returns on weekday k
        mu = x.expanding(min_periods=1).mean()                # past mean incl. up to the last k-day
        n = x.notna().cumsum()
        mu = mu.where(n >= 26)
        # at close D where D+1 is weekday k, use mu as of D
        tgt = dow.shift(-1) == k
        cond = pd.DataFrame(np.repeat(tgt.values[:, None], s.shape[1], axis=1), index=idx, columns=s.columns)
        s = s.mask(cond, mu.ffill())
    add(rl.linear_weights(rl.rank_xs(s, m), m), f"sameweekday_expanding_{nm}")

# (c) turn-of-month: coins' historical excess on days 1-3 of month vs rest
dom = pd.Series(idx.day, index=idx)
tom = dom <= 3
nxt_tom = tom.shift(-1, fill_value=False)
a = xr.mul(np.where(tom, 1.0, np.nan), axis=0).expanding(min_periods=30).mean(); b = xr.mul(np.where(~tom, 1.0, np.nan), axis=0).expanding(min_periods=100).mean()
s = (a - b).ffill().mul(np.where(nxt_tom, 1.0, -1.0), axis=0)
add(rl.linear_weights(rl.rank_xs(s, m), m), "turn_of_month_expanding")

res = pd.DataFrame(rows).set_index("name")
pd.set_option("display.width", 250)
print(res.round(2).to_string())
res.to_csv("reframe_02.csv")
