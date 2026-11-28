"""global-rebalance-pressure books.
SPEC (fixed before this script; window disclosed as read off the full-sample day profile):
  at close t, if session t+1 is one of the last 4 of the month (days_left in {3,2,1,0}):
      w(t) = -clip(Z_t, -2, 2) / 2    on GLOBAL = 0.6 SPY + 0.4 EFA (gross <= 1)
  Z_t = calendar-fund SPY-IEF drift since the previous month-end through close t.
  Costs: SPY 1 bp/side, EFA 2 bp, country ETFs 5 bp. Flat otherwise.
Grid around the spec: windows, instruments, sizing, signal bond; backcast on S&P/syn10."""
import itertools
import numpy as np, pandas as pd
from grp_lib import load_etf, load_back, drift_z, days_left, month_end_flags, SPL, BACK, COUNTRIES

C, R = load_etf()
me = month_end_flags(R.index)
dl = days_left(R.index, me)
COST = {"SPY": 1.0, "EFA": 2.0, **{c: 5.0 for c in COUNTRIES}, "EEM": 3.0, "ACWI": 2.0}
INSTR = {"GLOBAL": {"SPY": 0.6, "EFA": 0.4}, "SPY": {"SPY": 1.0}, "EFA": {"EFA": 1.0}, "BASKET": "basket"}

def instr_weights(name, idx):
    spec = INSTR[name]
    if spec == "basket":
        av = C[COUNTRIES].notna()
        return av.astype(float).div(av.sum(axis=1), axis=0).fillna(0.0)
    return pd.DataFrame({k: v for k, v in spec.items()}, index=idx)

def run(pos, name, cost_mult=1.0):
    W = instr_weights(name, R.index).mul(pos, axis=0)
    ret = C[W.columns].pct_change().fillna(0.0)
    We = W.shift(1).fillna(0.0)
    gross = (We * ret).sum(axis=1)
    dW = (We - We.shift(1).fillna(0.0)).abs()
    cost = (dW * pd.Series({c: COST[c] for c in W.columns}) * cost_mult / 1e4).sum(axis=1)
    return gross - cost, gross, dW.sum(axis=1), We

def sr(x, a, b):
    x = x.loc[a:b]; return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else np.nan

def book_pos(z, window, sizing="clip", dl_=dl):
    nxt = dl_.shift(-1)                      # days left of the session the weight earns
    # live: next session's days_left comes from the NYSE calendar; in history the index
    active = nxt.isin(window)
    x = (-np.clip(z, -2, 2) / 2) if sizing == "clip" else -np.sign(z) * 0.5
    return x.where(active, 0.0).fillna(0.0)

rows = {}
Z = {"IEF": drift_z(R.SPY, R.IEF, me), "TLT": drift_z(R.SPY, R.TLT, me)}
WIN = {"last4 L-3..L (SPEC)": [3, 2, 1, 0], "last5 L-4..L": [4, 3, 2, 1, 0], "last3 L-2..L": [2, 1, 0],
       "L-3 only": [3], "L only": [0], "L-1..L": [1, 0]}
for (wn, win), ins, sz, bd in itertools.product(WIN.items(), INSTR, ["clip", "sign"], ["IEF", "TLT"]):
    if (sz == "sign" or bd == "TLT") and not (ins == "GLOBAL"):
        continue
    pos = book_pos(Z[bd], win, sz)
    net, gross, turn, We = run(pos, ins)
    eq = (1 + net.loc[SPL["FULL"][0]:]).cumprod()
    rows[(wn, ins, sz, bd)] = {"FULL": sr(net, *SPL["FULL"]), "IS": sr(net, *SPL["IS"]), "OOS": sr(net, *SPL["OOS"]),
        "2020-26": sr(net, "2020", "2026"), "2024-26": sr(net, "2024", "2026"), "gross_FULL": sr(gross, *SPL["FULL"]),
        "@2x cost": sr(run(pos, ins, 2.0)[0], *SPL["FULL"]),
        "CAGR": eq.iloc[-1] ** (252 / len(eq)) - 1, "Vol": net.loc[SPL["FULL"][0]:].std() * np.sqrt(252),
        "MaxDD": (eq / eq.cummax() - 1).min(), "Turn/yr": turn.loc[SPL["FULL"][0]:].sum() / (len(eq) / 252),
        "AvgGross": We.abs().sum(axis=1).loc[SPL["FULL"][0]:].mean()}
pd.set_option("display.width", 250)
T = pd.DataFrame(rows).T
print(T.round(2).to_string())
print(f"\ncells: {len(T)}")

# ---- backcast, S&P 500 index with syn10 drift, 1 bp/side
Bk = load_back(); meb = month_end_flags(Bk.index); dlb = days_left(Bk.index, meb); zb = drift_z(Bk.EQ, Bk.BD, meb)
print("\n=== backcast S&P 500 (1 bp/side), net Sharpe")
for wn, win in WIN.items():
    pos = book_pos(zb, win, "clip", dlb)
    We = pos.shift(1).fillna(0.0)
    net = We * Bk.EQ.fillna(0.0) - (We - We.shift(1).fillna(0.0)).abs() * 1e-4
    print(f"{wn:22s} " + "  ".join(f"{k}: {sr(net, a, b):5.2f}" for k, (a, b) in {**BACK, "1995.06-2002": ("1995-06-07", "2002-07-31")}.items()))
spec = book_pos(Z["IEF"], WIN["last4 L-3..L (SPEC)"])
net, gross, turn, We = run(spec, "GLOBAL")
net.rename("grp_spec").to_frame().to_parquet("nets_03.parquet")
print("\nSPEC by calendar year (net %):"); print((net.loc["2002-08":].groupby(net.loc["2002-08":].index.year).sum() * 100).round(2).to_string())
