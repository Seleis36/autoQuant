"""exp04 — validation of the base cell (-raw log global L/S account ratio, q30, beta-neutral,
7-day tranches, PIT top-20, 10 bp).

1. Leg decomposition (gross): long leg minus EW universe, EW universe minus short leg.
2. Correlation with the live crypto-alts alt-sleeve-blend (its research weights) and its sleeves.
3. Lookahead truncation test: weights computed on data truncated at T must equal the
   full-sample weights at T (every input is cut at T, including the metrics archive).
4. Deflated Sharpe at the number of configurations evaluated in exp01-exp03.
5. Stationary block bootstrap of the daily Sharpe (10-day blocks).
6. Rolling 12-month Sharpe, worst days, exposure stats.
"""
import os
import sys
import importlib.util
import numpy as np
import pandas as pd

from common import (load, btc_beta, beta_neutral, quantile_ls, tranche, evaluate, IS, OOS,
                    FULL, ROOT)
import research_lib as rl

close, vol, met, mask = load()
beta = btc_beta(close)
x = np.log(met["count_long_short_ratio"])


def weights(x, close, mask, beta):
    return tranche(beta_neutral(quantile_ls(-x, mask), beta), 7)


w = weights(x, close, mask, beta)
net, row = evaluate(w, close, "base")
st = rl.perf_stats(net.loc[FULL[0]:])
print("BASE", {k: round(v, 3) for k, v in row.items() if k != "name"})
print("full stats:", st.round(3).to_dict())

# 1. legs (gross)
ret = close.pct_change(fill_method=None)
we = w.shift(1)
ew = ret.where(mask.shift(1).fillna(False).astype(bool)).mean(axis=1)
lw, sw = we.clip(lower=0), -we.clip(upper=0)
long_r = (lw * ret.fillna(0)).sum(axis=1) / lw.sum(axis=1).replace(0, np.nan)
short_r = (sw * ret.fillna(0)).sum(axis=1) / sw.sum(axis=1).replace(0, np.nan)
for nm, s in {"long - EW": long_r - ew, "EW - short": ew - short_r}.items():
    s = s.loc[FULL[0]:]
    print(f"{nm:10s} SR full {rl.perf_stats(s)['Sharpe']:.2f} IS {rl.perf_stats(s.loc[:IS[1]])['Sharpe']:.2f} "
          f"OOS {rl.perf_stats(s.loc[OOS[0]:])['Sharpe']:.2f}")
print("avg long gross", round(lw.loc[FULL[0]:].sum(axis=1).mean(), 3), "avg short gross",
      round(sw.loc[FULL[0]:].sum(axis=1).mean(), 3), "avg net", round(we.loc[FULL[0]:].sum(axis=1).mean(), 3))
pb = (we * beta.shift(1)).sum(axis=1).loc[FULL[0]:]
print("avg ex-ante BTC beta", round(pb.mean(), 3), "| realised beta to BTC",
      round(np.polyfit(ret["BTC-USD"].loc[net.index].loc[FULL[0]:].fillna(0), net.loc[FULL[0]:], 1)[0], 3))

# 2. correlation with the live alt-sleeve-blend and its sleeves
p = os.path.join(ROOT, "code", "crypto-alts", "alt-sleeve-blend", "weights_final.parquet")
if os.path.exists(p):
    wb = pd.read_parquet(p)
    sys.path.insert(0, os.path.join(ROOT, "code", "crypto-alts", "shared"))
    import universe as uv
    cb = uv.clean_close(uv.load_panel(list(wb.columns))["Close"])
    nb, _ = rl.backtest_xs(wb, cb, 10.0)
    both = pd.concat([net, nb.rename("blend")], axis=1).loc[FULL[0]:].dropna()
    print("corr with alt-sleeve-blend (daily):", round(both.corr().iloc[0, 1], 3),
          "| blend SR same window:", round(rl.perf_stats(both["blend"])["Sharpe"], 2))
    for k, (a, b) in {"IS": IS, "OOS": OOS}.items():
        seg = both.loc[a:b]
        print(f"  {k}: corr {seg.corr().iloc[0, 1]:.2f}")
    # 50/50 at equal vol
    s1, s2 = both.iloc[:, 0], both["blend"]
    comb = 0.5 * s1 / s1.std() + 0.5 * s2 / s2.std()
    for k, (a, b) in {"full": FULL, "IS": IS, "OOS": OOS}.items():
        print(f"  equal-risk combo {k}: SR {rl.perf_stats(comb.loc[a:b])['Sharpe']:.2f}"
              f"  (blend alone {rl.perf_stats(s2.loc[a:b])['Sharpe']:.2f})")

