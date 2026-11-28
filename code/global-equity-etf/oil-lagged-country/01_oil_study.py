"""Step 1: does last month's WTI change predict next month's equity return?
(a) time series: slope of r(m+1) on oil(m) for SPY, BASKET, WORLD, EFA, EEM, each country;
    ETF era IS/OOS and backcast 1988-2000.
(b) cross-section: country oil beta (60m rolling, contemporaneous) -> does the next-month
    return of high-beta (exporter) countries exceed low-beta ones after oil rises?"""
import numpy as np, pandas as pd
from ol_lib import oil_monthly, etf_monthly, back_monthly, ols_t, sr_m, SPL, BACK, COUNTRIES

oil = oil_monthly()
R = etf_monthly()
B = back_monthly()
pd.set_option("display.width", 200)
print("oil monthly: ", oil.index.min().date(), oil.index.max().date(), "std", round(oil.std(), 3))

rows = {}
for c in ["SPY", "BASKET", "WORLD", "EFA", "EEM"] + COUNTRIES:
    r = {}
    for pn, (a, b) in SPL.items():
        bt, t, n = ols_t(R[c].shift(-1).loc[a:b], oil.loc[a:b])
        r[pn] = f"{bt:6.3f} ({t:5.2f}) n={n}"
    rows[c] = r
for c in ["US", "BASKET", "WORLD", "JP", "UK", "CA", "AU", "HK"]:
    bt, t, n = ols_t(B[c].shift(-1).loc[BACK["1988-2000"][0]:BACK["1988-2000"][1]], oil.loc["1988":"2000"])
    rows.setdefault("BACK " + c, {})["1988-2000"] = f"{bt:6.3f} ({t:5.2f}) n={n}"
print("\n=== slope of next-month return on this month's log oil change (t)")
print(pd.DataFrame(rows).T.to_string())

# ---- placebo: contemporaneous and 2-month lag
for lag, lab in [(0, "contemporaneous"), (-2, "two months ahead")]:
    r = {pn: "%6.3f (%5.2f)" % ols_t(R["WORLD"].shift(lag).loc[a:b], oil.loc[a:b])[:2] for pn, (a, b) in SPL.items()}
    print(f"WORLD {lab}: {r}")

# ---- cross-section: oil beta x oil change
Rc = R[COUNTRIES]
ob = Rc.rolling(60, min_periods=36).cov(oil) .div(oil.rolling(60, min_periods=36).var(), axis=0)
print("\nmean 60m oil beta by country (2001-2026):", ob.loc["2005":].mean().round(3).to_dict())
sig = ob.mul(oil, axis=0)                     # expected continuation of month-m oil news
xs = sig.sub(sig.mean(axis=1), axis=0)
nxt = Rc.shift(-1).sub(Rc.shift(-1).mean(axis=1), axis=0)
# pooled IC
for pn, (a, b) in SPL.items():
    s, y = xs.loc[a:b].stack(), nxt.loc[a:b].stack()
    d = pd.concat([s, y], axis=1).dropna()
    ic = d.groupby(level=0).apply(lambda g: g.iloc[:, 0].rank().corr(g.iloc[:, 1].rank()) if len(g) > 3 else np.nan).dropna()
    print(f"XS rank IC {pn}: mean {ic.mean():.3f}, t {ic.mean() / ic.std() * np.sqrt(len(ic)):.2f}, n {len(ic)}")
