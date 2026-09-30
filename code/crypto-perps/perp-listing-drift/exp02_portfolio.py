"""exp02 — the tradeable version: a basket of spot shorts opened at each perp listing.

Per event (spot trading on D0): short `size` of capital in the coin's Binance spot from the
close of D0+delay for H days, long `size` of BTC spot as the hedge (beta 1). Positions of
overlapping events add up. Pre-declared grid:
  H     in {14, 30, 60, 90}
  delay in {0, 1}       (enter at the close of D0 or D0+1)
  size  fixed 5 % per event, gross short capped at 1.0 (scaled down pro rata when exceeded)
  sizing alt: inverse-vol (0.2 % daily-vol contribution per event, cap 5 %) using the
        coin's trailing 30d spot vol (pre-listing history) -- only when >= 20 days exist
Costs 10 bp/side (20 / 30 bp sensitivity). A funding-adjusted line adds the funding a
SHORT-PERP implementation would have received (+rate) / paid (-rate) -- the sim book books
spot, so the headline is spot-only; the funding line is what a real perp short would earn.
"""
import numpy as np
import pandas as pd

from common import (load_listings, spot_close_panel, clean_close, daily_funding_sym, IS_END,
                    OOS_START)
import research_lib as rl

s = load_listings()
close = clean_close(spot_close_panel(sorted(set(s.spot_base) | {"BTC"})))
close = close.loc["2019-09-01":]
ret = close.pct_change(fill_method=None)
idx = close.index

ev = []
for _, e in s.iterrows():
    b = e.spot_base
    if b == "BTC" or b not in close or e.D0 not in idx or pd.isna(close.at[e.D0, b]):
        continue
    ev.append((e.symbol, b, e.D0))
print("events:", len(ev))


def book(H, delay=0, size=0.05, sizing="fixed", cap=1.0):
    """Target weights [date x coin] (known at the close of each date)."""
    w = pd.DataFrame(0.0, index=idx, columns=close.columns)
    vol30 = ret.rolling(30, min_periods=20).std()
    for sym, b, d0 in ev:
        i0 = idx.get_loc(d0) + delay
        if i0 >= len(idx):
            continue
        sl = idx[i0: i0 + H]
        sz = size
        if sizing == "invvol":
            v = vol30.at[idx[i0], b]
            if not np.isfinite(v) or v <= 0:
                continue
            sz = min(size, 0.002 / v)             # 0.2 % daily-vol contribution per event, cap 5 %
        # only while the coin still has a price
        alive = close[b].reindex(sl).notna()
        sl = sl[alive.values]
        w.loc[sl, b] -= sz
        w.loc[sl, "BTC"] += sz
    short = -w.drop(columns="BTC").clip(upper=0).sum(axis=1)
    scale = (cap / short).where(short > cap, 1.0)
    return w.mul(scale, axis=0)


def funding_pnl(w):
    """Funding a short-perp implementation would receive: sum over coins of -w * rate(D+1)."""
    out = pd.Series(0.0, index=idx)
    sym_of = {b: sym for sym, b, _ in ev}
    for b in w.columns:
        if b == "BTC" or not (w[b] != 0).any():
            continue
        f = daily_funding_sym(sym_of[b], lag_hours=0)   # settlements in (D, D+1] -> return row D
        if f is None:
            continue
        f = f.reindex(idx).fillna(0.0)
        out += (-w[b].shift(1).fillna(0.0)) * f       # short (w<0) receives +rate
    return out


rows = []
SPL = {"full": ("2020-01-01", "2026-12-31"), "IS": ("2020-01-01", IS_END), "OOS": (OOS_START, "2026-12-31")}


def evaluate(w, name, cost=10.0, fund=False):
    net, st = rl.backtest_xs(w, close, cost_bps=cost, name=name)
    if fund:
        net = net + funding_pnl(w).reindex(net.index).fillna(0.0)
    row = {"name": name}
    for k, (a, b) in SPL.items():
        ps = rl.perf_stats(net.loc[a:b])
        row[f"SR_{k}"] = ps["Sharpe"]
        if k != "full":
            row[f"CAGR_{k}"] = ps["CAGR"]
    ps = rl.perf_stats(net.loc[SPL["full"][0]:])
    row.update(CAGR=ps["CAGR"], MaxDD=ps["MaxDD"], Turn=st["Turnover_ann"],
               Gross=w.shift(1).abs().sum(axis=1).loc[SPL["full"][0]:].mean())
    rows.append(row)
    return net


nets = {}
for H in (14, 30, 60, 90):
    for delay in (0, 1):
        w = book(H, delay)
        nets[(H, delay)] = evaluate(w, f"H{H} d{delay} fixed5%")
for H in (30, 60, 90):
    evaluate(book(H, 0, sizing="invvol"), f"H{H} d0 invvol")
w60 = book(60, 0)
for c in (20, 30):
    evaluate(w60, f"H60 d0 fixed5% cost{c}", cost=c)
evaluate(w60, "H60 d0 fixed5% + short-perp funding", fund=True)
evaluate(book(90, 0), "H90 d0 fixed5% + short-perp funding", fund=True)
evaluate(book(30, 0), "H30 d0 fixed5% + short-perp funding", fund=True)

pd.set_option("display.width", 230)
res = pd.DataFrame(rows)
print(res.round(2).to_string(index=False))
res.to_csv("exp02_results.csv", index=False)
n = nets[(60, 0)]
print("H60 d0 yearly Sharpe:", n.loc["2020":].groupby(n.loc["2020":].index.year).apply(
    lambda r: round(r.mean() / r.std() * np.sqrt(365), 2) if r.std() > 0 else np.nan).to_dict())
print("H60 d0 yearly return:", n.loc["2020":].groupby(n.loc["2020":].index.year).sum().round(3).to_dict())
print("active events (H60) mean/max:", (w60.drop(columns='BTC') < 0).sum(axis=1).loc["2020":].mean().round(1),
      (w60.drop(columns='BTC') < 0).sum(axis=1).max())
print("worst days H60:", n.nsmallest(5).round(4).to_dict())
fp = funding_pnl(w60)
print("short-perp funding P&L H60, ann. by period:", {k: round(fp.loc[a:b].mean() * 365, 4) for k, (a, b) in SPL.items()})