# 3. truncation test
import metrics_panel as mp  # noqa: E402
bad = 0
for T in ["2022-09-30", "2023-06-15", "2024-05-01", "2025-03-20", "2026-01-10"]:
    ct, vt = close.loc[:T], vol.loc[:T]
    xt = x.loc[:T]
    mt = mask.loc[:T]          # mask uses only rolling/cumulative past data; recomputed below
    # recompute mask from truncated inputs
    med = vt.rolling(90, min_periods=45).median()
    hist = ct.notna().cumsum()
    has_m = met["count_long_short_ratio"].loc[:T].notna().cumsum() >= 60
    elig = (hist >= 120) & (med >= 1e6) & ct.notna() & has_m & met["count_long_short_ratio"].loc[:T].notna()
    mt = (med.where(elig).rank(axis=1, ascending=False) <= 20) & elig
    wt = weights(xt, ct, mt, btc_beta(ct))
    d = (wt.iloc[-1] - w.loc[T]).abs().max()
    bad += d > 1e-12
    print(f"truncation {T}: max |w_trunc - w_full| = {d:.2e}")
# the daily metrics row D only uses stamps < D 23:00: verify on raw 5-min data for one coin
m5 = mp.load_metrics("DOGEUSDT")
D = pd.Timestamp("2024-03-05")
raw_last = m5.loc[:D + pd.Timedelta(hours=22, minutes=59), "count_long_short_ratio"].iloc[-1]
print("DOGE 2024-03-05 daily value", met["count_long_short_ratio"].loc[D, "DOGE-USD"], "== last stamp <23:00", raw_last)
print("truncation failures:", bad)

# 4. deflated Sharpe
n_trials = 20 + 22 + 15
for k, (a, b) in {"full": FULL, "OOS": OOS}.items():
    s = net.loc[a:b]
    ps = rl.perf_stats(s)
    print(f"DSR {k} (N={n_trials}):", round(rl.deflated_sharpe(ps['Sharpe'], len(s), n_trials, ps['Skew'], ps['Kurt'] + 3), 3))

# 5. bootstrap
rng = np.random.default_rng(0)
r = net.loc[FULL[0]:].values
n, B, L = len(r), 2000, 10
srs = []
for _ in range(B):
    idx = []
    while len(idx) < n:
        s0 = rng.integers(0, n)
        idx.extend(range(s0, min(s0 + L, n)))
    rr = r[np.array(idx[:n])]
    srs.append(rr.mean() / rr.std() * np.sqrt(365))
print("bootstrap SR 5/50/95%:", np.round(np.percentile(srs, [5, 50, 95]), 2), "P(SR>0.5)=", np.mean(np.array(srs) > 0.5))

# 6. rolling and tails
roll = net.loc[FULL[0]:].rolling(365).apply(lambda v: v.mean() / v.std() * np.sqrt(365))
print("rolling-12m SR min/median:", round(roll.min(), 2), round(roll.median(), 2))
print("worst days:", net.loc[FULL[0]:].nsmallest(5).round(4).to_dict())
print("monthly hit rate:", round((net.loc[FULL[0]:].resample("ME").sum() > 0).mean(), 2))
net.to_frame("retail_crowding_xs").to_parquet("exp04_net.parquet")
w.to_parquet("exp04_weights.parquet")
