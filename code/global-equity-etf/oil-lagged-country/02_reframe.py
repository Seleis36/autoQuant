"""Re-framings of the dead oil -> equity lag:
(1) horizons: oil change over the past h sessions (h = 5, 10, 21) -> next h-session return,
    non-overlapping blocks, with a 1-session skip (EIA spot is published late; use CL=F for ETF era check);
(2) supply-shock residual (Kilian-Park): oil change minus its rolling 252d beta x the WORLD
    equity return over the same window -> next-period equity return (TS) and the
    oil-beta-weighted cross-section;
(3) books: WORLD (0.5 SPY + 0.5 country basket) long/short = -clip(z_resid)/2, monthly and weekly,
    5 bp countries / 1 bp SPY."""
import sys, os
import numpy as np, pandas as pd
from ol_lib import wti_daily, ols_t, SPL, COUNTRIES
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
import data as D

C = D.load_panel(COUNTRIES + ["SPY"], "Close", start="1998-12-01")
R = C.pct_change()
av = R[COUNTRIES].notna().sum(axis=1)
R["BASKET"] = R[COUNTRIES].mean(axis=1).where(av >= 2)
R["WORLD"] = 0.5 * R["SPY"] + 0.5 * R["BASKET"]
wti = wti_daily().reindex(C.index).ffill(limit=3)
cl = D.load_panel(["CL=F"], "Close", start="1998-12-01")["CL=F"]
ro = np.log(wti).diff()
print("corr monthly EIA spot vs CL=F log changes:",
      round(np.log(wti.resample("ME").last()).diff().corr(np.log(cl.resample("ME").last()).diff()), 3))

lw = np.log1p(R["WORLD"])
beta = ro.rolling(252, min_periods=126).cov(lw) / lw.rolling(252, min_periods=126).var()
for h in [5, 10, 21]:
    oil_h = ro.rolling(h).sum(); eq_h = lw.rolling(h).sum()
    resid = oil_h - beta * eq_h
    fwd = {k: np.log1p(R[k]).rolling(h).sum().shift(-h - 1) for k in ["SPY", "BASKET", "WORLD"]}  # skip 1 session
    blocks = C.index[::h]
    out = {}
    for nm, sig in {"raw": oil_h, "resid": resid}.items():
        for k, y in fwd.items():
            for pn, (a, b) in SPL.items():
                bk = blocks[(blocks >= a) & (blocks <= b)]
                bt, t, n = ols_t(y.reindex(bk), sig.reindex(bk))
                out.setdefault(f"{nm}->{k}", {})[pn] = f"{bt:6.3f} ({t:5.2f})"
    print(f"\n=== horizon {h} sessions (non-overlapping blocks, 1-session skip)"); print(pd.DataFrame(out).T.to_string())

# ---- XS: country oil beta x residual oil shock (monthly)
M = C.resample("ME").last(); Rm = M.pct_change(fill_method=None)[COUNTRIES]
om = np.log(wti.resample("ME").last()).diff()
wm = Rm.mean(axis=1) * 0.5 + M["SPY"].pct_change() * 0.5
bm = om.rolling(60, min_periods=36).cov(wm) / wm.rolling(60, min_periods=36).var()
res_m = om - bm * wm
ob = Rm.sub(wm, axis=0).rolling(60, min_periods=36).cov(om).div(om.rolling(60, min_periods=36).var(), axis=0)
for nm, s in {"raw": om, "resid": res_m}.items():
    sig = ob.mul(s, axis=0); xs = sig.sub(sig.mean(axis=1), axis=0)
    nxt = Rm.shift(-1).sub(Rm.shift(-1).mean(axis=1), axis=0)
    for pn, (a, b) in SPL.items():
        d = pd.concat([xs.loc[a:b].stack(), nxt.loc[a:b].stack()], axis=1).dropna()
        ic = d.groupby(level=0).apply(lambda g: g.iloc[:, 0].rank().corr(g.iloc[:, 1].rank()) if len(g) > 3 else np.nan).dropna()
        print(f"XS {nm} IC {pn}: {ic.mean():.3f} (t {ic.mean() / ic.std() * np.sqrt(len(ic)):.2f})")

# ---- books on WORLD: monthly and weekly residual-shock timing
def book(h):
    oil_h = ro.rolling(h).sum(); eq_h = lw.rolling(h).sum(); resid = oil_h - beta * eq_h
    z = resid / resid.rolling(756, min_periods=252).std()
    reb = C.index[::h]
    pos = (-z.clip(-2, 2) / 2).reindex(reb).reindex(C.index).ffill().fillna(0.0)
    w = pd.DataFrame({"SPY": 0.5 * pos})
    avb = C[COUNTRIES].notna(); wb = avb.astype(float).div(avb.sum(axis=1), axis=0).fillna(0.0)
    for c in COUNTRIES: w[c] = 0.5 * pos * wb[c]
    ret = C[w.columns].pct_change().fillna(0.0); We = w.shift(1).fillna(0.0)
    dW = (We - We.shift(1).fillna(0.0)).abs(); cst = pd.Series(5.0, index=w.columns); cst["SPY"] = 1.0
    net = (We * ret).sum(axis=1) - (dW * cst / 1e4).sum(axis=1)
    return {pn: round(net.loc[a:b].mean() / net.loc[a:b].std() * np.sqrt(252), 2) for pn, (a, b) in SPL.items()}
for h in [5, 21]:
    print(f"book WORLD, resid oil shock, hold {h}: {book(h)}")
