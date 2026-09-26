"""cot-positioning -- screen.

Hypotheses (pre-registered before looking at returns):
  H1 crowding reversal: when speculators (legacy non-commercials; TFF leveraged funds) hold
     an extreme net long in a currency relative to its own history, the currency
     underperforms (crowded trades unwind).  weight = -z(net share of OI, 3y window).
  H2 real-money flow continuation: changes in ASSET MANAGER net positioning (TFF) are slow,
     persistent flows; the currency they are building a long in keeps appreciating.
     weight = +z(4-week change of asset-manager net share).
  Controls: H1 on asset managers and H2 on leveraged funds / non-commercials (both signs
  reported) -- the TFF literature finds opposite behaviour of the two groups.

Timing: a report (Tuesday positions, published Friday 19:30/20:30 UTC) is used from the first
=X row whose 00:00 UTC stamp is after Saturday 21:00 UTC -- the Monday row. Rebalance weekly
on that row (the first row of each ISO week), hold one week. Cross-section: the 7 non-USD
currencies, demeaned (USD-neutral) -- `xs`; or each pair against USD on its own signal
-- `bil` (carries USD exposure).
Costs: measured half-spread at the 00:00 UTC print per pair and year (fx_panel.cost_frame).
Samples: =X 2010-2026 daily; H.10 noon rates 2000-2026 weekly for the legacy report.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from fx_panel import CCYS, backtest, load_px, split_table  # noqa: E402
from fetch_cot_fx import fetch_legacy, fetch_tff, net_share, on_fx_rows, report_avail  # noqa: E402
from macro_data import h10_fx  # noqa: E402
from research_lib import perf_stats  # noqa: E402


def zts(x, win=156, minp=52):
    """Own-history z-score on the weekly report grid (3y window)."""
    m = x.rolling(win, min_periods=minp).mean()
    s = x.rolling(win, min_periods=minp).std()
    return (x - m) / s


def xs(sig):
    s = sig[CCYS].sub(sig[CCYS].mean(axis=1), axis=0)
    d = s.abs().sum(axis=1).replace(0, np.nan)
    return s.div(d, axis=0).fillna(0.0)


def bil(sig):
    s = sig[CCYS].clip(-2, 2) / 2.0
    return (s / len(CCYS)).fillna(0.0)


def weekly_hold(W, idx):
    s = pd.Series(idx, index=idx)
    first = s.groupby(idx.to_period("W-SUN")).transform("min").eq(s).values
    return W.reindex(idx)[first].reindex(idx).ffill().fillna(0.0)


def signals():
    lg, tf = fetch_legacy(), fetch_tff()
    lg = lg[lg["date"] >= "1999-01-01"]
    nc = net_share(lg, "nc")
    lev, am, dl = net_share(tf, "lev"), net_share(tf, "am"), net_share(tf, "dealer")
    S = {
        "H1_nc_level": -zts(nc), "H1_lev_level": -zts(lev), "H1c_am_level": -zts(am),
        "H2_am_d4": zts(am.diff(4)), "H2c_lev_d4": zts(lev.diff(4)), "H2c_nc_d4": zts(nc.diff(4)),
        "H2_am_d1": zts(am.diff(1)), "H2c_lev_d1": zts(lev.diff(1)),
        "am_level": zts(am), "dealer_level": zts(dl),
    }
    return S


def avail_all():
    return pd.concat([report_avail(fetch_legacy()), report_avail(fetch_tff())]).groupby(level=0).max()


def main():
    px = load_px()
    idx = px.index
    S = signals()
    AV = avail_all()
    rows = []
    for name, sg in S.items():
        s_rows = on_fx_rows(sg, idx, AV)
        for kind, f in (("xs", xs), ("bil", bil)):
            W = weekly_hold(f(s_rows), idx)
            net, gross, turn, st = backtest(W, px, cost=None, name=f"{name}_{kind}")
            t = split_table(net)
            rows.append({"sig": name, "book": kind, "FULL": t.loc["FULL", "Sharpe"], "IS": t.loc["IS", "Sharpe"],
                         "OOS": t.loc["OOS", "Sharpe"], "gross": gross.mean() / gross.std() * np.sqrt(252),
                         "t": t.loc["FULL", "t_NW"], "turn": st["Turnover_ann"], "cost_bp": st["CostDrag_bp"]})
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print("=X 2010-2026, measured costs")
    print(df.round(2).to_string())
    df.to_csv(os.path.join(HERE, "01_screen_fx.csv"))

    # legacy signals on H.10, weekly, 2000-2026 (1 bp/side)
    h = h10_fx().loc["1999-06-01":].ffill().dropna()
    hidx = h.index
    r = h.pct_change()
    out = []
    for name in ("H1_nc_level", "H2c_nc_d4"):
        for sign in (1, -1):
            s_rows = on_fx_rows(sign * S[name], hidx + pd.Timedelta(hours=17), AV)   # noon NY = 16/17 UTC
            s_rows.index = hidx
            for kind, f in (("xs", xs), ("bil", bil)):
                W = weekly_hold(f(s_rows), hidx)
                net = (W.shift(1) * r[CCYS]).sum(axis=1) - (W.shift(1) - W.shift(2)).abs().sum(axis=1) * 1e-4
                row = {"sig": f"{'+' if sign > 0 else '-'}{name}", "book": kind}
                for per, a, b in (("00-09", "2000", "2009"), ("10-19", "2010", "2019"), ("20-26", "2020", "2026"), ("ALL", "2000", "2026")):
                    row[per] = perf_stats(net.loc[a:b], ann=252)["Sharpe"]
                out.append(row)
    dh = pd.DataFrame(out)
    print("H.10 2000-2026 weekly, legacy non-commercials")
    print(dh.round(2).to_string())
    dh.to_csv(os.path.join(HERE, "01_screen_h10.csv"))


if __name__ == "__main__":
    main()
