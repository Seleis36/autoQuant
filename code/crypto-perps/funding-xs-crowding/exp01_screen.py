"""exp01 — cross-sectional screen of perp-funding features, traded on spot prices.

Every feature is sorted cross-sectionally within the PIT top-20 universe; the portfolio is
long top-30% / short bottom-30% (dollar-neutral, gross 1), in both directions ("+" = long
high feature, "-" = long low feature). Holding h in {1, 7} days via staggered tranches.
10 bp/side. Reports IS/OOS Sharpe for every cell -- nothing is dropped.
"""
import numpy as np
import pandas as pd
import common as c
import research_lib as rl

close, vol, fund, mask = c.load()
ret = close.pct_change()

F = {}
for k in (1, 3, 7, 14, 30):
    F[f"fund_{k}"] = fund.rolling(k, min_periods=k).mean()
F["fund_chg_3_30"] = F["fund_3"] - F["fund_30"]
F["fund_chg_7_60"] = F["fund_7"] - fund.rolling(60, min_periods=40).mean()
mu90 = fund.rolling(90, min_periods=60).mean()
sd90 = fund.rolling(90, min_periods=60).std()
F["fund_z7_90"] = (F["fund_7"] - mu90) / sd90
F["fund_excess_7"] = F["fund_7"] - 0.0003          # distance from the 0.01%/8h default
F["fund_neg_share_14"] = (fund < 0.0003 * 0.5).astype(float).where(fund.notna()).rolling(14).mean()
for k in (7, 30):
    F[f"mom_{k}"] = close.pct_change(k)

# funding residual after cross-sectional regression on 7d and 30d momentum
def xs_resid(y, xs):
    out = pd.DataFrame(np.nan, index=y.index, columns=y.columns)
    for d in y.index:
        m = mask.loc[d]
        yy = y.loc[d][m]
        X = pd.concat([x.loc[d][m] for x in xs], axis=1)
        ok = yy.notna() & X.notna().all(axis=1)
        if ok.sum() < 8:
            continue
        A = np.column_stack([np.ones(ok.sum()), X[ok].rank().values])
        b, *_ = np.linalg.lstsq(A, yy[ok].rank().values, rcond=None)
        out.loc[d, ok[ok].index] = yy[ok].rank().values - A @ b
    return out

F["fund7_resid_mom"] = xs_resid(F["fund_7"], [F["mom_7"], F["mom_30"]])

rows = []
for fname, f in F.items():
    for sign in (+1, -1):
        for h in (1, 7):
            w = rl.quantile_weights(sign * f, mask, q=0.3, gross=1.0)
            w = c.tranche(w, h)
            _, row = c.evaluate(w, close, f"{'+' if sign > 0 else '-'}{fname}_h{h}")
            rows.append(row)
res = pd.DataFrame(rows).set_index("name")
res.to_csv("exp01_results.csv")
pd.set_option("display.width", 200)
print(rl.fmt(res).to_string())
print("cells:", len(res))
