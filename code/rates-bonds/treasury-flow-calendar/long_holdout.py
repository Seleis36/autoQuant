"""1990-2009 holdout on synthetic constant-maturity bonds built from ^TNX (10y) and ^TYX (30y).

Daily return of a par bond at constant maturity T with yield y (annual %, semi-annual coupons):
    r_t = -D_mod(y_{t-1}) * (y_t - y_{t-1})/100 + (y_{t-1}/100)/252
This is a standard approximation and ignores convexity and roll-down; both are second-order at
a daily horizon. The 2010-26 overlap with TLT/IEF is printed as a sanity check on the proxy.
"""
import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../../shared"))
sys.path.insert(0, HERE)
import research_lib as rl
import backtest_calendar as bc
from event_study import month_end_offsets

ANN = 252; COST = 2.0


def load_yield(t):
    a = rl.load_series(t)["Close"]
    p = rl.daily_cache_path(t).replace("_d.parquet", "_d_pre2010.parquet")
    if os.path.exists(p):
        b = pd.read_parquet(p)["Close"]; a = pd.concat([b[b.index < a.index[0]], a])
    return a.sort_index().dropna()


def synthetic_price(y, T):
    y = y / 100.0
    c = y / 2; n = 2 * T
    dmod = ((1 - (1 + c) ** (-n)) / c) / (1 + c) / 2 * 1.0   # Macaulay of par bond / (1+y/2) ... in years
    # Macaulay duration of a par bond: (1+c)/c * (1 - (1+c)^-n) in half-years; convert to years and modify
    dmac_half = (1 + c) / c * (1 - (1 + c) ** (-n))
    dmod = dmac_half / 2 / (1 + c)
    r = -dmod.shift(1) * y.diff() + y.shift(1) / 252
    return (1 + r.fillna(0)).cumprod()


def stats(w, close, name, windows):
    net, _ = rl.backtest(w, close, COST, ANN, name)
    out = {}
    for k, (a, b) in windows.items():
        seg = net.loc[a:b]
        if len(seg) > 100:
            s = rl.perf_stats(seg, ANN); out[k] = {"Sharpe": round(s["Sharpe"], 2), "CAGR%": round(s["CAGR"] * 100, 1), "t_NW": round(s["t_NW"], 2)}
    return pd.DataFrame(out).T


def main():
    pd.set_option("display.width", 220)
    y10 = load_yield("^TNX"); y30 = load_yield("^TYX")
    p10 = synthetic_price(y10, 10); p30 = synthetic_price(y30, 30)
    tlt = bc.load_close("TLT"); ief = bc.load_close("IEF")
    # proxy sanity: correlation of daily returns with the ETFs on the overlap
    for nm, p, e in [("10y vs IEF", p10, ief), ("30y vs TLT", p30, tlt)]:
        a = p.pct_change(); b = e.pct_change(); j = pd.concat([a, b], axis=1).dropna().loc["2010":]
        print(f"proxy check {nm}: corr {j.corr().iloc[0,1]:.3f}, vol {j.iloc[:,0].std()*np.sqrt(252)*100:.1f}% vs {j.iloc[:,1].std()*np.sqrt(252)*100:.1f}%")

    windows = {"1990-99": ("1990-01-01", "1999-12-31"), "2000-09": ("2000-01-01", "2009-12-31"),
               "1990-09": ("1990-01-01", "2009-12-31"), "2010-26": ("2010-01-01", "2026-12-31")}
    for nm, p, tenors in [("synthetic 10y", p10, ("10y",)), ("synthetic 30y", p30, ("10y", "30y"))]:
        idx = p.index
        legs = {"month_end3": bc.leg_month_end(idx, 3),
                "fomc_1b+0": bc.leg_fomc(idx, 1, True),
                "pre_auc_2d": bc.leg_pre_auction(idx, tenors + ("20y",), 2),
                "post_auc_12": bc.leg_post_auction(idx, tenors, (1, 2)),
                "month_start_short35": bc.leg_month_start(idx, (3, 5))}
        print(f"\n################ {nm}: auctions {tenors}+20y ################")
        for n, w in legs.items():
            print(f"--- {n}"); print(stats(w, p, n, windows).to_string())
        for cn, parts in {"core3": ["month_end3", "fomc_1b+0", "pre_auc_2d"], "me3+fomc": ["month_end3", "fomc_1b+0"]}.items():
            print(f"--- {cn}"); print(stats(bc.combine([legs[x] for x in parts]), p, cn, windows).to_string())

    # ---- diagnostic: month-end return by calendar month, refunding months (Feb/May/Aug/Nov) vs others
    print("\n################ month-end3 daily return by month-of-year (bp), 30y synthetic 1990-2009 vs TLT 2010-26 ################")
    for nm, p, lo, hi in [("30y synth", p30, "1990", "2009"), ("TLT", tlt, "2010", "2026")]:
        r = p.pct_change().loc[lo:hi]; k_end, _ = month_end_offsets(r.index)
        sel = r[(k_end >= -2)]
        g = sel.groupby(sel.index.month)
        print(nm, (g.mean() * 1e4).round(1).to_dict(), " | refunding-months mean bp:", round(sel[sel.index.month.isin([2, 5, 8, 11])].mean() * 1e4, 1),
              " others:", round(sel[~sel.index.month.isin([2, 5, 8, 11])].mean() * 1e4, 1), " quarter-end:", round(sel[sel.index.month.isin([3, 6, 9, 12])].mean() * 1e4, 1))

    # ---- LQD month-end (one variant)
    lqd = bc.load_close("LQD")
    w = bc.leg_month_end(lqd.index, 3)
    print("\n--- month_end3 on LQD"); print(stats(w, lqd, "lqd", {"2002-09": ("2002-07-30", "2009-12-31"), "2010-17": ("2010-01-01", "2017-12-31"), "2018-26": ("2018-01-01", "2026-12-31")}).to_string())


if __name__ == "__main__":
    main()
