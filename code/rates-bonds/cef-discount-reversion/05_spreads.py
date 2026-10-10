"""What does a trade in these funds really cost? Effective-spread estimates from daily OHLC.

  tick   : one cent / price                          (lower bound on the quoted spread)
  AR     : Abdi-Ranaldo (2017) close-high-low, monthly  S = 2 sqrt(max(E[(c-eta_t)(c-eta_t+1)],0))
  roll   : Roll (1984), monthly                      S = 2 sqrt(max(-cov(dp_t, dp_t-1), 0))
  CS     : Corwin-Schultz (2012) two-day high-low, monthly mean with negatives set to 0

Reported as FULL spread in bp; the cost per side of a marketable order is half of it.
Saves a per-fund monthly half-spread panel (AR, floored at half a tick) for 06.
"""
import numpy as np
import pandas as pd
import cef_lib as cl

pd.set_option("display.width", 220)
d = cl.load()
c, h, l = np.log(d["close"]), np.log(d["high"]), np.log(d["low"])
mask = cl.liquid_mask(d, 1e6)
month = c.index.to_period("M")

tick = 0.01 / d["close"]

eta = (h + l) / 2
prod = (c - eta) * (c - eta.shift(-1))
ar = 2 * np.sqrt(prod.groupby(month).mean().clip(lower=0))

dp = c.diff()
cov = (dp * dp.shift(1)).groupby(month).mean() - dp.groupby(month).mean() * dp.shift(1).groupby(month).mean()
roll = 2 * np.sqrt((-cov).clip(lower=0))

beta = (h - l) ** 2 + (h.shift(-1) - l.shift(-1)) ** 2
gamma = (np.maximum(h, h.shift(-1)) - np.minimum(l, l.shift(-1))) ** 2
k = 3 - 2 * np.sqrt(2)
alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
cs = (2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))).clip(lower=0).groupby(month).mean()

mm = mask.groupby(month).mean() > 0.5
tk = tick.groupby(month).mean()
rows = {}
for name, s in (("tick", tk), ("AR", ar), ("roll", roll), ("CS", cs)):
    x = s.where(mm) * 1e4
    y = x.groupby(x.index.year).apply(lambda f: pd.Series({"med": np.nanmedian(f.values), "mean": np.nanmean(f.values),
                                                            "p75": np.nanpercentile(f.values, 75)}))
    rows[name] = y.unstack()
out = pd.concat(rows, axis=1).round(1)
print("FULL spread estimates in bp, liquid universe (>= $1M median daily volume), by year")
print(out.to_string())

half = (np.maximum(ar, tk) / 2)
half.index = half.index.to_timestamp()
half.to_parquet("05_half_spread_monthly.parquet")
print("\nhalf-spread (max(AR, tick)/2) bp, liquid universe: median %.1f  mean %.1f  p75 %.1f  p90 %.1f" % (
    np.nanmedian((half.values * 1e4)[mm.values]), np.nanmean((half.values * 1e4)[mm.values]),
    np.nanpercentile((half.values * 1e4)[mm.values], 75), np.nanpercentile((half.values * 1e4)[mm.values], 90)))
print("price level of liquid funds: median $%.2f" % np.nanmedian(d["close"].where(mask).values))
