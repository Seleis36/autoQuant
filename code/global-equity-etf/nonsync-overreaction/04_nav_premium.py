"""Levy-Lieberman premium: ETF close vs a NAV proxy (local index close x synchronous FX ETF).
premium_t = log ETF_t - log Local_t - log FX_t, minus its trailing 20d mean (absorbs dividends,
index mismatch, tracking). Does it predict the next-day SPY-hedged ETF return beyond the
US-session residual u_t?  Sample 2007+ (FX ETFs list 2005-07)."""
from lib import *
import statsmodels.api as sm
MAP = {"EWJ": ("^N225", "FXY", 1), "EWA": ("^AXJO", "FXA", 1), "EWY": ("^KS11", "KRW=X", -1),
       "INDA": ("^NSEI", "INR=X", -1), "FXI": ("^HSI", None, 0), "EWG": ("^GDAXI", "FXE", 1),
       "EWU": ("^FTSE", "FXB", 1)}
tick = list(MAP) + ["SPY"] + [v[0] for v in MAP.values()] + [v[1] for v in MAP.values() if v[1]]
C = D.load_panel(tick, "Close", start="2007-01-01")
O = D.load_panel(list(MAP) + ["SPY"], "Open", start="2007-01-01")
r = C.pct_change()
u, z = residual_signal(C, O, list(MAP))
bcc = rolling_beta(r[list(MAP)], r["SPY"], 250)
rows = []
for etf, (loc, fx, sgn) in MAP.items():
    lp = np.log(C[etf]) - np.log(C[loc])
    if fx: lp = lp - sgn * np.log(C[fx])
    prem = lp - lp.rolling(20).mean()
    pz = prem / prem.rolling(250, min_periods=120).std().shift(1)
    h1 = (r[etf] - bcc[etf].shift(1) * r["SPY"]).shift(-1)
    for per, (a, b) in {"IS": ("2007", "2012"), "OOS": ("2013", "2026")}.items():
        df = pd.DataFrame({"h1": h1, "pz": pz, "uz": z[etf]}).loc[a:b].dropna()
        m = sm.OLS(df.h1 * 1e4, sm.add_constant(df[["pz", "uz"]])).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
        rows.append({"etf": etf, "per": per, "n": len(df), "corr_pz_uz": df.pz.corr(df.uz),
                     "IC_pz": df.pz.corr(df.h1, method="spearman"), "IC_uz": df.uz.corr(df.h1, method="spearman"),
                     "b_pz(bp/sd)": m.params.pz, "t_pz": m.tvalues.pz, "b_uz": m.params.uz, "t_uz": m.tvalues.uz})
print(pd.DataFrame(rows).set_index(["etf", "per"]).round(3).to_string())
