"""exp02 — the one consistent cell of exp01: ETH falls in the hours before a month-end expiry
(T-8h..T: -50 bp IS, -76 bp OOS). Is it real?

1. Hour-by-hour path T-24h..T+8h, month-end vs weekly Fridays vs Tuesday placebo.
2. Robustness of the window (entry T-12h..T-2h, exit T or T+1h), per year, and per class.
3. BTC replication (same expiry clock), and a pre-options placebo: last Fridays 2017-09 -> 2019-12.
4. Is it the Friday-00:00 UTC window in general, or month-end in general? Controls: every Friday,
   the last Thursday/Wednesday of the month, the last calendar days of the month.
5. Costed: a short-only event sleeve (sim book, 10 bp/side) and a veto on the live trend filter.
"""
import numpy as np
import pandas as pd

import common as c
from common import ek

pd.set_option("display.width", 260)
H, D = pd.Timedelta(hours=1), pd.Timedelta(days=1)
p = c.price_at("ETHUSDT", start="2017-08-17")
pb = c.price_at("BTCUSDT", start="2017-08-17")
end = p.index.max() - 1 * D
ex = c.expiries(end)
me, wk = ex.index[ex != "weekly"], ex.index[ex == "weekly"]
pl = c.placebo_times(end)
IS, OOS = (c.START, c.IS_END), (c.OOS_START, None)


def ms(x):
    x = x.dropna()
    return f"{x.mean() * 1e4:+6.0f} ({x.mean() / x.std() * np.sqrt(len(x)):+.1f}, n {len(x)}, hit {np.mean(x < 0):.2f})" if len(x) > 4 else "n/a"


# ---------------------------------------------------------------- 1. hourly path
print("1. mean hourly log return (bp) around T: month-end | weekly | Tuesday placebo, full sample 2020+")
rows = []
for k in range(-24, 8):
    r = [c.window_ret(p, t, k * H, (k + 1) * H) for t in (me, wk, pl)]
    rows.append({"hour": f"T{k:+d}h", "month-end": r[0].mean() * 1e4, "t": r[0].mean() / r[0].std() * np.sqrt(r[0].notna().sum()),
                 "weekly": r[1].mean() * 1e4, "placebo": r[2].mean() * 1e4})
hp = pd.DataFrame(rows).set_index("hour")
hp["cum month-end"] = hp["month-end"].cumsum()
hp["cum weekly"] = hp["weekly"].cumsum()
print(hp.round(1).to_string())

# ---------------------------------------------------------------- 2. window robustness
print("\n2. month-end expiries, ETH log return by window: IS | OOS")
for a in (-16, -12, -8, -6, -4, -2):
    for b in (0, 1):
        x = c.window_ret(p, me, a * H, b * H)
        print(f"  T{a:+d}h..T{b:+d}h   IS {ms(x.loc[IS[0]:IS[1]])}   OOS {ms(x.loc[OOS[0]:])}")
x8 = c.window_ret(p, me, -8 * H, 0 * H)
print("by year (bp, n, share negative):")
print(pd.DataFrame({"bp": x8.groupby(x8.index.year).mean() * 1e4, "n": x8.groupby(x8.index.year).count(),
                    "neg": x8.groupby(x8.index.year).apply(lambda s: (s < 0).mean())}).round(2).T.to_string())
print("by class:")
for k in ("quarterly", "monthly"):
    xx = c.window_ret(p, ex.index[ex == k], -8 * H, 0 * H)
    print(f"  {k:9s} IS {ms(xx.loc[IS[0]:IS[1]])}   OOS {ms(xx.loc[OOS[0]:])}")

# ---------------------------------------------------------------- 3. BTC and pre-options placebo
print("\n3. BTC, same clock, T-8h..T")
xb = c.window_ret(pb, me, -8 * H, 0 * H)
xbw = c.window_ret(pb, wk, -8 * H, 0 * H)
print(f"  BTC month-end  IS {ms(xb.loc[IS[0]:IS[1]])}   OOS {ms(xb.loc[OOS[0]:])}")
print(f"  BTC weekly     IS {ms(xbw.loc[IS[0]:IS[1]])}   OOS {ms(xbw.loc[OOS[0]:])}")
rel = x8 - xb
print(f"  ETH minus BTC  IS {ms(rel.loc[IS[0]:IS[1]])}   OOS {ms(rel.loc[OOS[0]:])}")
old = c.expiries("2019-12-31", start="2017-09-01")
xo = c.window_ret(p, old.index[old != "weekly"], -8 * H, 0 * H)
xow = c.window_ret(p, old.index[old == "weekly"], -8 * H, 0 * H)
print(f"  pre-options placebo 2017-09..2019-12: last Fridays {ms(xo)}; other Fridays {ms(xow)}")

# ---------------------------------------------------------------- 4. controls
print("\n4. controls, 00:00-08:00 UTC log return, 2020+: IS | OOS")
days = pd.date_range(c.START, end.normalize(), freq="D")
t8 = days + 8 * H
allr = c.window_ret(p, t8, -8 * H, 0 * H)
dow = pd.Series(days.weekday, index=t8)
month_last = pd.Series(days, index=t8).groupby([days.year, days.month]).transform("max").dt.normalize()
dfe = pd.Series((month_last.to_numpy() - days.to_numpy()) / np.timedelta64(1, "D"), index=t8)     # calendar days to month end


