"""(a) Event windows conditioned on trailing dividend yield (terciles, known at the event) and
by year; (b) Hartzmark-Solomon monthly book: at each month-end, long payers whose ex-date fell
in NEXT calendar month one year earlier, short payers without, sector-neutral, dollar-neutral,
all / high-yield only; 5 bp."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
from common import sector_map, splits_row, month_ends, xs_backtest
from panel import load_panel
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from research_lib import DATA_DIR

P = load_panel()
close = P["close"]; dates = close.index; tix = list(close.columns)
ret = close.pct_change(fill_method=None)
mem = P["member"]; sec = sector_map(P)
A = pd.read_parquet(os.path.join(DATA_DIR, "SP500_actions.parquet"))
dv = A[(A.dividend > 0) & A.ticker.isin(tix)]
# trailing 12m dividend yield, known at t (split-adjusted dividends vs dividend-adjusted close:
# use the yield on the split-adjusted price scale -> close / div factor is not needed for a rank)
D = pd.DataFrame(0.0, index=dates, columns=tix)
ri = dates.searchsorted(dv.date.values); ci = pd.Index(tix).get_indexer(dv.ticker)
ok = (ri < len(dates)) & (ci >= 0)
M = np.zeros(D.shape); np.add.at(M, (ri[ok], ci[ok]), dv.dividend.values[ok]); D[:] = M
dy = D.rolling(252, min_periods=200).sum() / close          # rank-only use (adj close ~ scale)

# (a) event windows by yield tercile
ev = pd.read_parquet("/tmp/div_events.parquet")
ev["dy"] = dy.values[ev.ri.values - 21, ev.ci.values]
ev["dy_rank"] = [dy.iloc[i - 21][mem.iloc[i - 21]].rank(pct=True).get(t, np.nan) for i, t in zip(ev.ri.values, ev.ticker)]
r = ret.where(mem); res = r.copy()
for s, cols in sec.groupby(sec).groups.items():
    cols = [c for c in cols if c in r.columns]
    res[cols] = r[cols].sub(r[cols].mean(axis=1), axis=0)
C = res.fillna(0.0).cumsum().values
ev["w20"] = (C[ev.ri.values - 1, ev.ci.values] - C[ev.ri.values - 21, ev.ci.values]) * 1e4
ev["w10"] = (C[ev.ri.values - 1, ev.ci.values] - C[ev.ri.values - 11, ev.ci.values]) * 1e4
ev["terc"] = pd.cut(ev.dy_rank, [0, 1 / 3, 2 / 3, 1.0], labels=["low", "mid", "high"])
ev.to_parquet("/tmp/div_events_dy.parquet")
print(ev.groupby("terc", observed=True)[["w20", "w10"]].agg(["mean", "count"]).round(2))
print("by year w20:", ev.groupby(ev.pred.dt.year).w20.mean().round(1).to_dict())

# (b) HS monthly book
if __name__ != "__main__":
    raise ImportError("stop")  # imported for `ev` only
rebal = month_ends(dates); rebal = rebal[rebal >= "2010-12-31"]
exm = dv.assign(ym=dv.date.dt.year * 12 + dv.date.dt.month - 1)
has = set(zip(exm.ticker, exm.ym))
payer = D.rolling(252, min_periods=200).sum() > 0
rows = []
for cond in ("all", "high_yield", "high_yield_long_only_vs_mkt"):
    W = pd.DataFrame(0.0, index=rebal, columns=tix)
    for d in rebal:
        nxt = (d.year * 12 + d.month - 1) + 1          # next calendar month index
        elig = mem.loc[d] & payer.loc[d]
        if cond != "all":
            q = dy.loc[d][elig].rank(pct=True); elig = elig & (q.reindex(tix) >= 2 / 3).fillna(False)
        e = [t for t in tix if elig[t]]
        lon = [t for t in e if (t, nxt - 12) in has]
        sho = [t for t in e if (t, nxt - 12) not in has]
        if len(lon) < 10 or len(sho) < 10:
            continue
        # sector-neutral: within each sector, +1/n_long, -1/n_short, scaled to gross 1
        w = pd.Series(0.0, index=tix)
        for s, cols in sec.reindex(e).groupby(sec.reindex(e)).groups.items():
            L_ = [c for c in cols if c in lon]; S_ = [c for c in cols if c in sho]
            if L_ and S_:
                w[L_] += 1 / len(L_); w[S_] -= 1 / len(S_)
        if cond == "high_yield_long_only_vs_mkt":
            w = pd.Series(0.0, index=tix); w[lon] = 1 / len(lon)
            m_ = mem.loc[d].astype(float); w = w - m_ / m_.sum()
        W.loc[d] = w / w.abs().sum()
    Wd = W.reindex(dates).ffill().fillna(0.0).loc["2011-01-01":]
    net, st = xs_backtest(Wd, ret.loc["2011-01-01":], cost_bps=5.0)
    row = splits_row(net, st); row["cond"] = cond; rows.append(row)
    n0, s0 = xs_backtest(Wd, ret.loc["2011-01-01":], cost_bps=0.0)
    row = splits_row(n0, s0); row["cond"] = cond + " @0bp"; rows.append(row)
d = pd.DataFrame(rows).set_index("cond")
pd.set_option("display.width", 200)
print(d.round(3).to_string())
d.round(4).to_csv(os.path.join(HERE, "screen1_results.csv"))
