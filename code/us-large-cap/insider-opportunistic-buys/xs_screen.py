"""Cross-sectional framing: trailing insider-activity measures as a monthly sector-neutral
signal (Lakonishok-Lee net purchase ratio, selling intensity, breadth of sellers), with and
without routine traders. Uses filing dates (entry = first trading day after filing)."""
import os, sys, pickle
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
from common import *

S, P, aux = pickle.load(open("/tmp/qvc_signals.pkl", "rb"))
close = P["close"]; dates = close.index; tix = list(close.columns)
ret = close.pct_change(fill_method=None)
sec = sector_map(P)
mcap = aux["mcap"]
E = pd.read_parquet("/tmp/insider_events.parquet")
E = E[~E.is_10pct_only]
rebal = month_ends(dates); rebal = rebal[rebal >= "2010-12-31"]


def daily_sum(ev, col=None):
    M = np.zeros((len(dates), len(tix)))
    ri = dates.get_indexer(ev.entry); ci = pd.Index(tix).get_indexer(ev.ticker)
    ok = (ri >= 0) & (ci >= 0)
    np.add.at(M, (ri[ok], ci[ok]), 1.0 if col is None else ev[col].values[ok])
    return pd.DataFrame(M, index=dates, columns=tix)


sig = {}
for tag, ev in {"all": E, "nonroutine": E[E.cls != "routine"]}.items():
    nb = daily_sum(ev[ev.code == "P"]); ns = daily_sum(ev[ev.code == "S"])
    vb = daily_sum(ev[ev.code == "P"], "val"); vs = daily_sum(ev[ev.code == "S"], "val")
    for W in (126, 252):
        b = nb.rolling(W, min_periods=1).sum(); s = ns.rolling(W, min_periods=1).sum()
        sig[f"npr_{tag}_{W}"] = ((b - s) / (b + s)).where(b + s > 0, 0.0)          # no activity = neutral
        sig[f"sellint_{tag}_{W}"] = -(vs.rolling(W, min_periods=1).sum() - vb.rolling(W, min_periods=1).sum()) / mcap
    # breadth: distinct sellers in 126d (approx: sell events count)
    sig[f"nsell_{tag}_126"] = -ns.rolling(126, min_periods=1).sum()

base = P["member"] & mcap.notna()
mret = ret.where(P["member"]).mean(axis=1)
beta = ret.rolling(252, min_periods=200).cov(mret).div(mret.rolling(252, min_periods=200).var(), axis=0)
mw = P["member"].astype(float); mw = mw.div(mw.sum(axis=1), axis=0)
rows = []
for k, s in sig.items():
    s = s.where(base)
    mask = base & s.notna()
    z = sector_z(s, sec, mask)
    for kind in ("quintile", "linear"):
        net, st, w = run_book(z, mask, ret, rebal, kind=kind, name=k)
        r = splits_row(net, st); r.update({"signal": k, "kind": kind, "hedge": "none"}); rows.append(r)
        bw = (w * beta.reindex_like(w).fillna(1.0)).sum(axis=1)
        wh = w - mw.loc[w.index].mul(bw, axis=0)
        n2, s2 = xs_backtest(wh, ret.loc[w.index[0]:], cost_bps=5.0)
        r = splits_row(n2, s2); r.update({"signal": k, "kind": kind, "hedge": "beta"}); rows.append(r)
d = pd.DataFrame(rows).set_index(["signal", "kind", "hedge"])
pd.set_option("display.width", 200)
print(d.round(3).to_string())
d.round(4).to_csv(os.path.join(HERE, "xs_screen_results.csv"))
