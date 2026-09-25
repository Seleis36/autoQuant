"""Re-framing 1: time-series (not cross-sectional) short-term mean reversion.
Per sector: enter long when oversold (RSI(2) or k-day vol-z) and, optionally, the sector
is above its SMA200; exit on RSI(2) recovery / close>SMA5 / max hold. Each position
sized 1/9 of capital (gross <= 11/9 in the worst case, <1 typically). Optional SPY hedge
turns it back into relative value. Compared against SPY-only RSI(2)."""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx

c = data.load_panel()
S = data.SECTORS
px = c[S + ["SPY"]]
r = px.pct_change()

def rsi(p, n=2):
    d = p.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)

R2 = rsi(px, 2)
sma200 = px.rolling(200).mean()
sma5 = px.rolling(5).mean()
vol = r.ewm(halflife=63, min_periods=63).std()

def state_machine(entry, exit_, maxhold):
    """Long from the close where entry fires until the close where exit fires (or maxhold)."""
    E = entry.values; X = exit_.values
    pos = np.zeros_like(E, dtype=float)
    for j in range(E.shape[1]):
        held = 0
        for i in range(E.shape[0]):
            if held > 0:
                if X[i, j] or held >= maxhold:
                    held = 0
                else:
                    held += 1
                    pos[i, j] = 1
                    continue
            if E[i, j]:
                held = 1
                pos[i, j] = 1
    return pd.DataFrame(pos, index=entry.index, columns=entry.columns)

rows = []
cells = []
for trig, thr, trend, ex, mh, hedge in itertools.product(
        ["rsi2", "z3"], ["lo", "mid", "hi"], [True, False], ["rsi50", "sma5"], [5, 10], [False, True]):
    if trig == "rsi2":
        th = {"lo": 5, "mid": 10, "hi": 20}[thr]
        ent = R2 < th
    else:
        th = {"lo": -2.0, "mid": -1.5, "hi": -1.0}[thr]
        ent = (r.rolling(3).sum() / (vol * np.sqrt(3))) < th
    if trend:
        ent = ent & (px > sma200)
    ext = (R2 > 50) if ex == "rsi50" else (px > sma5)
    ent = ent.fillna(False); ext = ext.fillna(False)
    pos = state_machine(ent[S], ext[S], mh)
    pos = pos.where(c[S].notna(), 0)
    W = pos / 9.0
    if hedge:
        beta = sx.beta_to(r[S], r["SPY"], halflife=126).fillna(1.0)
        W["SPY"] = -(W * beta).sum(axis=1)
    name = f"{trig}|{thr}|trend{int(trend)}|{ex}|mh{mh}|hedge{int(hedge)}"
    s, net = sx.summary(W, px, name=name)
    s0, _ = sx.summary(W, px, cost_bps=0.0)
    s["Sh0_OOS"] = s0["Sh_OOS"]
    rows.append(s)
    # SPY-only analogue
df = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
print(len(df), "cells")
print(sx.fmt(df.sort_values("Sh_IS", ascending=False)).head(25))
print(sx.fmt(df[df.index.str.endswith("hedge0")].sort_values("Sh_OOS", ascending=False)).head(10))
print(sx.fmt(df[df.index.str.endswith("hedge1")].sort_values("Sh_OOS", ascending=False)).head(10))
df.to_csv(os.path.join(os.path.dirname(__file__), "ts_grid_results.csv"))

# benchmarks
for t in ["SPY"]:
    ent = (R2[t] < 10) & (px[t] > sma200[t]); ext = R2[t] > 50
    pos = state_machine(ent.to_frame().fillna(False), ext.to_frame().fillna(False), 10)
    s, _ = sx.summary(pos, px, name="SPY rsi2<10 trend")
    print(sx.fmt(s.to_frame().T))
bh = pd.DataFrame({"SPY": 1.0}, index=px.index)
print(sx.fmt(sx.summary(bh, px, name="SPY B&H")[0].to_frame().T))
ew = c[S].notna().astype(float); ew = ew.div(ew.sum(axis=1), axis=0)
print(sx.fmt(sx.summary(ew, px, name="EW sectors B&H")[0].to_frame().T))
