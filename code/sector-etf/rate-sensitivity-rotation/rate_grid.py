"""Rate-sensitivity rotation (QuantSeeker 'rate momentum' sector strategy; Driesprong-style
under-reaction to rates). Each sector's rolling beta to daily 10y-yield changes, controlling for
SPY (2-factor OLS over the last L days). Signal = rate beta x past-k-day yield change
(yields have momentum -> sectors that benefit from the ongoing rate trend are expected to keep
benefiting). ^TNX / DGS10 closes are not synchronous with 16:00 ET, so yield changes enter the
signal lagged one day. Book: linear XS weights, SPY-hedged, monthly or 21d tranches.
Also: the pure 'rate beta' tilt (no trend) and the trend-only sign variant."""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx

S = data.SECTORS
c = data.load_panel(); r = c.pct_change(); spy = r["SPY"]
beta = sx.beta_to(r[S], spy, 126)
mask = data.universe_mask(c[S])
dgs = pd.read_parquet(os.path.join(sx.rl.DATA_DIR, "FRED_DGS10_d.parquet"))["DGS10"]
dgs.index = pd.to_datetime(dgs.index)
y = dgs.reindex(c.index.union(dgs.index)).ffill().reindex(c.index)
dy = y.diff()                                   # same-day co-movement for beta estimation only
me = c.index.to_series().groupby(c.index.to_period("M")).transform("max") == c.index.to_series()

def rate_beta(L):
    # 2-factor rolling OLS: r_i = a + b_m spy + b_y dy
    X = pd.concat([spy, dy], axis=1).fillna(0); X.columns = ["m", "y"]
    out = {}
    for s_ in S:
        yy = r[s_]
        cm = X["m"].rolling(L).cov(yy); cy = X["y"].rolling(L).cov(yy)
        vm = X["m"].rolling(L).var(); vy = X["y"].rolling(L).var(); cmy = X["m"].rolling(L).cov(X["y"])
        det = vm * vy - cmy ** 2
        out[s_] = (vm * cy - cmy * cm) / det
    return pd.DataFrame(out)

def lin(s):
    s = s.where(mask); s = s.sub(s.mean(axis=1), axis=0)
    return s.div(s.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0)

rows = []
fwd = np.log1p(r[S] - beta.shift(1).mul(spy, axis=0)).rolling(21).sum().shift(-21)
for L, k, reb, form in itertools.product([126, 252], [21, 63, 126, 252], ["monthly", "t21"], ["beta*trend", "beta*sign"]):
    by = rate_beta(L)
    tr = y.diff(k).shift(1)
    sig = by.mul(tr if form == "beta*trend" else np.sign(tr), axis=0)
    w = lin(sig)
    w = w.where(me).ffill().fillna(0) if reb == "monthly" else sx.tranche(w, 21)
    W = w.copy(); W["SPY"] = -(w * beta.fillna(1)).sum(axis=1)
    st, _ = sx.summary(W, c, name=f"L{L}|k{k}|{reb}|{form}")
    ic = sig.where(mask)[me].rank(axis=1).corrwith(fwd.where(mask)[me].rank(axis=1), axis=1)
    st["IC_IS"] = ic.loc[:"2014"].mean(); st["IC_OOS"] = ic.loc["2015":].mean()
    rows.append(st)
for L in [126, 252]:
    w = lin(rate_beta(L)).where(me).ffill().fillna(0)
    W = w.copy(); W["SPY"] = -(w * beta.fillna(1)).sum(axis=1)
    st, _ = sx.summary(W, c, name=f"L{L}|static rate-beta tilt"); rows.append(st)
df = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 100)
print(sx.fmt(df.sort_values("Sh_IS", ascending=False)))
df.to_csv(os.path.join(os.path.dirname(__file__), "rate_grid.csv"))
