"""In-depth checks on the IS-selected book (k = 3, every day, 2 bp per side), built from
book.target_weights so the deployable function is the thing being tested."""
import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "rates-bonds", "shared"))
import research_lib as rl
from rb_data import etf_close
import book as S

pd.set_option("display.width", 220)
IS, OOS = ("2008-01-01", "2017-12-31"), ("2018-01-01", "2026-12-31")
px = etf_close(S.TICKERS).loc["2007-10":]
ret = px.pct_change(fill_method=None)


def sh(r, a=None, b=None):
    r = r.loc[a:b].dropna()
    return r.mean() / r.std() * np.sqrt(252) if len(r) > 60 and r.std() > 0 else np.nan


def run(w, cost=2.0, lag=0):
    we = w.shift(1 + lag).fillna(0.0)
    r = ret.reindex(columns=w.columns).fillna(0.0)
    gross = (we * r).sum(axis=1)
    turn = we.diff().abs().sum(axis=1)
    return gross - turn * cost / 1e4, gross, turn


w = S.target_weights(px)
net, gross, turn = run(w)
net, gross = net.loc[IS[0]:], gross.loc[IS[0]:]
print("== headline, 2 bp per side")
for lab, (a, b) in (("IS 2008-17", IS), ("OOS 2018-26", OOS), ("full", (IS[0], OOS[1]))):
    st = rl.perf_stats(net.loc[a:b], ann=252)
    print("%-12s Sharpe %.2f  CAGR %.2f%%  vol %.2f%%  maxDD %.1f%%  t_NW %.1f  (gross Sharpe %.2f)" % (
        lab, st["Sharpe"], st["CAGR"] * 100, st["Vol"] * 100, st["MaxDD"] * 100, st["t_NW"], sh(gross, a, b)))
print("turnover %.0fx / yr   avg gross %.2f   max gross %.2f   avg |muni notional| %.2f   avg |IEF| %.2f" % (
    turn.loc[IS[0]:].sum() / (len(net) / 252), w.loc[IS[0]:].abs().sum(axis=1).mean(), w.abs().sum(axis=1).max(),
    w.loc[IS[0]:, list(S.MUNI)].sum(axis=1).abs().mean(), w.loc[IS[0]:, "IEF"].abs().mean()))

print("\n== where the P&L comes from (gross, % per year)")
we = w.shift(1).fillna(0.0)
muni_leg = (we[list(S.MUNI)] * ret[list(S.MUNI)].fillna(0)).sum(axis=1)
hedge_leg = we["IEF"] * ret["IEF"].fillna(0)
for lab, (a, b) in (("IS", IS), ("OOS", OOS)):
    print(lab, "muni legs %.2f%%  IEF hedge leg %.2f%%  | Sharpe of hedge leg alone %.2f, muni legs alone %.2f" % (
        muni_leg.loc[a:b].mean() * 25200, hedge_leg.loc[a:b].mean() * 25200, sh(hedge_leg, a, b), sh(muni_leg, a, b)))

print("\n== cost ladder (bp per side): IS / OOS net Sharpe")
for c in (0, 1, 2, 3, 4, 5):
    n, _, _ = run(w, c)
    print(c, "%.2f / %.2f" % (sh(n, *IS), sh(n, *OOS)))

print("\n== entry delay (sessions), 2 bp")
for L in (0, 1, 2, 3):
    n, g, _ = run(w, 2.0, lag=L)
    print(L, "net %.2f / %.2f   gross %.2f / %.2f" % (sh(n, *IS), sh(n, *OOS), sh(g, *IS), sh(g, *OOS)))

print("\n== by year (net %, 2 bp) and net Sharpe")
y = pd.DataFrame({"net%": net.groupby(net.index.year).sum() * 100, "gross%": gross.groupby(gross.index.year).sum() * 100,
                  "sharpe": net.groupby(net.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(252))})
print(y.round(2).T.to_string())

