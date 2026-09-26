"""cot-positioning -- final composite, pre-registered before running (only these four books):

  A  CP_legacy      : mean(-z level, -z 4w change) of legacy non-commercial net share (= 02 base:CP)
  B  CP_tff         : same two legs for TFF leveraged funds AND asset managers (4 legs, mean)
  C  CP_all         : mean of the 6 legs (legacy nc + TFF lev + TFF am)
  D  CP_all_riskpar : C, with each currency's weight divided by its trailing 60d EWMA vol
                      (so every currency contributes comparable risk), then demeaned again
                      in risk space and rescaled to sum|w| = 1.
Each book is scaled to 5 % ex-ante annual vol (trailing 126d EWMA of the unit book, sampled
weekly), gross capped at 3. Costs: measured 00:00 UTC half-spreads. Also: cost x2 / x3 /
flat 1 bp, per-year table, and a stationary block bootstrap of the OOS Sharpe.
"""
import os
import sys
import importlib

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, HERE)
from fx_panel import CCYS, ANN, backtest, cost_frame, load_px, split_table, usd_per_ccy  # noqa: E402
from fetch_cot_fx import fetch_legacy, fetch_tff, net_share, on_fx_rows  # noqa: E402
from research_lib import perf_stats  # noqa: E402
s01 = importlib.import_module("01_screen")
s02 = importlib.import_module("02_refine")
zts = s02.zts


def legs(win=156, dh=4):
    lg = fetch_legacy()
    lg = lg[lg["date"] >= "1995-01-01"]
    tf = fetch_tff()
    out = {}
    for tag, frame, grp in (("nc", lg, "nc"), ("lev", tf, "lev"), ("am", tf, "am")):
        ns = net_share(frame, grp)[CCYS]
        out[f"{tag}_level"] = -zts(ns, win)
        out[f"{tag}_chg"] = -zts(ns.diff(dh), win)
    return out


def combine(parts):
    """Mean of legs on the union of availability stamps (each leg forward-filled)."""
    ix = sorted(set().union(*[p.index for p in parts]))
    al = [p.reindex(ix).ffill() for p in parts]
    return sum(al) / len(al)


def weekly_first(idx):
    s = pd.Series(idx, index=idx)
    return s.groupby(idx.to_period("W-SUN")).transform("min").eq(s).values


def book(sig_rows, px, riskpar=False, vol_target=0.05, cap=3.0):
    idx = px.index
    first = weekly_first(idx)
    W = s01.xs(sig_rows)
    if riskpar:
        r = np.log(usd_per_ccy(px)).diff()
        v = r.ewm(halflife=60, min_periods=40).std() * np.sqrt(ANN)
        W = (sig_rows[CCYS].sub(sig_rows[CCYS].mean(axis=1), axis=0)) / v
        W = W.sub(W.mean(axis=1), axis=0)
        W = W.div(W.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    W = W.reindex(idx)[first].reindex(idx).ffill().fillna(0.0)
    _, g, _, _ = backtest(W, px, cost=0.0)
    vol = g.ewm(halflife=126, min_periods=60).std() * np.sqrt(ANN)
    k = (vol_target / vol).clip(upper=cap / W.abs().sum(axis=1).replace(0, np.nan).max())
    k = pd.Series(np.where(first, k, np.nan), index=idx).ffill().fillna(0.0)
    return W.mul(k, axis=0)


def block_boot(x, n=2000, block=21, seed=1):
    rng = np.random.default_rng(seed)
    x = np.asarray(x)
    T = len(x)
    out = np.empty(n)
    for i in range(n):
        starts = rng.integers(0, T - block, size=T // block + 1)
        s = np.concatenate([x[a:a + block] for a in starts])[:T]
        out[i] = s.mean() / s.std() * np.sqrt(ANN)
    return out


def main():
    px = load_px()
    idx = px.index
    L = legs()
    books = {
        "A_CP_legacy": combine([L["nc_level"], L["nc_chg"]]),
        "B_CP_tff": combine([L["lev_level"], L["lev_chg"], L["am_level"], L["am_chg"]]),
        "C_CP_all": combine(list(L.values())),
    }
    AV = s01.avail_all()
    rows, nets, W_all = [], {}, {}
    for name, sig in list(books.items()) + [("D_CP_all_riskpar", books["C_CP_all"])]:
        s_rows = on_fx_rows(sig, idx, AV)
        W = book(s_rows, px, riskpar=name.startswith("D"))
        W_all[name] = W
        net, gross, turn, st = backtest(W, px, cost=None, name=name)
        nets[name] = net
        t = split_table(net)
        row = {"book": name, "FULL": t.loc["FULL", "Sharpe"], "IS": t.loc["IS", "Sharpe"], "OOS": t.loc["OOS", "Sharpe"],
               "t": t.loc["FULL", "t_NW"], "CAGR": st["CAGR"], "Vol": st["Vol"], "MaxDD": st["MaxDD"],
               "turn": st["Turnover_ann"], "gross_avg": st["AvgGross"], "cost_bp": st["CostDrag_bp"],
               "gross_SR": gross.mean() / gross.std() * np.sqrt(ANN)}
        for m in (2, 3):
            n2, *_ = backtest(W, px, cost=cost_frame(idx, mult=m))
            row[f"SR_cost_x{m}"] = perf_stats(n2, ann=ANN)["Sharpe"]
        n1, *_ = backtest(W, px, cost=1.0)
        row["SR_flat1bp"] = perf_stats(n1, ann=ANN)["Sharpe"]
        rows.append(row)
    df = pd.DataFrame(rows).set_index("book")
    pd.set_option("display.width", 250)
    print(df.round(3).to_string())
    df.to_csv(os.path.join(HERE, "03_composite.csv"))
    N = pd.DataFrame(nets)
    print("\nper-year Sharpe:")
    print(N.groupby(N.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(ANN)).round(2).to_string())
    print("\ncorrelations:\n", N.corr().round(2).to_string())
    for name in N:
        bs = block_boot(N[name].loc["2020":].values)
        print(f"{name}: OOS bootstrap mean {bs.mean():.2f}  5-95% [{np.percentile(bs,5):.2f}, {np.percentile(bs,95):.2f}]  P>0 {np.mean(bs>0):.2f}  P>0.5 {np.mean(bs>0.5):.2f}")
    N.to_parquet(os.path.join(HERE, "03_composite_nets.parquet"))
    pd.concat(W_all, axis=1).to_parquet(os.path.join(HERE, "03_composite_weights.parquet"))


if __name__ == "__main__":
    main()
