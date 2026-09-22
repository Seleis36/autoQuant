"""Step 3 of credit-spread-trend -- the explicitly risk-off family.

The brief asks for a *hedge* to the crypto book, so the last family worth testing is
the one built to pay in risk-off: buy duration on equity-vol spikes, sell credit on
credit-vol spikes, and the equity->bond next-day flight-to-quality reversal.
Design window IS 2010-2017, confirm on OOS 2018-2026 (the crypto-book overlap).
"""
import os, sys
import numpy as np, pandas as pd
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
sys.path.insert(0, os.path.join(H, "..", "..", "shared"))
from data_lib import prices, hy_excess, crypto_book, hedge_report, ANN, DUR_HEDGE
from research_lib import perf_stats
pd.set_option("display.width", 220, "display.max_columns", 40)

IS = ("2010-01-01", "2017-12-31"); OOS = ("2018-01-01", "2026-09-21")
px = prices(["TLT", "IEF", "SHY", "HYG", "LQD", "SPY"], include_pre2010=False).dropna()
vix = prices(["^VIX"], include_pre2010=False)["^VIX"].reindex(px.index).ffill()
r = px.pct_change()
hx = hy_excess(px)


def bt(w, ret, cost=2.0, legs=1.0, name="s"):
    w = w.reindex(ret.index).fillna(0.0)
    we = w.shift(1).fillna(0.0)
    turn = (we - we.shift(1).fillna(0.0)).abs() * legs
    net = (we * ret - turn * cost / 1e4).rename(name)
    return net, turn, we


rows, nets = {}, {}
def add(name, w, ret, legs=1.0):
    n, t, we = bt(w, ret, legs=legs, name=name)
    nets[name] = n
    s = perf_stats(n.loc[IS[0]:IS[1]].dropna(), ann=ANN, name=name)
    s["TO"] = t.loc[IS[0]:IS[1]].sum() / (len(t.loc[IS[0]:IS[1]]) / ANN)
    s["AvgAbsExp"] = we.loc[IS[0]:IS[1]].abs().mean()
    rows[name] = s


# --- A. long TLT after a VIX spike, hold k days
vspike = vix / vix.rolling(20).mean() - 1
for thr in [0.10, 0.20, 0.30]:
    for k in [1, 3, 5, 10]:
        w = (vspike > thr).astype(float).rolling(k).max().fillna(0.0)
        add(f"vixspike{int(thr*100)}_h{k}", w, r["TLT"])

# --- B. long TLT after a big SPY down day (flight to quality), hold k days
spydn = r["SPY"] < r["SPY"].rolling(252).std() * -1.5
for k in [1, 2, 3, 5]:
    add(f"spydn_h{k}", spydn.astype(float).rolling(k).max().fillna(0.0), r["TLT"])
# --- B2. the reversal: SHORT TLT the day after a flight-to-quality rally
tltup = (r["TLT"] > r["TLT"].rolling(252).std() * 1.5) & (r["SPY"] < 0)
add("fq_reversal", -tltup.astype(float), r["TLT"])

# --- C. short HY credit when credit vol spikes (the crypto-stress hedge proper)
cvol = hx.rolling(20).std() * np.sqrt(ANN)
cmed = cvol.rolling(252).median()
for mult in [1.25, 1.5, 2.0]:
    add(f"credit_volgate{mult}", -(cvol > mult * cmed).astype(float), hx, legs=1 + DUR_HEDGE)
    add(f"credit_carrygate{mult}", (cvol <= mult * cmed).astype(float), hx, legs=1 + DUR_HEDGE)

# --- D. HYG vs LQD relative momentum (HY leads the risk cycle)
hl = r["HYG"] - r["LQD"]
hli = (1 + hl.fillna(0)).cumprod()
for L in [20, 60, 120]:
    add(f"hy_vs_ig_ma{L}", np.sign(hli / hli.rolling(L).mean() - 1), hl, legs=2.0)

df = pd.DataFrame(rows).T
print("=== IS 2010-2017, risk-off family, 2bp/side ===")
print(df[["CAGR", "Vol", "Sharpe", "MaxDD", "t_NW", "TO", "AvgAbsExp"]].sort_values("Sharpe", ascending=False).round(3))

print("\n=== OOS 2018-2026 for the IS top 5 (reported for completeness, not for selection) ===")
top = df.sort_values("Sharpe", ascending=False).index[:5]
oos = {k: perf_stats(nets[k].loc[OOS[0]:OOS[1]].dropna(), ann=ANN, name=k) for k in top}
print(pd.DataFrame(oos).T[["CAGR", "Vol", "Sharpe", "MaxDD", "t_NW"]].round(3))

book = crypto_book()
print("\n=== hedge diagnostics for the IS top 5 ===")
print(pd.DataFrame({k: hedge_report(nets[k], book) for k in top}).round(4))
