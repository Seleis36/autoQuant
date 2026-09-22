"""Step 4 -- the ONE configuration chosen on IS 1990-2009, run out of sample.

Config frozen from steps 2-3 before any OOS number was looked at:
    signal_n = ( clip(carry_n / 0.02, -1, 1) + trend_n(63,126,252) ) / 2   for n in {2,10,30}
    leg vol target 5%, portfolio vol target 10%, gross cap 6x, 21d smoothing, 5% no-trade band
    cost 2 bp per side
Two implementations of the same signal:
    SYN  synthetic constant-maturity returns (1990-2026)
    ETF  SHY(2y) / IEF(10y) / TLT(30y), notional weights, 2010-2026
"""
import os, sys
import numpy as np, pandas as pd
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
sys.path.insert(0, os.path.join(H, "..", "..", "shared"))
sys.path.insert(0, os.path.join(H, "..", "credit-spread-trend"))
from curve_lib import yields, total_returns, excess_returns, carry
from research_lib import perf_stats
from backtest_is2 import band
from backtest_is import build, ANN, MATS
from data_lib import prices, crypto_book, hedge_report
pd.set_option("display.width", 220, "display.max_columns", 40)

IS = ("1990-01-01", "2009-12-31"); OOS = ("2010-01-01", "2026-09-21")
ETF = {2: "SHY", 10: "IEF", 30: "TLT"}

y = yields(); ex = excess_returns(total_returns(y, MATS), y)[list(MATS)]
cy = carry(y, MATS)
idx = (1 + ex.fillna(0)).cumprod()

SIG = ((cy / 0.02).clip(-1, 1)
       + sum(np.sign(idx / idx.rolling(L).mean() - 1) for L in (63, 126, 252)) / 3) / 2


def weights(rets, sig=SIG, leg_vol=0.05, tvol=0.10, gross_cap=6.0, smooth=21, tol=0.05):
    sig = sig.reindex(rets.index).ffill()
    v = rets.rolling(252, min_periods=126).std() * np.sqrt(ANN)
    w = (sig * (leg_vol / v)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    pr = (w.shift(1) * rets).sum(axis=1)
    pv = pr.rolling(252, min_periods=126).std() * np.sqrt(ANN)
    w = w.mul((tvol / pv).clip(0, 3).shift(1).fillna(0.0), axis=0)
    g = w.abs().sum(axis=1)
    w = w.div((g / gross_cap).clip(lower=1.0), axis=0)
    if smooth:
        w = w.rolling(smooth).mean()
    return band(w.fillna(0.0), tol=tol)


def bt(w, rets, cost=2.0, name="s"):
    we = w.shift(1).fillna(0.0)
    turn = (we - we.shift(1).fillna(0.0)).abs().sum(axis=1)
    net = ((we * rets).sum(axis=1) - turn * cost / 1e4).rename(name)
    return net, we, turn


def report(net, we, turn, label, ann=ANN):
    st = perf_stats(net.dropna(), ann=ann, name=label)
    st["Turnover_ann"] = turn.sum() / (len(turn) / ann)
    st["AvgGross"] = we.abs().sum(axis=1).mean()
    st["MaxGross"] = we.abs().sum(axis=1).max()
    return st


# ---------------------------------------------------------------- synthetic
w_syn = weights(ex)
net_syn, we_syn, tu_syn = bt(w_syn, ex, name="SYN")
rows = {}
for k, (a, b) in {"IS 1990-2009": IS, "OOS 2010-2026": OOS, "FULL 1990-2026": ("1990-01-01", OOS[1])}.items():
    m = (net_syn.index >= a) & (net_syn.index <= b)
    rows[k] = report(net_syn[m], we_syn[m], tu_syn[m], k)
print("=== SYNTHETIC constant-maturity implementation, 2bp/side ===")
print(pd.DataFrame(rows).T[["CAGR", "Vol", "Sharpe", "Sortino", "MaxDD", "Calmar", "t_NW",
                            "Turnover_ann", "AvgGross"]].round(3))

# ---------------------------------------------------------------- ETF
px = prices(list(ETF.values()), include_pre2010=False).dropna()
r_etf = px.pct_change().rename(columns={v: k for k, v in ETF.items()})[list(MATS)]
# ETF returns are TOTAL returns; fund the book at the 3m bill to match the synthetic
r_etf_ex = r_etf.sub(y[0.25].reindex(r_etf.index).ffill().shift(1) / 252.0, axis=0)
w_etf = weights(r_etf_ex)
net_etf, we_etf, tu_etf = bt(w_etf, r_etf_ex, name="ETF")
rows = {}
for k, (a, b) in {"ETF 2010-2026 (all OOS)": OOS,
                  "ETF 2010-2017": ("2010-01-01", "2017-12-31"),
                  "ETF 2018-2026": ("2018-01-01", OOS[1])}.items():
    m = (net_etf.index >= a) & (net_etf.index <= b)
    rows[k] = report(net_etf[m], we_etf[m], tu_etf[m], k)
print("\n=== ETF implementation SHY/IEF/TLT, 2bp/side, excess of 3m bill ===")
print(pd.DataFrame(rows).T[["CAGR", "Vol", "Sharpe", "Sortino", "MaxDD", "Calmar", "t_NW",
                            "Turnover_ann", "AvgGross", "MaxGross"]].round(3))

print("\nSYN vs ETF correlation over 2010-2026:",
      round(net_syn.loc[OOS[0]:].corr(net_etf.loc[OOS[0]:]), 3))
print("\nETF per-year Sharpe / return:")
n = net_etf.loc[OOS[0]:]
yr = pd.DataFrame({"SR": n.groupby(n.index.year).apply(lambda s: s.mean() / s.std() * np.sqrt(ANN)),
                   "ret": n.groupby(n.index.year).apply(lambda s: (1 + s).prod() - 1)})
print(yr.round(3).T)

# ---------------------------------------------------------------- hedge vs crypto book
book = crypto_book()
print("\n=== hedge diagnostics vs the live crypto book proxy (2018-03 -> 2026-09) ===")
hr = pd.DataFrame({"ETF_carry_trend": hedge_report(net_etf, book),
                   "SYN_carry_trend": hedge_report(net_syn, book)})
print(hr.round(4))
b = book.reindex(net_etf.index).dropna()
n2 = net_etf.reindex(b.index)
for wgt in [0.0, 0.25, 0.5]:
    comb = (1 - wgt) * b + wgt * n2
    print(f"  book {1-wgt:.0%} + rates {wgt:.0%}:  SR {comb.mean()/comb.std()*np.sqrt(365):5.2f}"
          f"   ann {comb.mean()*365:6.2%}   maxDD {((1+comb).cumprod()/(1+comb).cumprod().cummax()-1).min():6.2%}")

out = pd.DataFrame({"net_syn": net_syn, "net_etf": net_etf})
out.to_parquet(os.path.join(H, "backtest_series.parquet"))
w_etf.to_parquet(os.path.join(H, "weights_etf.parquet"))
