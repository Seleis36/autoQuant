"""Portfolio test: long every member name with a qualifying insider PURCHASE whose entry fell in
the last H trading days, equal weight, each long hedged dollar-for-dollar with its sector's EW
member basket (or the EW market). Optional short leg: names with qualifying SALES, hedged the
same way. Gross = 1 per leg when names are present; daily net at 5 bp/side."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
from common import sector_map, splits_row
from panel import load_panel
from xs_lib import xs_backtest

P = load_panel()
close = P["close"]; dates = close.index
ret = close.pct_change(fill_method=None)
mem = P["member"]
sec = sector_map(P)
E = pd.read_parquet("/tmp/insider_events.parquet")
tix = list(close.columns)

# sector basket weights: for each sector, EW over members
secw = {}
for s, cols in sec.groupby(sec).groups.items():
    cols = [c for c in cols if c in close.columns]
    m = mem[cols].astype(float)
    secw[s] = m.div(m.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
mkt = mem.astype(float).div(mem.sum(axis=1), axis=0)


def active(ev, H):
    """bool panel: an event entered within the last H bars (entry bar inclusive)."""
    A = pd.DataFrame(0.0, index=dates, columns=tix)
    ri = dates.get_indexer(ev.entry); ci = pd.Index(tix).get_indexer(ev.ticker)
    ok = (ri >= 0) & (ci >= 0)
    M = np.zeros(A.shape)
    np.add.at(M, (ri[ok], ci[ok]), 1.0)
    A[:] = M
    return (A.rolling(H, min_periods=1).sum() > 0) & mem


def book(flags, hedge="sector", side=1.0):
    n = flags.sum(axis=1)
    wl = flags.astype(float).div(n.replace(0, np.nan), axis=0).fillna(0.0) * 0.5 * side
    if hedge == "sector":
        wh = pd.DataFrame(0.0, index=dates, columns=tix)
        for s, cols in sec.groupby(sec).groups.items():
            cols = [c for c in cols if c in tix]
            expo = wl[cols].sum(axis=1)
            wh[cols] = wh[cols] - secw[s][cols].mul(expo, axis=0)
    else:
        wh = -mkt.mul(wl.sum(axis=1), axis=0)
    return wl + wh, n


SUBSETS = {
    "P_all": lambda e: (e.code == "P") & ~e.is_10pct_only,
    "P_officer": lambda e: (e.code == "P") & e.is_officer,
    "P_opportunistic": lambda e: (e.code == "P") & (e.cls == "opportunistic"),
    "P_nonroutine": lambda e: (e.code == "P") & ~e.is_10pct_only & (e.cls != "routine"),
    "P_cluster2": lambda e: (e.code == "P") & ~e.is_10pct_only & (e.n_ins_30d >= 2),
    "P_small_lt100k": lambda e: (e.code == "P") & ~e.is_10pct_only & (e.val < 1e5),
    "S_nonroutine_gt20pct": lambda e: (e.code == "S") & ~e.is_10pct_only & (e.cls != "routine") & (e.frac_holdings > 0.2),
}
rows = []
nets = {}
for name, f in SUBSETS.items():
    ev = E[f(E)]
    side = -1.0 if name.startswith("S_") else 1.0
    for H in (21, 63, 126):
        for hedge in ("sector", "market"):
            fl = active(ev, H)
            w, n = book(fl, hedge=hedge, side=side)
            w = w.loc["2010-01-01":]
            net, st = xs_backtest(w, ret.loc["2010-01-01":], cost_bps=5.0, name=name)
            r = splits_row(net, st)
            r.update({"subset": name, "H": H, "hedge": hedge, "names": n.loc["2010":].mean(),
                      "pct_days_active": (n.loc["2010":] > 0).mean()})
            rows.append(r)
            nets[(name, H, hedge)] = net
d = pd.DataFrame(rows).set_index(["subset", "H", "hedge"])
pd.set_option("display.width", 220)
print(d.round(3).to_string())
d.round(4).to_csv(os.path.join(HERE, "portfolio_results.csv"))
pd.DataFrame({f"{k[0]}|{k[1]}|{k[2]}": v for k, v in nets.items()}).to_parquet(os.path.join(HERE, "nets_0_portfolio.parquet"))