def last_wd(wd):
    d = days[days.weekday == wd]
    s = pd.Series(d, index=d)
    return (s[s.groupby([d.year, d.month]).transform("max") == s].index) + 8 * H


ctrl = {"all days": allr, "all Fridays": allr[dow == 4], "Fridays not month-end": allr.reindex(wk),
        "last Friday (= month-end expiry)": allr.reindex(me),
        "last Thursday of month": allr.reindex(last_wd(3)), "last Wednesday of month": allr.reindex(last_wd(2)),
        "last Monday of month": allr.reindex(last_wd(0)),
        "last 7 calendar days, not Friday": allr[(dfe <= 6) & (dow != 4)],
        "first Friday of month": allr.reindex(pd.DatetimeIndex([g.min() for _, g in pd.Series(t8[dow == 4]).groupby([t8[dow == 4].year, t8[dow == 4].month])]))}
for k, x in ctrl.items():
    print(f"  {k:34s} IS {ms(x.loc[IS[0]:IS[1]])}   OOS {ms(x.loc[OOS[0]:])}")

# permutation: pick one random Friday per month, 5000 times; how often is the mean <= observed in BOTH halves?
rng = np.random.default_rng(11)
fr = allr[dow == 4].dropna()
grp = fr.groupby([fr.index.year, fr.index.month])
obs_is, obs_oos = x8.loc[IS[0]:IS[1]].mean(), x8.loc[OOS[0]:].mean()
cnt = cnt_full = 0
obs_full = x8.mean()
vals = [g.to_numpy() for _, g in grp]
is_mask = np.array([k[0] <= 2023 for k, _ in grp])
N = 5000
for _ in range(N):
    pick = np.array([v[rng.integers(len(v))] for v in vals])
    if pick[is_mask].mean() <= obs_is and pick[~is_mask].mean() <= obs_oos:
        cnt += 1
    if pick.mean() <= obs_full:
        cnt_full += 1
print(f"\npermutation (random Friday of each month, {N} draws): P(mean <= observed in both halves) = {cnt / N:.4f}; "
      f"P(full-sample mean <= observed {obs_full * 1e4:.0f} bp) = {cnt_full / N:.4f}")

# ---------------------------------------------------------------- 5. costed
print("\n5. costed (10 bp/side). Hourly book; bar stamped t covers [t, t+1h)")
h = ek.ed.bars("ETHUSDT", "1h", start="2019-11-01")["Close"]
idx = h.index
short = pd.Series(0.0, index=idx)
for t in me:
    # hold the short over bars stamped T-8h .. T-1h: weight set on the bar before (backtest shifts by one)
    short.loc[(idx >= t - 9 * H) & (idx < t - 1 * H)] = -1.0
netS, stS = ek.ed.bt(short, h)
dS = ek.ed.to_daily(netS).loc[c.START:]
for k, (a, b) in {"Full": (c.START, None), "IS": IS, "OOS": OOS}.items():
    s = dS.loc[a:b]
    print(f"  short ETH T-8h..T on month-end expiries: {k} Sharpe {s.mean() / s.std() * np.sqrt(365):+.2f}, ann ret {s.mean() * 365 * 100:+.1f}%, "
          f"per event {netS.loc[a:b].sum() / max(len(me[(me >= pd.Timestamp(a)) & (me <= (pd.Timestamp(b) if b else me.max()))]), 1) * 1e4:+.0f} bp")
for cst in (0, 5, 10, 20):
    n_, _ = ek.ed.bt(short, h, cost_bps=cst)
    d_ = ek.ed.to_daily(n_).loc[c.START:]
    print(f"    cost {cst:>2} bp: full Sharpe {d_.mean() / d_.std() * np.sqrt(365):+.2f}")

# veto on the live trend filter: flat over the same eight hours
eth_d = ek.daily()["Close"]
tfd = ek.baselines(eth_d)["TF_live"]
# daily weight w[D] is held over day D+1 -> hourly bars of day D+1; hourly weight at bar t is held over bar t+1
wh = tfd.reindex(idx.floor("D") - D).set_axis(idx).fillna(0.0)          # weight in force during the bar stamped t
w_hold = wh.shift(-1).fillna(0.0)                                        # research_lib convention: w[t] held over bar t+1
veto = w_hold.copy()
for t in me:
    veto.loc[(idx >= t - 9 * H) & (idx < t - 1 * H)] = 0.0
rows = {}
for nm, w_ in (("TF_live (hourly book)", w_hold), ("TF_live, flat T-8h..T at month-end expiry", veto)):
    n_, _ = ek.ed.bt(w_, h)
    d_ = ek.ed.to_daily(n_).loc[c.START:]
    eq = (1 + d_).cumprod()
    rows[nm] = {k: d_.loc[a:b].mean() / d_.loc[a:b].std() * np.sqrt(365) for k, (a, b) in {"Full": (c.START, None), "IS": IS, "OOS": OOS}.items()}
    rows[nm]["MDD"] = (eq / eq.cummax() - 1).min()
    rows[nm]["CAGR"] = eq.iloc[-1] ** (365 / len(d_)) - 1
print(pd.DataFrame(rows).T.round(3).to_string())
print(f"  corr(short sleeve, TF_live) daily: {dS.corr(ek.ed.to_daily(ek.ed.bt(w_hold, h)[0]).loc[c.START:]):+.2f}")
