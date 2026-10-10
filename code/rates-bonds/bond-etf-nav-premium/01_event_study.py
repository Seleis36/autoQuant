"""Do the official premium and the creation/redemption flow predict the ETF's next return?

Signal at close t (NAV and shares of day t, posted that evening). Forward return over h
sessions is measured from close t+1 (one-session skip), on the fund's return residual to
IEF and HYG (trailing 120-session betas, known the day before).

Two views: (1) cross-sectional rank IC and extreme-tercile spread across the funds each day;
(2) a pooled time-series slope of the residual forward return on the within-fund z-score.
"""
import numpy as np
import pandas as pd
import nav_lib as nl

pd.set_option("display.width", 220)
d = nl.load()
ret, prem, shares = d["ret"], d["prem"], d["shares"]
b1, b2 = nl.trailing_betas(ret, d["hedge"])
res = nl.residual_returns(ret, d["hedge"], b1, b2)
liquid = (d["dv"].rolling(60, min_periods=30).median() >= 2e6) & prem.notna()
print("funds per year (liquid):", liquid.sum(axis=1).groupby(liquid.index.year).mean().round(0).to_dict())
print("premium, bp: median |prem| %.1f, std of daily change %.1f; AR(1) of prem %.2f" % (
    prem.abs().stack().dropna().median() * 1e4, prem.diff().stack().dropna().std() * 1e4,
    pd.concat([prem.stack(), prem.shift(1).stack()], axis=1).dropna().corr().iloc[0, 1]))
by_sec = (prem.diff().std() * 1e4).groupby(d["sector"]).mean().round(1)
print("std of daily premium change by sector (bp):", by_sec.to_dict())

flow1 = shares.pct_change(fill_method=None).where(lambda x: x.abs() < 0.5)
sigs = {
    "prem_dev60": prem - prem.rolling(60, min_periods=30).mean(),
    "prem_z60": nl.zscore(prem, 60), "prem_z20": nl.zscore(prem, 20), "prem_z250": nl.zscore(prem, 250),
    "prem_chg1": prem.diff(), "prem_chg5": prem.diff(5),
    "flow1": flow1, "flow5": flow1.rolling(5).sum(), "flow21": flow1.rolling(21).sum(),
    "flow5_z": nl.zscore(flow1.rolling(5).sum(), 250),
}
cum = res.fillna(0.0).cumsum()


def fwd(h, skip=1):
    return (cum.shift(-(skip + h)) - cum.shift(-skip)).where(res.notna())


rows = []
for name, s in sigs.items():
    sg = s.where(liquid)
    for h in (1, 5, 10):
        f = fwd(h).where(liquid)
        idx = sg.index[::h]
        a, b_ = sg.loc[idx], f.loc[idx]
        ic = a.rank(axis=1).corrwith(b_.rank(axis=1), axis=1)
        pr = a.rank(axis=1, pct=True)
        spread = b_.where(pr <= 1 / 3).mean(axis=1) - b_.where(pr >= 2 / 3).mean(axis=1)
        # pooled TS slope: forward residual return (bp) per 1 sd of the fund's own signal
        zs = (a - a.expanding(250).mean().shift(1)) / a.expanding(250).std().shift(1)
        for sn, (lo, hi) in nl.SPLITS.items():
            i, sp = ic.loc[lo:hi].dropna(), spread.loc[lo:hi].dropna()
            z_, f_ = zs.loc[lo:hi].stack().dropna(), b_.loc[lo:hi].stack().dropna()
            j = z_.index.intersection(f_.index)
            zz, ff = z_.loc[j].clip(-5, 5), f_.loc[j]
            slope = (zz * ff).sum() / (zz ** 2).sum() * 1e4 if len(j) > 100 else np.nan
            rows.append(dict(sig=name, h=h, split=sn, IC=i.mean(), t_IC=i.mean() / i.std() * np.sqrt(len(i)),
                             lowminushigh_bp=sp.mean() * 1e4, t_sp=sp.mean() / sp.std() * np.sqrt(len(sp)),
                             ts_slope_bp=slope))
out = pd.DataFrame(rows)
out.to_csv("01_event_study.csv", index=False)
piv = out.pivot_table(index=["sig", "h"], columns="split", values=["IC", "lowminushigh_bp", "t_sp", "ts_slope_bp"])
print(piv.reindex(columns=["IS", "OOS"], level=1).round(3).to_string())
