"""equity-credit-lead-lag -- round 2: rank ICs and tradable books.

Pre-registered direction (the lead-lag hypothesis): after equities rise (fall), the credit
premium catches up (down) -> weight = +sign(predictor). For the residual predictor, positive
= credit lagged equities -> long credit.

Books on the duration-stripped premia (HY, JNK, IG, EM), held h days (tranched: 1/h of the
book re-set each day), cost 2 bp/side on gross turnover of both legs.
Variants: all days | only days where |z(predictor)| > 1.5 (large equity moves; z on a
trailing 252-day std).
Split: IS 2007-04 -> 2017, OOS 2018 -> 2026 (JNK/EMB start 2010).
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from importlib import import_module  # noqa: E402
scr = import_module("01_screen")

pd.set_option("display.width", 220)
COST = 2e-4


def sh(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(252) if len(x) > 200 and x.std() > 0 else np.nan


def main():
    r, cr = scr.load()
    spy = r["SPY"]
    rows, ics = [], []
    for k in cr.columns:
        y = cr[k]
        hedge = scr.HEDGE[k][1]
        beta = y.rolling(252, min_periods=126).cov(spy) / spy.rolling(252, min_periods=126).var()
        for kk in (1, 2, 5):
            preds = {"spy": spy.rolling(kk).sum(),
                     "resid": -(y.rolling(kk).sum() - beta * spy.rolling(kk).sum())}
            for pname, p in preds.items():
                zp = p / p.rolling(252, min_periods=126).std()
                for h in (1, 5):
                    fwd = y[::-1].rolling(h).sum()[::-1].shift(-1)
                    d = pd.concat([p, fwd], axis=1).dropna().iloc[::max(h, kk)]
                    for sp, (a, b) in {"IS": ("2007-04", "2017"), "OOS": ("2018", "2026")}.items():
                        dd = d.loc[a:b]
                        ics.append(dict(credit=k, pred=pname, k=kk, h=h, split=sp,
                                        ic=dd.iloc[:, 0].corr(dd.iloc[:, 1], method="spearman")))
                    for filt in ("all", "big"):
                        s = np.sign(zp)
                        if filt == "big":
                            s = s.where(zp.abs() > 1.5, 0.0)
                        w = s.rolling(h, min_periods=1).mean().fillna(0)        # h tranches
                        we = w.shift(1).fillna(0)
                        net = we * y - we.diff().abs().fillna(0) * (1 + hedge) * COST
                        rows.append(dict(credit=k, pred=pname, k=kk, h=h, filt=filt,
                                         IS=sh(net.loc["2007-04":"2017"]), OOS=sh(net.loc["2018":]),
                                         expo=we.abs().mean()))
    ic = pd.DataFrame(ics)
    bk = pd.DataFrame(rows)
    bk.to_csv(os.path.join(_HERE, "02_books.csv"), index=False)
    print("=== Spearman IC (non-overlapping), pre-registered sign ===")
    print(ic.pivot_table(index=["credit", "pred", "k", "h"], columns="split", values="ic").round(3).to_string())
    print(f"\n=== books, 2bp/side: {len(bk)} cells ===")
    print(bk.round(2).to_string(index=False))
    print(f"\nIS>0.3 cells: {(bk.IS > 0.3).sum()}, of which OOS>0.3: {((bk.IS > 0.3) & (bk.OOS > 0.3)).sum()}; "
          f"median IS {bk.IS.median():.2f}, median OOS {bk.OOS.median():.2f}, "
          f"rank corr {bk.IS.corr(bk.OOS, method='spearman'):.2f}")


if __name__ == "__main__":
    main()
