"""etf-volume-shock -- abnormal dollar volume of country ETFs as a flow proxy.

Brown, Davies & Ringgenberg (RF 2021): ETF flows = non-fundamental demand -> negative future
returns. Gervais, Kaniel & Mingelgrin (2001): high-volume -> higher future returns (visibility).
Llorente, Michaely, Saar & Wang (2002): high-volume returns reverse when trading is liquidity-
driven (index products), continue when informed.
Signals at close t, per ETF (9 countries + EFA + EEM):
  AV5   = log(mean $vol t-4..t / mean $vol t-67..t-5)
  SAV5  = AV5 x sign(hedged 5d return)                  (signed flow proxy)
  RV5   = hedged 5d return,  RVxAV = RV5 x AV5          (LMSW interaction)
Targets: hedged spread over sessions t+2 .. t+1+h (one-session skip kills the non-synchronous
1-day reversal), h = 5, 21. Non-overlapping dates. IS 2001-2012, OOS 2013-2026."""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
import data as D

NAMES = ["EWJ", "EWG", "EWU", "EWZ", "EWY", "EWA", "EWC", "FXI", "INDA", "EFA", "EEM"]
SPL = {"FULL": ("2001-06-01", "2026-12-31"), "IS": ("2001-06-01", "2012-12-31"), "OOS": ("2013-01-01", "2026-12-31")}
C = D.load_panel(NAMES + ["SPY"], "Close", start="1998-12-01")
V = D.load_panel(NAMES + ["SPY"], "Volume", start="1998-12-01")
R = C.pct_change()
x = R["SPY"]
beta = pd.DataFrame({n: R[n].rolling(252, min_periods=126).cov(x) / x.rolling(252, min_periods=126).var() for n in NAMES})
H = R[NAMES] - beta.shift(1).mul(x, axis=0)
DV = (C * V)[NAMES]
AV5 = np.log(DV.rolling(5).mean() / DV.shift(5).rolling(63, min_periods=40).mean())
RV5 = np.log1p(H).rolling(5).sum()
RVn = RV5 / H.rolling(252, min_periods=126).std()
SIG = {"AV5": AV5, "SAV5": AV5 * np.sign(RV5), "RV5": RVn, "RVxAV": RVn * AV5,
       "AV5_hi_RV": RVn.where(AV5 > AV5.rolling(252, min_periods=126).quantile(0.8))}
pd.set_option("display.width", 200)
for h in [5, 21]:
    fwd = np.log1p(H).rolling(h).sum().shift(-(h + 1))
    dates = C.index[::h]
    ic_rows, ts_rows = {}, {}
    for sn, S in SIG.items():
        for pn, (a, b) in SPL.items():
            dd = dates[(dates >= a) & (dates <= b)]
            ics = []
            for d in dd:
                s, y = S.loc[d], fwd.loc[d]; ok = s.notna() & y.notna()
                if ok.sum() >= 5: ics.append(s[ok].rank().corr(y[ok].rank()))
            ics = np.array(ics)
            ic_rows.setdefault(sn, {})[pn] = f"{np.nanmean(ics):6.3f} (t {np.nanmean(ics) / np.nanstd(ics) * np.sqrt(np.isfinite(ics).sum()):5.2f})"
            d_ = pd.concat([S.reindex(dd).stack(), fwd.reindex(dd).stack()], axis=1).dropna()
            X = d_.iloc[:, 0] - d_.iloc[:, 0].mean(); Y = d_.iloc[:, 1]
            bt = (X * Y).sum() / (X ** 2).sum(); res = Y - Y.mean() - bt * X
            ts_rows.setdefault(sn, {})[pn] = f"{bt*1e4:7.1f} (t {bt / np.sqrt((res ** 2).sum() / (len(d_) - 2) / (X ** 2).sum()):5.2f})"
    print(f"\n=== horizon {h}: cross-sectional rank IC"); print(pd.DataFrame(ic_rows).T.to_string())
    print(f"--- horizon {h}: pooled slope (bp per unit signal)"); print(pd.DataFrame(ts_rows).T.to_string())
