"""Predictive tests (signals known at close t; IVs lagged a session):
  VRP      = IV_i - RV_i(21d, annualised, through t)                       [vol points]
  VRPr     = log(IV_i / RV_i)
  RELIV    = log(IV_i / VIX) - its trailing 252d mean                      [abnormal country fear]
  DRELIV5  = 5-session change in log(IV_i / VIX)                           [fear shock]
Targets: next 5 and 21 sessions of the SPY-hedged spread of ETF i.
Pooled cross-sectional rank IC (per date, non-overlapping dates) and per-name TS slopes."""
import numpy as np, pandas as pd
from iv_lib import load, hedged, NAMES, SPL

C, R, IV = load()
H, B = hedged(R)
RV = R[NAMES + ["SPY"]].rolling(21).std() * np.sqrt(252) * 100
lr = np.log(IV[NAMES].div(IV["SPY"], axis=0))
SIG = {"VRP": IV[NAMES] - RV[NAMES], "VRPr": np.log(IV[NAMES] / RV[NAMES]),
       "RELIV": lr - lr.rolling(252, min_periods=126).mean(), "DRELIV5": lr - lr.shift(5),
       "IVlevel_rel": lr}
pd.set_option("display.width", 200)
for h in [5, 21]:
    fwd = np.log1p(H).rolling(h).sum().shift(-h)
    dates = C.index[::h]
    rows = {}
    for sn, S in SIG.items():
        for pn, (a, b) in SPL.items():
            dd = dates[(dates >= a) & (dates <= b)]
            ics = []
            for d in dd:
                s, y = S.loc[d], fwd.loc[d]
                ok = s.notna() & y.notna()
                if ok.sum() >= 4:
                    ics.append(s[ok].rank().corr(y[ok].rank()))
            ics = np.array(ics)
            rows.setdefault(sn, {})[pn] = f"{ics.mean():6.3f} (t {ics.mean() / ics.std() * np.sqrt(len(ics)):5.2f}, n {len(ics)})"
    print(f"\n=== cross-sectional rank IC, horizon {h} sessions"); print(pd.DataFrame(rows).T.to_string())
    # time-series slope per name (pooled z within name)
    rows = {}
    for sn, S in SIG.items():
        z = (S - S.rolling(252, min_periods=126).mean()) / S.rolling(252, min_periods=126).std()
        for pn, (a, b) in SPL.items():
            dd = dates[(dates >= a) & (dates <= b)]
            zz = z.reindex(dd).stack(); yy = fwd.reindex(dd).stack()
            d_ = pd.concat([zz, yy], axis=1).dropna()
            X = d_.iloc[:, 0] - d_.iloc[:, 0].mean(); Y = d_.iloc[:, 1]
            bt = (X * Y).sum() / (X ** 2).sum(); res = Y - Y.mean() - bt * X
            t = bt / np.sqrt((res ** 2).sum() / (len(d_) - 2) / (X ** 2).sum())
            rows.setdefault(sn, {})[pn] = f"{bt*1e4:6.1f}bp (t {t:5.2f})"
    print(f"--- pooled TS slope of hedged spread on own z-signal, horizon {h}"); print(pd.DataFrame(rows).T.to_string())

# global VRP -> basket timing (Bollerslev et al.): avg VRP across names incl. SPY
gv = (IV[NAMES + ["SPY"]] - RV[NAMES + ["SPY"]]).mean(axis=1)
gz = (gv - gv.rolling(252, min_periods=126).mean()) / gv.rolling(252, min_periods=126).std()
bask = R[NAMES].mean(axis=1)
for h in [5, 21]:
    y = np.log1p(bask).rolling(h).sum().shift(-h); ys = np.log1p(R.SPY).rolling(h).sum().shift(-h)
    dates = C.index[::h]
    for nm, yy in [("basket", y), ("SPY", ys)]:
        out = []
        for pn, (a, b) in SPL.items():
            dd = dates[(dates >= a) & (dates <= b)]
            d_ = pd.concat([gz.reindex(dd), yy.reindex(dd)], axis=1).dropna()
            X = d_.iloc[:, 0] - d_.iloc[:, 0].mean(); Y = d_.iloc[:, 1]
            bt = (X * Y).sum() / (X ** 2).sum(); res = Y - Y.mean() - bt * X
            out.append(f"{pn} {bt*1e4:6.1f}bp t {bt / np.sqrt((res ** 2).sum() / (len(d_) - 2) / (X ** 2).sum()):5.2f}")
        print(f"global VRP z -> {nm} next {h}: " + " | ".join(out))
