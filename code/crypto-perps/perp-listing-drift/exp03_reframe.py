"""exp03 — re-framings of the listing short (declared before running):

  A. age filter: only coins whose Binance spot pair is < 30 days old at the perp listing
     (the exp01 age split, the only bucket negative in both IS and OOS)
  B. squeeze stop: close an event's short once its close exceeds 1.5x the entry close
     (checked at each close, exit at that close; no re-entry)
  C. regime filter: open new events only while the EW top-20-alt / BTC ratio is below its
     200-day SMA (no alt season). Alt index = EW of the 20 coins with the largest trailing
     90d Binance spot quote volume (excluding BTC, ETH and stablecoins), past data only
  D. run-up filter: only events with a positive 30-day pre-listing abnormal return
Each at H = 30 and 60, delay 0, fixed 5 % per event, gross short cap 1.0, 10 bp.
"""
import numpy as np
import pandas as pd

from common import (load_listings, spot_close_panel, spot_qvol_panel, clean_close, IS_END,
                    OOS_START)
import research_lib as rl

s = load_listings()
bases = sorted(set(s.spot_base) | {"BTC", "ETH"})
close = clean_close(spot_close_panel(bases)).loc["2019-06-01":]
qv = spot_qvol_panel(bases).reindex_like(close)
ret = close.pct_change(fill_method=None)
idx = close.index
ab = ret.sub(ret["BTC"], axis=0)

# alt-season regime (past data only)
excl = {"BTC", "ETH"}
med = qv.drop(columns=[c for c in excl if c in qv]).rolling(90, min_periods=30).median()
top = med.rank(axis=1, ascending=False) <= 20
alt_ret = ret.drop(columns=[c for c in excl if c in ret]).where(top.shift(1).fillna(False).astype(bool)).mean(axis=1)
ratio = (1 + alt_ret.fillna(0)).cumprod() / close["BTC"] * close["BTC"].iloc[0]
no_altseason = ratio < ratio.rolling(200, min_periods=150).mean()
print("share of days with no alt season:", round(no_altseason.loc["2020":].mean(), 2))

ev = []
for _, e in s.iterrows():
    b = e.spot_base
    if b == "BTC" or b not in close or e.D0 not in idx or pd.isna(close.at[e.D0, b]):
        continue
    i0 = idx.get_loc(e.D0)
    runup = ab[b].iloc[max(0, i0 - 30): i0].sum()
    ev.append(dict(sym=e.symbol, b=b, d0=e.D0, age=e.spot_age, runup=runup,
                   regime=bool(no_altseason.get(e.D0, False))))
ev = pd.DataFrame(ev)
print("events:", len(ev), "| age<30d:", (ev.age < 30).sum(), "| no-altseason:", ev.regime.sum(),
      "| runup>0:", (ev.runup > 0).sum())


def book(E, H, size=0.05, cap=1.0, stop=None):
    w = pd.DataFrame(0.0, index=idx, columns=close.columns)
    for _, e in E.iterrows():
        i0 = idx.get_loc(e.d0)
        sl = idx[i0: i0 + H]
        px = close[e.b].reindex(sl)
        sl = sl[px.notna().values]
        if stop is not None and len(sl):
            entry = close.at[sl[0], e.b]
            hit = px.reindex(sl) > stop * entry
            if hit.any():
                sl = sl[: int(np.argmax(hit.values))]   # flat from the close where the stop hits
        w.loc[sl, e.b] -= size
        w.loc[sl, "BTC"] += size
    short = -w.drop(columns="BTC").clip(upper=0).sum(axis=1)
    return w.mul((cap / short).where(short > cap, 1.0), axis=0)


SPL = {"full": ("2020-01-01", "2026-12-31"), "IS": ("2020-01-01", IS_END), "OOS": (OOS_START, "2026-12-31")}
rows = []


def evaluate(w, name, cost=10.0):
    net, st = rl.backtest_xs(w, close, cost_bps=cost, name=name)
    row = {"name": name}
    for k, (a, b) in SPL.items():
        row[f"SR_{k}"] = rl.perf_stats(net.loc[a:b])["Sharpe"]
    ps = rl.perf_stats(net.loc[SPL["full"][0]:])
    row.update(CAGR=ps["CAGR"], MaxDD=ps["MaxDD"],
               MaxDD_IS=rl.perf_stats(net.loc[SPL["IS"][0]:SPL["IS"][1]])["MaxDD"],
               Gross=w.shift(1).abs().sum(axis=1).loc["2020":].mean())
    y = net.loc["2020":]
    row["worst_year"] = y.groupby(y.index.year).sum().min()
    rows.append(row)
    return net


nets = {}
for H in (30, 60):
    nets[("all", H)] = evaluate(book(ev, H), f"all events H{H}")
    nets[("young", H)] = evaluate(book(ev[ev.age < 30], H), f"A age<30d H{H}")
    nets[("stop", H)] = evaluate(book(ev, H, stop=1.5), f"B stop 1.5x H{H}")
    nets[("regime", H)] = evaluate(book(ev[ev.regime], H), f"C no-altseason H{H}")
    nets[("runup", H)] = evaluate(book(ev[ev.runup > 0], H), f"D runup>0 H{H}")
    evaluate(book(ev[ev.age < 30], H, stop=1.5), f"A+B age<30d stop H{H}")
pd.set_option("display.width", 230)
res = pd.DataFrame(rows)
print(res.round(2).to_string(index=False))
res.to_csv("exp03_results.csv", index=False)
for k in (("young", 30), ("young", 60)):
    n = nets[k].loc["2020":]
    print(k, "yearly Sharpe:", n.groupby(n.index.year).apply(lambda r: round(r.mean() / r.std() * np.sqrt(365), 2) if r.std() > 0 else np.nan).to_dict())
    print(k, "yearly return:", n.groupby(n.index.year).sum().round(3).to_dict())
ev.to_csv("exp03_events.csv", index=False)
