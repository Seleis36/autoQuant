"""bond-vrp-timing -- does the Treasury variance risk premium time duration?

Mueller, Vedolin & Yen (2017, "Bond variance risk premiums", RoF): the gap between implied and
realised Treasury volatility predicts bond excess returns (and equity returns) -- investors pay
for rate-vol insurance when the premium is high, and the term premium is high with it.

Data: ICE BofA MOVE (^MOVE, yfinance, 2002-11+): 1-month implied NORMAL vol in bp/yr, weighted
2y/5y/10y/30y = 0.2/0.2/0.4/0.2. Realised: the same weights of the daily CMT yield changes
(FRED DGS2/5/10/30, bp), annualised over 21 days -- the same units as MOVE.
Signals at the close of day t (MOVE close is ~16:00; H.15 yields are the same day's close;
live, realised vol would be computed from the ETF prices -- see 02 for that check):
  vrp     = MOVE - RV21                (bp)
  ratio   = MOVE / RV21
  move_z  = z(MOVE, trailing 252d)
  vrp_z   = z(vrp, trailing 252d)
  dmove   = MOVE change over 5 days (spike)
Tests: Spearman IC vs forward 5/21/63-day IEF/TLT excess returns (weekly samples), and books:
position = clip(z/2, +-1) (linear) or sign(z) (binary), re-set weekly (Mondays' first bar)
or monthly, 2 bp/side. Direction from the hypothesis (high premium -> long duration),
reported both ways only for the ICs.
Split fixed in advance: IS 2003-2014, OOS 2015-2026.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from rb_data import etf_close, fred, rl, ANN  # noqa: E402

pd.set_option("display.width", 220)
COST = 2e-4
W = {2: 0.2, 5: 0.2, 10: 0.4, 30: 0.2}


def z(x, win=252, minp=126):
    return (x - x.rolling(win, min_periods=minp).mean()) / x.rolling(win, min_periods=minp).std()


def build():
    mv = rl.load_series("^MOVE")["Close"].rename("MOVE")
    ys = pd.DataFrame({k: fred(f"DGS{k}") for k in W}).dropna() * 100
    dy = ys.diff()
    rv = sum(W[k] * dy[k].rolling(21).std() for k in W) * np.sqrt(ANN)
    bill = fred("DGS3MO") / 100 / ANN
    px = etf_close(["IEF", "TLT"])
    ex = px.pct_change().sub(bill.reindex(px.index).ffill().shift(1), axis=0)
    idx = ex.index.intersection(mv.index)
    f = pd.DataFrame({"MOVE": mv.reindex(idx), "RV": rv.reindex(idx).ffill(limit=3)}, index=idx)
    f["vrp"] = f.MOVE - f.RV
    f["ratio"] = f.MOVE / f.RV
    sig = pd.DataFrame({"vrp": z(f.vrp), "ratio": z(np.log(f.ratio)), "move_z": z(f.MOVE),
                        "vrp_raw": (f.vrp - f.vrp.expanding(252).mean()) / f.vrp.expanding(252).std(),
                        "dmove": z(f.MOVE.diff(5))}, index=idx)
    return f, sig, ex.reindex(idx)


def book(s, r, mode, freq, cost=COST):
    w = (s / 2).clip(-1, 1) if mode == "lin" else np.sign(s)
    per = r.index.to_period("W" if freq == "W" else "M")
    first = ~pd.Series(per, index=r.index).duplicated().values
    w = w.where(first).ffill().fillna(0)
    we = w.shift(1).fillna(0)
    return we * r - we.diff().abs().fillna(0) * cost, we


def sh(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(ANN) if len(x) > 250 and x.std() > 0 else np.nan


def main():
    f, sig, ex = build()
    print(f.describe().round(2).T.to_string())
    rows, brows = [], []
    for inst in ("IEF", "TLT"):
        r = ex[inst]
        for h in (5, 21, 63):
            fwd = r[::-1].rolling(h).sum()[::-1].shift(-1)
            for c in sig.columns:
                d = pd.concat([sig[c], fwd], axis=1).dropna()
                d = d[~d.index.to_period("W").duplicated()]
                for sp, (a, b) in {"IS": ("2003", "2014"), "OOS": ("2015", "2026")}.items():
                    dd = d.loc[a:b]
                    rows.append(dict(inst=inst, h=h, sig=c, split=sp,
                                     ic=dd.iloc[:, 0].corr(dd.iloc[:, 1], method="spearman")))
        for c in sig.columns:
            for mode in ("lin", "bin"):
                for freq in ("W", "M"):
                    net, we = book(sig[c], r, mode, freq)
                    brows.append(dict(inst=inst, sig=c, mode=mode, freq=freq, IS=sh(net.loc["2003":"2014"]),
                                      OOS=sh(net.loc["2015":]), net_long=we.mean()))
    ic = pd.DataFrame(rows)
    print("\nSpearman IC (signal high -> bond up), weekly samples")
    print(ic.pivot_table(index=["sig", "inst"], columns=["split", "h"], values="ic").round(3).to_string())
    bk = pd.DataFrame(brows)
    bk.to_csv(os.path.join(_HERE, "01_books.csv"), index=False)
    print("\nbooks (long duration when signal high), 2 bp/side")
    print(bk.round(2).to_string(index=False))
    print(f"\nIS-rank vs OOS-rank Spearman: {bk.IS.corr(bk.OOS, method='spearman'):.2f}")


if __name__ == "__main__":
    main()
