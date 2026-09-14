"""Round 2: principled (un-mined) leg definitions and instrument choice, plus walk-forward.

Legs added here are defined by the literature's description, not by the best cell of the
event table:
  * month_start_short_all5 : short every one of the first 5 trading days (HS reversal)
  * mid_month_settle       : long the 2 trading days after the 15th (coupon + refunding
                             settlement reinvestment)
  * pre_auc_5d_10y30y      : LYZ's own window, 5 days before 10y/30y auctions, on TLT
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


def leg_month_start_all(index, n=5):
    _, k_start = month_end_offsets(index)
    d = index[(k_start >= 1) & (k_start <= n)]
    return -bc._prev_day_flags(index, d)


def leg_mid_month_settle(index, days=(1, 2)):
    """Long the `days`-th trading days on/after the 15th of each month."""
    s = pd.Series(index, index=index)
    ym = index.to_period("M")
    days_sel = []
    for p, g in s.groupby(ym):
        after = g[g >= pd.Timestamp(p.year, p.month, 15)]
        for d in days:
            if len(after) >= d:
                days_sel.append(after.iloc[d - 1])
    return bc._prev_day_flags(index, days_sel)


def evaluate_set(name, w, close):
    _, df = bc.evaluate(w, close, COST, name)
    print(f"\n--- {name}"); print(rl.fmt(df)[["Sharpe", "CAGR", "MaxDD", "AvgExpo", "Turn/yr"]].to_string())
    return df


def walk_forward(legs, cands, close, thr=1.0, first_year=2010, label=""):
    idx = close.index
    nets = {c: rl.backtest(legs[c], close, COST, ANN, c)[0] for c in cands}
    wf_w = pd.Series(0.0, index=idx); log = {}
    for y in range(first_year, idx[-1].year + 1):
        train = slice(None, f"{y-1}-12-31"); keep = []
        for c in cands:
            r = nets[c].loc[train]; r = r[legs[c].shift(1).loc[train].abs() > 0]
            if len(r) > 60 and rl.newey_west_t(r.values, lags=5) > thr:
                keep.append(c)
        log[y] = keep
        if keep:
            wf_w.loc[str(y)] = bc.combine([legs[c] for c in keep]).loc[str(y)]
    net, _ = rl.backtest(wf_w, close, COST, ANN, "wf")
    sub = net.loc[str(first_year):]
    p = lambda s: rl.perf_stats(s, ANN)
    print(f"  WF {label} thr={thr}: {first_year}-26 Sharpe {p(sub)['Sharpe']:.2f} | -2017 {p(sub.loc[:'2017'])['Sharpe']:.2f} | 2018- {p(sub.loc['2018':])['Sharpe']:.2f} | CAGR {p(sub)['CAGR']*100:.1f}% MaxDD {p(sub)['MaxDD']*100:.1f}% | last-year set {log[max(log)]}")
    return net, wf_w, log


def build_legs(idx):
    return {
        "month_end3": bc.leg_month_end(idx, 3),
        "month_end2": bc.leg_month_end(idx, 2),
        "month_end4": bc.leg_month_end(idx, 4),
        "month_start_short35": bc.leg_month_start(idx, (3, 5)),
        "month_start_short_all5": leg_month_start_all(idx, 5),
        "month_start_short_all3": leg_month_start_all(idx, 3),
        "mid_month_settle": leg_mid_month_settle(idx, (1, 2)),
        "fomc_1b+0": bc.leg_fomc(idx, 1, True),
        "pre_auc_10y20y_2d": bc.leg_pre_auction(idx, ("10y", "20y"), 2),
        "pre_auc_5d_10y30y": bc.leg_pre_auction(idx, ("10y", "30y"), 5),
        "post_auc_10y30y_12": bc.leg_post_auction(idx, ("10y", "30y"), (1, 2)),
    }


def main():
    pd.set_option("display.width", 220, "display.max_columns", 40)
    close = {t: bc.load_close(t) for t in ["TLT", "IEF"]}
    for t in ["TLT", "IEF"]:
        c = close[t]; idx = c.index; legs = build_legs(idx)
        print(f"\n################ {t} ################")
        for n in ["month_end3", "month_end2", "month_end4", "month_start_short_all5", "month_start_short_all3",
                  "mid_month_settle", "pre_auc_5d_10y30y", "fomc_1b+0"]:
            evaluate_set(n, legs[n], c)
        combos = {
            "core3": ["month_end3", "fomc_1b+0", "pre_auc_10y20y_2d"],
            "core3+ms_all5": ["month_end3", "fomc_1b+0", "pre_auc_10y20y_2d", "month_start_short_all5"],
            "core3+ms_all3": ["month_end3", "fomc_1b+0", "pre_auc_10y20y_2d", "month_start_short_all3"],
            "me3+fomc+ms_all5": ["month_end3", "fomc_1b+0", "month_start_short_all5"],
            "me3+fomc+preauc5d": ["month_end3", "fomc_1b+0", "pre_auc_5d_10y30y"],
            "me3+ms_all5": ["month_end3", "month_start_short_all5"],
        }
        for n, parts in combos.items():
            evaluate_set(n, bc.combine([legs[p] for p in parts]), c)
        print(f"\n--- walk-forward on {t}")
        cands = ["month_end3", "month_start_short_all5", "mid_month_settle", "fomc_1b+0",
                 "pre_auc_10y20y_2d", "pre_auc_5d_10y30y", "post_auc_10y30y_12"]
        for thr in (0.5, 1.0, 1.5):
            walk_forward(legs, cands, c, thr, 2010, t)


if __name__ == "__main__":
    main()
