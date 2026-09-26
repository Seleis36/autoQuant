"""fx-sleeve-blend -- equal-risk blend of the four sleeves (see sleeves.py for the inclusion
rule), with a walk-forward inclusion control. Books compared (all declared up front):

  COT_only   the Working sleeve alone (reference)
  EQ4        each sleeve scaled to 5 % ex-ante vol (trailing EWMA-126d of its unit book,
             re-set weekly), averaged, then the sum re-scaled to 5 % (weekly), gross cap 3
  WF4        EQ4, but each calendar year only the sleeves whose expanding net Sharpe
             (from their first trade to the prior 31 Dec, >= 1 year of history) is > 0;
             all four in the first year
  EQ3_exCOT  EQ4 without COT (do the weak sleeves carry anything on their own?)
Costs at the blend level (legs net across sleeves): measured 00:00 UTC half-spreads.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, HERE)
from fx_panel import ANN, CCYS, backtest, cost_frame, load_px, split_table  # noqa: E402
from research_lib import perf_stats  # noqa: E402
from sleeves import SLEEVES  # noqa: E402

VOL, HL, CAP = 0.05, 126, 3.0


def weekly_first(idx):
    s = pd.Series(idx, index=idx)
    return s.groupby(idx.to_period("W-SUN")).transform("min").eq(s).values


def vol_scale(W, px, target=VOL):
    _, g, _, _ = backtest(W, px, cost=0.0)
    v = g.ewm(halflife=HL, min_periods=60).std() * np.sqrt(ANN)
    # every sleeve's unit book has sum|w| <= 1, so k <= CAP keeps each sleeve's gross <= CAP;
    # v == 0 (sleeve not yet trading) -> no position
    k = (target / v.where(v > 0)).clip(upper=CAP)
    first = weekly_first(px.index)
    k = pd.Series(np.where(first, k, np.nan), index=px.index).ffill().fillna(0.0)
    return W.mul(k, axis=0)


def cap(W):
    g = W.abs().sum(axis=1)
    return W.mul((CAP / g).clip(upper=1.0).fillna(1.0), axis=0)


def build(px, which=None):
    raw = {k: f(px).reindex(px.index).fillna(0.0)[CCYS] for k, f in SLEEVES.items() if which is None or k in which}
    scaled = {k: (v if k == "COT" else vol_scale(v, px)) for k, v in raw.items()}
    return scaled


def blend(scaled, px, include=None):
    """include: DataFrame date x sleeve of 0/1 (None = all)."""
    ks = list(scaled)
    if include is None:
        include = pd.DataFrame(1.0, index=px.index, columns=ks)
    n = include[ks].sum(axis=1).replace(0, np.nan)
    W = sum(scaled[k].mul(include[k], axis=0) for k in ks).div(n, axis=0).fillna(0.0)
    return cap(vol_scale(W, px))


def wf_include(scaled, px):
    nets = {k: backtest(v, px, cost=None)[0] for k, v in scaled.items()}
    inc = pd.DataFrame(1.0, index=px.index, columns=list(scaled))
    years = sorted(set(px.index.year))
    for y in years[1:]:
        for k, n in nets.items():
            live = n[n != 0]
            hist = live.loc[: f"{y - 1}-12-31"]
            if len(hist) >= 250:
                sr = hist.mean() / hist.std() * np.sqrt(ANN)
                inc.loc[str(y), k] = float(sr > 0)
    return inc


def report(name, W, px, rows, nets):
    net, gross, turn, st = backtest(W, px, cost=None, name=name)
    t = split_table(net)
    n2, *_ = backtest(W, px, cost=cost_frame(px.index, mult=2))
    n1, *_ = backtest(W, px, cost=1.0)
    rows.append({"book": name, "FULL": t.loc["FULL", "Sharpe"], "IS": t.loc["IS", "Sharpe"], "OOS": t.loc["OOS", "Sharpe"],
                 "t": t.loc["FULL", "t_NW"], "CAGR": st["CAGR"], "Vol": st["Vol"], "MaxDD": st["MaxDD"],
                 "turn": st["Turnover_ann"], "gross": st["AvgGross"], "maxgross": W.abs().sum(axis=1).max(),
                 "cost_bp": st["CostDrag_bp"], "SR_x2": perf_stats(n2, ann=ANN)["Sharpe"],
                 "SR_1bp": perf_stats(n1, ann=ANN)["Sharpe"], "OOS_1bp": perf_stats(n1.loc["2020":], ann=ANN)["Sharpe"]})
    nets[name] = net


def main():
    px = load_px()
    S = build(px)
    rows, nets = [], {}
    for k, v in S.items():
        report(f"sleeve_{k}", v, px, rows, nets)
    report("COT_only", S["COT"], px, rows, nets)
    report("EQ4", blend(S, px), px, rows, nets)
    inc = wf_include(S, px)
    report("WF4", blend(S, px, inc), px, rows, nets)
    report("EQ3_exCOT", blend({k: v for k, v in S.items() if k != "COT"}, px), px, rows, nets)
    df = pd.DataFrame(rows).set_index("book")
    pd.set_option("display.width", 250)
    print(df.round(3).to_string())
    N = pd.DataFrame(nets)
    print("\nsleeve correlations (daily net):")
    print(N[[c for c in N if c.startswith("sleeve_")]].corr().round(2).to_string())
    print("\nWF inclusion by year:")
    print(inc.groupby(inc.index.year).first().astype(int).to_string())
    print("\nper-year Sharpe:")
    print(N[["COT_only", "EQ4", "WF4"]].groupby(N.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(ANN)).round(2).to_string())
    df.to_csv(os.path.join(HERE, "01_blend.csv"))
    N.to_parquet(os.path.join(HERE, "01_blend_nets.parquet"))


if __name__ == "__main__":
    main()
