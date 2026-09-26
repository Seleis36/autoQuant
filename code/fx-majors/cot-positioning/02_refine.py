"""cot-positioning -- refinement and controls for the contrarian-positioning finding.

01: fading speculative positioning works in both forms -- the level (crowding, -z of net
share of OI vs own 3y history) and the 4-week change (flow). Continuation hypotheses fail.

Pre-registered here, before running:
  * Composite CP = mean of the two legacy non-commercial legs: -z(level) and -z(4w change).
    The legacy report exists since 1986, so CP can be checked on H.10 2000-2026.
  * Price-reversal control: speculators chase trends, so the 4-week change in positions
    is correlated with the 4-week price move. Test the matching price-reversal signal
    (-z of the Tuesday-to-Tuesday 4-week FX return, same weekly grid and z-window) and the
    positioning signal RESIDUALISED on it (cross-sectional regression each week).
  * Delay test: use every report one extra week late. A real slow-moving positioning
    effect should survive; a timing artefact should not.
  * Neighbourhood: z-window 52/104/156/260 weeks, change horizon 2/4/8/13 weeks,
    hold 1 week vs 4 overlapping weekly tranches.
Costs: measured half-spread at 00:00 UTC (fx_panel.cost_frame).
"""
import os
import sys
import importlib

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, HERE)
from fx_panel import CCYS, backtest, load_px, split_table, usd_per_ccy  # noqa: E402
from fetch_cot_fx import fetch_legacy, fetch_tff, net_share, on_fx_rows  # noqa: E402
from macro_data import h10_fx  # noqa: E402
from research_lib import perf_stats  # noqa: E402
s01 = importlib.import_module("01_screen")


def zts(x, win=156, minp=52):
    return (x - x.rolling(win, min_periods=minp).mean()) / x.rolling(win, min_periods=minp).std()


def price_on_report_grid(fx_usd_per, report_dates):
    """USD-per-ccy price at each report Tuesday's close (last quote on or before Tue 23:59 UTC).
    Uses the H.10/=X frame passed in; only used to build the control signal."""
    p = fx_usd_per.reindex(fx_usd_per.index.union(report_dates)).ffill().reindex(report_dates)
    return p


def resid_xs(y, x):
    """Per-row cross-sectional OLS residual of y on x (both demeaned)."""
    yd = y.sub(y.mean(axis=1), axis=0)
    xd = x.sub(x.mean(axis=1), axis=0)
    b = (yd * xd).sum(axis=1) / (xd * xd).sum(axis=1)
    return yd - xd.mul(b, axis=0)


def tranche_hold(Wrows, idx, n):
    """Average of n weekly books started on consecutive weeks (overlapping holds)."""
    s = pd.Series(idx, index=idx)
    first = s.groupby(idx.to_period("W-SUN")).transform("min").eq(s).values
    W = Wrows.reindex(idx)[first]
    W = sum(W.shift(k) for k in range(n)) / n
    return W.reindex(idx).ffill().fillna(0.0)


def build(lg_w, avail, fx_for_ctrl, win=156, dh=4, delay=0):
    """Weekly (report-grid) signals indexed by avail_utc."""
    nc = lg_w
    lvl = -zts(nc, win)
    chg = -zts(nc.diff(dh), win)
    cp = (lvl + chg) / 2
    # price control on the same grid: report Tuesday prices (H.10 noon, not the traded print)
    pr = price_on_report_grid(fx_for_ctrl, nc.index)
    prc = -zts(np.log(pr / pr.shift(dh)), win)
    out = {"CP": cp, "level": lvl, "chg": chg, "price_rev": prc,
           "CP_resid": resid_xs(cp[CCYS], prc[CCYS]), "chg_resid": resid_xs(chg[CCYS], prc[CCYS])}
    if delay:
        out = {k: v.shift(delay) for k, v in out.items()}
    return out


def main():
    lg = fetch_legacy()
    lg = lg[lg["date"] >= "1995-01-01"]
    nc = net_share(lg, "nc")[CCYS]
    px = load_px()
    idx = px.index
    usd = usd_per_ccy(px)
    h10 = h10_fx().ffill()
    # control prices: H.10 noon (independent of the traded =X print), Tuesday noon NY
    rows = []

    def run(tag, sig, hold_n=1, book="xs"):
        s_rows = on_fx_rows(sig, idx, AV)
        f = s01.xs if book == "xs" else s01.bil
        W = tranche_hold(f(s_rows), idx, hold_n)
        net, gross, turn, st = backtest(W, px, cost=None, name=tag)
        t = split_table(net)
        rows.append({"tag": tag, "FULL": t.loc["FULL", "Sharpe"], "IS": t.loc["IS", "Sharpe"],
                     "OOS": t.loc["OOS", "Sharpe"], "t": t.loc["FULL", "t_NW"], "CAGR": t.loc["FULL", "CAGR"],
                     "Vol": t.loc["FULL", "Vol"], "MaxDD": t.loc["FULL", "MaxDD"], "turn": st["Turnover_ann"],
                     "cost_bp": st["CostDrag_bp"]})
        return net

    AV = s01.avail_all()
    base = build(nc, nc, h10)
    nets = {}
    for k, v in base.items():
        nets[k] = run(f"base:{k}", v)
    for k in ("CP", "chg", "level"):
        run(f"delay1w:{k}", build(nc, nc, h10, delay=1)[k])
        run(f"delay2w:{k}", build(nc, nc, h10, delay=2)[k])
    for win in (52, 104, 260):
        run(f"win{win}:CP", build(nc, nc, h10, win=win)["CP"])
    for dh in (2, 8, 13):
        b = build(nc, nc, h10, dh=dh)
        run(f"dh{dh}:CP", b["CP"]); run(f"dh{dh}:chg", b["chg"])
    for n in (2, 4):
        run(f"tranche{n}:CP", base["CP"], hold_n=n)
    run("bil:CP", base["CP"], book="bil")
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print(df.round(2).to_string())
    df.to_csv(os.path.join(HERE, "02_refine_fx.csv"))
    c = pd.DataFrame(nets).corr().round(2)
    print("daily net-return correlations:\n", c.to_string())

    # ---- H.10 2000-2026 (weekly, 1 bp), CP and components, with price control
    hidx = h10.loc["1999-06-01":].dropna().index
    r = h10.loc[hidx].pct_change()
    out = []
    for k, v in base.items():
        s_rows = on_fx_rows(v, hidx + pd.Timedelta(hours=17), AV)
        s_rows.index = hidx
        W = tranche_hold(s01.xs(s_rows), hidx, 1)
        net = (W.shift(1) * r[CCYS]).sum(axis=1) - (W.shift(1) - W.shift(2)).abs().sum(axis=1) * 1e-4
        row = {"sig": k}
        for per, a, b in (("00-09", "2000", "2009"), ("10-19", "2010", "2019"), ("20-26", "2020", "2026"), ("ALL", "2000", "2026")):
            row[per] = perf_stats(net.loc[a:b], ann=252)["Sharpe"]
        out.append(row)
    dh_ = pd.DataFrame(out)
    print("H.10 weekly 2000-2026 (1 bp):")
    print(dh_.round(2).to_string())
    dh_.to_csv(os.path.join(HERE, "02_refine_h10.csv"))


if __name__ == "__main__":
    main()
