"""Backtest of the Treasury flow-calendar legs on TLT / IEF.

Split fixed before any backtest was run:
    PRE  2002-07 .. 2009-12   (never looked at in the event study -- true holdout)
    IS   2010-01 .. 2017-12
    OOS  2018-01 .. 2026-09
Cost: 2 bp per side headline (TLT quoted spread ~1 bp), sensitivity shown.
"""
import os, sys, itertools
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../../shared"))
sys.path.insert(0, HERE)
import research_lib as rl
import calendars as cal
from event_study import month_end_offsets

ANN = 252
SPLITS = {"PRE 2002-09": ("2002-07-30", "2009-12-31"),
          "IS 2010-17": ("2010-01-01", "2017-12-31"),
          "OOS 2018-26": ("2018-01-01", "2026-12-31"),
          "FULL 2010-26": ("2010-01-01", "2026-12-31")}


def load_close(t):
    a = rl.load_series(t)["Close"]
    p = os.path.join(rl.DATA_DIR, f"{t}_d_pre2010.parquet")
    if os.path.exists(p):
        b = pd.read_parquet(p)["Close"]
        a = pd.concat([b[b.index < a.index[0]], a])
    return a.sort_index()


# ------------------------------------------------------------------ signal legs
# Each leg returns the weight to hold FROM close t TO close t+1 (research_lib shifts by 1).
# So a leg that wants to earn the return of day D sets weight=1 on the trading day before D.

def _prev_day_flags(index, target_dates):
    """weight=1 on the trading day *before* each date in target_dates (so it earns that date's return)."""
    pos = pd.Series(np.arange(len(index)), index=index)
    w = pd.Series(0.0, index=index)
    tgt = index.intersection(pd.DatetimeIndex(target_dates))
    p = pos.reindex(tgt).values.astype(int) - 1
    p = p[p >= 0]
    w.iloc[p] = 1.0
    return w


def leg_month_end(index, n_days=3):
    """Long over the last n trading days of the month (earn returns of days e-(n-1)..e0)."""
    k_end, _ = month_end_offsets(index)
    days = index[(k_end >= -(n_days - 1)) & (k_end <= 0)]
    return _prev_day_flags(index, days)


def leg_month_start(index, days=(3, 5)):
    """Short on selected days into the new month (reversal of the month-end richening)."""
    _, k_start = month_end_offsets(index)
    d = index[k_start.isin(days)]
    return -_prev_day_flags(index, d)


def leg_fomc(index, before=1, on=True):
    """Long the `before` days before an FOMC statement day and (optionally) the day itself."""
    ev = cal.load("fomc")
    ev = ev[(ev >= index[0]) & (ev <= index[-1])]
    p0 = index.searchsorted(ev.values)          # position of first trading day >= event
    days = []
    for p in p0:
        ks = list(range(-before, 0)) + ([0] if on else [])
        days += [index[p + k] for k in ks if 0 <= p + k < len(index)]
    return _prev_day_flags(index, days)


def leg_pre_auction(index, tenors=("10y", "20y"), days_before=2):
    """Short the `days_before` trading days ahead of each auction in `tenors` (concession)."""
    auc = cal.load("auctions")
    ev = auc.loc[auc.tenor.isin(tenors), "auction_date"].drop_duplicates()
    ev = ev[(ev >= index[0]) & (ev <= index[-1])]
    p0 = index.searchsorted(ev.values)
    days = []
    for p in p0:
        days += [index[p + k] for k in range(-days_before, 0) if 0 <= p + k < len(index)]
    return -_prev_day_flags(index, days)


def leg_post_auction(index, tenors=("10y", "30y"), days_after=(1, 2)):
    """Long selected days after an auction (recovery)."""
    auc = cal.load("auctions")
    ev = auc.loc[auc.tenor.isin(tenors), "auction_date"].drop_duplicates()
    ev = ev[(ev >= index[0]) & (ev <= index[-1])]
    p0 = index.searchsorted(ev.values)
    days = []
    for p in p0:
        days += [index[p + k] for k in days_after if 0 <= p + k < len(index)]
    return _prev_day_flags(index, days)


def combine(legs, cap=1.0):
    w = sum(legs)
    return w.clip(-cap, cap)


# ------------------------------------------------------------------ evaluation

