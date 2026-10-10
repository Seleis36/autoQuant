"""Data sanity: coverage, NAV staleness and timestamp, discount distribution, liquidity."""
import numpy as np
import pandas as pd
import cef_lib as cl

d = cl.load("2000-01-01")
close, nav, disc, ret, dv = d["close"], d["nav"], d["disc"], d["ret"], d["dv"]
print("funds:", close.shape[1], d["group"].value_counts().to_dict())

yr = disc.index.year
cov = pd.DataFrame({
    "n_price": close.notna().groupby(yr).mean().sum(axis=1).round(0),
    "n_disc": disc.notna().groupby(yr).mean().sum(axis=1).round(0),
    "n_liq1m": cl.liquid_mask(d, 1e6).groupby(yr).mean().sum(axis=1).round(0),
    "n_liq500k": cl.liquid_mask(d, 5e5).groupby(yr).mean().sum(axis=1).round(0),
    "med_disc%": (disc.groupby(yr).median().median(axis=1) * 100).round(2),
    "xs_std%": (disc.std(axis=1).groupby(yr).mean() * 100).round(2),
    "med_dv_$m": (dv.groupby(yr).median().median(axis=1) / 1e6).round(2),
})
print(cov.to_string())

# NAV staleness: share of days the NAV print is unchanged
nr = nav.pct_change(fill_method=None)
print("\nshare of NAV prints unchanged vs prior day, by year:")
print(((nr == 0).sum(axis=1) / nr.notna().sum(axis=1)).groupby(yr).mean().round(3).to_string())

# NAV timestamp: is nav[t] struck on t? regress fund NAV return on same-day / next-day ETF
import research_lib as rl
mub = rl.load_series("MUB")["Close"].pct_change()
hyg = rl.load_series("HYG")["Close"].pct_change()
for g, bench in [("muni", mub), ("taxable", hyg)]:
    cols = d["group"].index[d["group"] == g]
    x = nr[cols].loc["2012":].mean(axis=1)
    df = pd.DataFrame({"nav": x, "b0": bench, "b_lag1": bench.shift(1), "b_lead1": bench.shift(-1)}).dropna()
    print(g, "corr of avg NAV return with bench same-day / bench t-1 / bench t+1:",
          df.corr()["nav"].round(3).to_dict())

# raw price short-term reversal vs discount: autocorr of discount changes
dd = disc.diff()
print("\npooled AR(1) of daily discount change:", round(pd.concat([dd.stack(), dd.shift(1).stack()], axis=1).dropna().corr().iloc[0, 1], 3))
print("discount half-life proxy -- pooled autocorr of the 250d z-score at 1/5/21/63 days:")
z = cl.zscore(disc, 250)
for h in (1, 5, 21, 63):
    a = pd.concat([z.stack(), z.shift(h).stack()], axis=1).dropna()
    print(h, round(a.corr().iloc[0, 1], 3))
