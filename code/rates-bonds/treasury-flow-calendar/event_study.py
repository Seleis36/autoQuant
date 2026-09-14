"""Event study: daily bond-ETF returns around month-end, auctions, FOMC, CPI, payrolls.

Return on day d is close_{d-1} -> close_d. "Offset k" relative to an event date E means
the k-th trading day after E (k<0 before). A position that earns offset-0 return is set at
the close of the trading day before E, which is knowable because every calendar here is
published ahead of time.
"""
import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../../shared"))
sys.path.insert(0, HERE)
import research_lib as rl
import calendars as cal

ANN = 252
TICKERS = ["TLT", "IEF", "SHY", "AGG", "LQD", "HYG", "TIP", "SPY"]


def load_returns(start="2010-01-01"):
    px = pd.concat({t: rl.load_series(t)["Close"] for t in TICKERS}, axis=1).loc[start:]
    return px.pct_change().dropna(how="all")


def offsets_from(index: pd.DatetimeIndex, events, lo=-5, hi=5) -> pd.DataFrame:
    """For each event, map trading-day offsets lo..hi to index dates. Returns long frame."""
    pos = pd.Series(np.arange(len(index)), index=index)
    ev = pd.DatetimeIndex(sorted(set(pd.to_datetime(events))))
    ev = ev[(ev >= index[0]) & (ev <= index[-1])]
    # event date -> position of first trading day >= event date
    p0 = index.searchsorted(ev)
    rows = []
    for e, p in zip(ev, p0):
        for k in range(lo, hi + 1):
            q = p + k
            if 0 <= q < len(index):
                rows.append((e, k, index[q]))
    return pd.DataFrame(rows, columns=["event", "k", "date"])


def stats_by_offset(ret: pd.DataFrame, off: pd.DataFrame) -> pd.DataFrame:
    out = {}
    for k, g in off.groupby("k"):
        r = ret.loc[ret.index.intersection(g["date"].unique())]
        m, s, n = r.mean(), r.std(ddof=1), r.count()
        out[k] = pd.concat({"mean_bp": m * 1e4, "t": m / s * np.sqrt(n),
                            "sharpe_pa": m / s * np.sqrt(ANN), "n": n}, axis=1)
    return pd.concat(out, names=["k", "ticker"])


def month_end_offsets(index: pd.DatetimeIndex) -> pd.Series:
    """0 = last trading day of month, -1 = the one before, ... ; positive = days into new month (1 = first)."""
    s = pd.Series(index, index=index)
    ym = index.to_period("M")
    last = s.groupby(ym).transform("max")
    first = s.groupby(ym).transform("min")
    pos = pd.Series(np.arange(len(index)), index=index)
    k_end = pos - pos.reindex(last.values).values     # <= 0
    k_start = pos - pos.reindex(first.values).values + 1  # >= 1
    return k_end, k_start


def main():
    ret = load_returns()
    idx = ret.index
    pd.set_option("display.width", 200, "display.max_rows", 500)

    print("\n===== unconditional (daily, 2010->) =====")
    print(pd.concat({"mean_bp": ret.mean() * 1e4, "sharpe": ret.mean() / ret.std() * np.sqrt(ANN)}, axis=1).round(2))

    print("\n===== month-end: k=0 last trading day, -1, -2 ...; and first days of month (k_start) =====")
    k_end, k_start = month_end_offsets(idx)
    rows = {}
    for k in range(-6, 1):
        r = ret[k_end == k]
        rows[f"end{k}"] = pd.concat({"mean_bp": r.mean() * 1e4, "t": r.mean() / r.std() * np.sqrt(r.count())}, axis=1)
    for k in range(1, 5):
        r = ret[k_start == k]
        rows[f"start+{k}"] = pd.concat({"mean_bp": r.mean() * 1e4, "t": r.mean() / r.std() * np.sqrt(r.count())}, axis=1)
    print(pd.concat(rows, axis=1).round(2))

    auc = cal.load("auctions")
    for tenor in ["2y", "3y", "5y", "7y", "10y", "20y", "30y"]:
        ev = auc.loc[auc.tenor == tenor, "auction_date"]
        off = offsets_from(idx, ev, -5, 5)
        st = stats_by_offset(ret, off)
        print(f"\n===== auction {tenor}: n_events={ev[(ev>=idx[0])&(ev<=idx[-1])].nunique()} =====")
        print(st["mean_bp"].unstack("ticker").round(1))
        print(st["t"].unstack("ticker").round(2))

    for name in ["fomc", "cpi", "payrolls"]:
        ev = cal.load(name)
        off = offsets_from(idx, ev, -3, 3)
        st = stats_by_offset(ret, off)
        print(f"\n===== {name}: n_events={ev[(ev>=idx[0])&(ev<=idx[-1])].nunique()} =====")
        print(st["mean_bp"].unstack("ticker").round(1))
        print(st["t"].unstack("ticker").round(2))


if __name__ == "__main__":
    main()