print("\n== one ETF at a time (net IS / OOS at 2 bp; gross)")
for m in S.MUNI:
    wm = S.target_weights(px, munis=(m,))
    n, g, _ = run(wm)
    print("%-5s net %.2f / %.2f   gross %.2f / %.2f" % (m, sh(n, *IS), sh(n, *OOS), sh(g, *IS), sh(g, *OOS)))
for lab, names in (("liquid four (MUB, VTEB, TFI, SHM)", ("MUB", "VTEB", "TFI", "SHM")), ("national IG only (MUB, VTEB, TFI, ITM)", ("MUB", "VTEB", "TFI", "ITM"))):
    n, g, _ = run(S.target_weights(px, munis=names))
    print("%-40s net %.2f / %.2f   gross %.2f / %.2f" % (lab, sh(n, *IS), sh(n, *OOS), sh(g, *IS), sh(g, *OOS)))

print("\n== neighbours (net IS / OOS at 2 bp)")
for kw in (dict(k=2), dict(k=4), dict(k=5), dict(vol_window=120, minp=60), dict(beta_window=120), dict(beta_window=500)):
    n, g, _ = run(S.target_weights(px, **kw))
    print(kw, "%.2f / %.2f" % (sh(n, *IS), sh(n, *OOS)))

print("\n== unhedged version (muni legs only) and hedge = SHY-scaled: for reference")
wu = w.copy(); wu["IEF"] = 0.0
n, g, _ = run(wu)
print("unhedged: net %.2f / %.2f" % (sh(n, *IS), sh(n, *OOS)))

print("\n== truncation test")
worst = 0.0
for T in ("2012-06-13", "2016-02-29", "2020-03-18", "2022-09-30", "2024-05-08", "2026-07-22"):
    wt = S.target_weights(px.loc[:T])
    d = (wt.iloc[-30:] - w.loc[wt.index[-30:]]).abs().max().max()
    worst = max(worst, d)
print("max |dw| over the last 30 rows at 6 cut dates: %.2e" % worst)
wn = S.target_weights(px.iloc[-400:])
print("last row from 400 bars vs full history: max |dw| %.2e" % (wn.iloc[-1] - w.iloc[-1]).abs().max())

print("\n== vectorbt cross-check (targetpercent, 2 bp fees)")
import vectorbt as vbt
st = "2008-06-01"
cols = list(w.columns)
pxf = px[cols].loc[st:].ffill()
size = w.loc[st:, cols].where(pxf.notna(), 0.0) / 3.0          # /3: vectorbt cannot borrow (see memory note)
pf = vbt.Portfolio.from_orders(pxf, size=size, size_type="targetpercent", fees=0.0002, freq="1D",
                               cash_sharing=True, group_by=True, call_seq="auto", init_cash=1e6)
rv = pf.returns()
both = pd.concat([rv, net.loc[st:] / 3.0], axis=1).dropna()
print("vectorbt Sharpe IS %.2f OOS %.2f | research %.2f / %.2f | daily corr %.4f" % (
    sh(rv, *IS), sh(rv, *OOS), sh(net.loc[st:], *IS), sh(net.loc[st:], *OOS), both.corr().iloc[0, 1]))

print("\n== correlation with deployed rates-bonds sleeves and the CEF book (daily / monthly, 2010+)")
from deployed_sleeves import deployed_returns
dep = deployed_returns()
cef = pd.read_csv(os.path.join(ROOT, "code", "rates-bonds", "cef-discount-reversion", "07_selected_daily.csv"), index_col=0, parse_dates=True)["net10"]
x = pd.concat([net.rename("muni-treasury-lead-lag"), dep, cef.rename("cef-discount-reversion")], axis=1).loc["2010":].dropna()
print(x.corr().round(3).iloc[0].to_dict())
print(x.resample("ME").sum().corr().round(3).iloc[0].to_dict())
net.to_frame("net2").assign(gross=gross).to_csv("02_selected_daily.csv")
print("\nDeflated Sharpe prob, OOS, 16 trials: %.3f" % rl.deflated_sharpe(sh(net, *OOS), len(net.loc[OOS[0]:]), 16,
      skew=net.loc[OOS[0]:].skew(), kurt=net.loc[OOS[0]:].kurtosis() + 3, ann=252))
