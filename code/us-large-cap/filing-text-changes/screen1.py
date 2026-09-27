"""Lazy Prices (Cohen, Malloy & Nguyen 2020) on S&P 500 members.

Per filing (10-K / 10-Q, 2009+): year-over-year similarity to the same form one year earlier
(data/SP500_filing_similarity.parquet, built by code/us-large-cap/shared/fetch_filing_text.py).
The latest filing's value is the firm's signal from the first session after its filing date
until the next filing (max 200 days). Higher similarity = "non-changer" = buy.

Variants: metric (cos_log / jac / cos / -|len_ratio|), 10-K only vs all forms, raw vs
de-meaned by the firm's own trailing similarity history (controls for firm-level boilerplate
style), quintile vs linear, raw vs beta-hedged; monthly sector-neutral books, 5 bp/side.
"""
import os, sys, pickle
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
from common import sector_map, sector_z, book_weights, hold_monthly, splits_row, month_ends, ic_series, ic_summary
from xs_lib import xs_backtest
from panel import load_panel
from xbrl import Fundamentals
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from research_lib import DATA_DIR

P = load_panel()
close = P["close"]; dates = close.index; tix = list(close.columns)
ret = close.pct_change(fill_method=None)
mem = P["member"]; sec = sector_map(P)
S = pd.read_parquet(os.path.join(DATA_DIR, "SP500_filing_similarity.parquet"))
S = S[S.ticker.isin(tix)].dropna(subset=["cos"])
S["neg_abslen"] = -S.len_ratio.abs()
# firm-demeaned: similarity minus the firm's mean over its PREVIOUS (up to 8) filings of the same form
S = S.sort_values("filing_date")
for m in ("cos_log", "jac", "cos"):
    S[m + "_dm"] = S[m] - S.groupby(["ticker", "form"])[m].transform(lambda x: x.shift(1).rolling(8, min_periods=3).mean())

sig = {}
for form in ("all", "10-K"):
    X = S if form == "all" else S[S.form == "10-K"]
    age = 200 if form == "all" else 400
    for m in ("cos_log", "jac", "cos", "neg_abslen", "cos_log_dm", "jac_dm"):
        long = X[["ticker", "report_date", "filing_date", m]].rename(columns={"report_date": "end", "filing_date": "avail", m: "val"}).dropna()
        sig[f"{m}|{form}"] = Fundamentals.daily(long, dates, tix, max_age_days=age)

base = mem & close.notna()
rebal = month_ends(dates); rebal = rebal[rebal >= "2010-12-31"]
M = ret.where(mem).mean(axis=1)
beta = ret.rolling(252, min_periods=200).cov(M).div(M.rolling(252, min_periods=200).var(), axis=0)
mw = mem.astype(float); mw = mw.div(mw.sum(axis=1), axis=0)
fwd63 = close.shift(-63) / close - 1
rows = []; NETS = {}
for k, s in sig.items():
    mask = base & s.notna()
    z = sector_z(s, sec, mask)
    ic = ic_series(z.loc[rebal], fwd63.loc[rebal], mask.loc[rebal]); ics = ic_summary(ic)
    for kind in ("quintile", "linear"):
        w0 = hold_monthly(book_weights(z, mask, kind=kind), rebal).loc["2011-01-01":]
        for hedge in ("none", "beta"):
            w = w0
            if hedge == "beta":
                bw = (w * beta.reindex_like(w).fillna(1.0)).sum(axis=1)
                w = w - mw.loc[w.index].mul(bw, axis=0)
            net, st = xs_backtest(w, ret.loc["2011-01-01":], cost_bps=5.0)
            r = splits_row(net, st)
            r.update({"signal": k, "kind": kind, "hedge": hedge, "IC63": ics["IC"], "IC63_t_naive": ics["IC_t"],
                      "coverage": (mask.sum(axis=1) / base.sum(axis=1)).loc["2012":].mean()})
            rows.append(r); NETS["|".join([k, kind, hedge])] = net
d = pd.DataFrame(rows).set_index(["signal", "kind", "hedge"])
pd.set_option("display.width", 220)
print(d.round(3).to_string())
d.round(4).to_csv(os.path.join(HERE, "screen1_results.csv"))
pd.DataFrame(NETS).to_parquet(os.path.join(HERE, "nets_0_screen1.parquet"))
pickle.dump({k: sig[k] for k in ("cos_log|all", "jac|all", "cos_log_dm|all")}, open("/tmp/lp_sig.pkl", "wb"))