def evaluate(w, close, cost_bps=2.0, name=""):
    net, st = rl.backtest(w, close, cost_bps=cost_bps, ann=ANN, name=name)
    rows = {}
    for k, (a, b) in SPLITS.items():
        seg = net.loc[a:b]
        if len(seg) < 50:
            continue
        s = rl.perf_stats(seg, ann=ANN, name=k)
        we = w.shift(1).loc[a:b]
        s["AvgExpo"] = we.abs().mean()
        s["Turn/yr"] = (we - we.shift(1)).abs().sum() / (len(we) / ANN)
        rows[k] = s
    df = pd.DataFrame(rows).T
    return net, df[["Sharpe", "CAGR", "Vol", "MaxDD", "HitRate", "t_NW", "AvgExpo", "Turn/yr", "N"]]


def main():
    pd.set_option("display.width", 220, "display.max_columns", 30)
    close = {t: load_close(t) for t in ["TLT", "IEF", "SHY"]}
    tlt = close["TLT"]; idx = tlt.index

    legs = {
        "month_end3": leg_month_end(idx, 3),
        "month_end2": leg_month_end(idx, 2),
        "month_end4": leg_month_end(idx, 4),
        "month_start_short": leg_month_start(idx, (3, 5)),
        "fomc_1b+0": leg_fomc(idx, 1, True),
        "fomc_0": leg_fomc(idx, 0, True),
        "fomc_2b+0": leg_fomc(idx, 2, True),
        "pre_auc_10y20y_2d": leg_pre_auction(idx, ("10y", "20y"), 2),
        "pre_auc_10y_2d": leg_pre_auction(idx, ("10y",), 2),
        "pre_auc_10y20y_1d": leg_pre_auction(idx, ("10y", "20y"), 1),
        "pre_auc_10y20y_3d": leg_pre_auction(idx, ("10y", "20y"), 3),
        "pre_auc_10y30y20y_2d": leg_pre_auction(idx, ("10y", "30y", "20y"), 2),
        "post_auc_10y30y_12": leg_post_auction(idx, ("10y", "30y"), (1, 2)),
    }
    print("\n##### single legs on TLT, 2 bp/side #####")
    for n, w in legs.items():
        _, df = evaluate(w, tlt, 2.0, n)
        print(f"\n--- {n}")
        print(rl.fmt(df).to_string())

    print("\n##### combinations on TLT (a-priori core = month_end3 + fomc_1b+0 + pre_auc_10y20y_2d) #####")
    combos = {
        "core3": ["month_end3", "fomc_1b+0", "pre_auc_10y20y_2d"],
        "core3+post": ["month_end3", "fomc_1b+0", "pre_auc_10y20y_2d", "post_auc_10y30y_12"],
        "core3+mstart": ["month_end3", "fomc_1b+0", "pre_auc_10y20y_2d", "month_start_short"],
        "me3+fomc": ["month_end3", "fomc_1b+0"],
        "me3+preauc": ["month_end3", "pre_auc_10y20y_2d"],
        "all5": ["month_end3", "fomc_1b+0", "pre_auc_10y20y_2d", "post_auc_10y30y_12", "month_start_short"],
    }
    results = {}
    for n, parts in combos.items():
        w = combine([legs[p] for p in parts])
        net, df = evaluate(w, tlt, 2.0, n)
        results[n] = net
        print(f"\n--- {n}: {parts}")
        print(rl.fmt(df).to_string())

    print("\n##### core3 on IEF, SHY, and TLT/IEF 50-50 #####")
    w = combine([legs[p] for p in combos["core3"]])
    for t in ["IEF", "SHY"]:
        wi = w.reindex(close[t].index).fillna(0.0)
        _, df = evaluate(wi, close[t], 2.0, t)
        print(f"\n--- core3 on {t}"); print(rl.fmt(df).to_string())

    print("\n##### cost sensitivity, core3 on TLT #####")
    for c in [0, 1, 2, 3, 5, 10]:
        _, df = evaluate(w, tlt, c, f"{c}bp")
        print(f"{c:>3} bp/side:", df["Sharpe"].round(2).to_dict())

    results_df = pd.DataFrame(results)
    results_df.to_parquet(os.path.join(HERE, "combo_returns.parquet"))


if __name__ == "__main__":
    main()
