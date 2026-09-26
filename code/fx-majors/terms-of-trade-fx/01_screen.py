"""terms-of-trade-fx -- screen.

Hypothesis (Chen & Rogoff 2003 "commodity currencies"; Macrosynergy "terms of trade as
trading signals"): commodity export prices move the terms of trade of AUD, CAD and NZD and,
with a lag, their currencies -- investors under-react to slow terms-of-trade trends, and
energy importers (JPY, EUR) are hurt by oil. Two pre-registered forms:
  MOM  -- the k-month change of each currency's commodity terms-of-trade index predicts its
          next-month return (k = 3, 6, 12);
  GAP  -- fair-value gap: currencies whose ToT rose more than they appreciated over 12
          months (z(dToT) - z(dFX), cross-sectional) catch up.

ToT index = fixed export(+)/import(-) weights on log commodity prices, set from broad
trade-share knowledge BEFORE running (never tuned):
  AUD: iron ore .40 (TIO=F, from 2010-10; before: renormalised without it), gold .15,
       crude .15 (LNG is oil-indexed), copper .10, wheat .10, cattle .10
  CAD: crude .60, natgas .10, gold .10, wheat .10, copper .05, cattle .05
  NZD: dairy .60 (DC=F), cattle .25, wheat .15   (NZ: dairy/meat exporter)
  JPY: crude -1.0         EUR: crude -0.5          USD, GBP, CHF: 0
Commodity closes (US session) stamped <= D-1 for the weight at =X row D. Monthly rebalance,
G8 cross-section demeaned (linear) or each pair vs USD (bil). Samples: =X 2010-26 (daily,
measured costs) and H.10 2000-26 (monthly, 1 bp).
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from fx_panel import CCYS, backtest, hold_monthly, lag_to_fx, load_px, split_table, usd_per_ccy  # noqa: E402
from macro_data import h10_fx  # noqa: E402
from research_lib import perf_stats  # noqa: E402

DATA = os.path.abspath(os.path.join(HERE, "..", "..", "..", "data"))
G8 = ["USD"] + CCYS
WEIGHTS = {
    "AUD": {"TIO=F": .40, "GC=F": .15, "CL=F": .15, "HG=F": .10, "ZW=F": .10, "LE=F": .10},
    "CAD": {"CL=F": .60, "NG=F": .10, "GC=F": .10, "ZW=F": .10, "HG=F": .05, "LE=F": .05},
    "NZD": {"DC=F": .60, "LE=F": .25, "ZW=F": .15},
    "JPY": {"CL=F": -1.0},
    "EUR": {"CL=F": -0.5},
}


def load_cmd():
    out = {}
    for t in sorted({k for w in WEIGHTS.values() for k in w}):
        parts = [pd.read_parquet(os.path.join(DATA, f"{t}{s}.parquet"))["Close"]
                 for s in ("_d_pre2010", "_d") if os.path.exists(os.path.join(DATA, f"{t}{s}.parquet"))]
        s = pd.concat(parts).sort_index()
        s.index = pd.to_datetime(s.index)
        out[t] = s[~s.index.duplicated(keep="last")]
    c = pd.DataFrame(out).ffill()
    return c.where(c > 0)          # WTI printed negative in Apr-2020


def tot_change(cmd, k_days):
    """Weighted k-day log change per currency; weights renormalised over available series."""
    lr = np.log(cmd).diff(k_days)
    out = pd.DataFrame(0.0, index=cmd.index, columns=G8)
    for c, w in WEIGHTS.items():
        num = sum(lr[t].fillna(0) * v for t, v in w.items())
        den = sum(lr[t].notna() * abs(v) for t, v in w.items())
        tot = sum(abs(v) for v in w.values())
        out[c] = num / den.replace(0, np.nan) * tot
    return out


def xs_lin(sig8):
    s = sig8.sub(sig8.mean(axis=1), axis=0)
    return s.div(s.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)[CCYS]


def bil(sig8):
    d = sig8[CCYS].sub(sig8["USD"], axis=0)
    z = d / d.abs().rolling(756, min_periods=250).mean()
    return (z.clip(-2, 2) / 2 / len(CCYS)).fillna(0.0)


def zxs(x):
    return x.sub(x.mean(axis=1), axis=0).div(x.std(axis=1), axis=0)


def main():
    cmd = load_cmd()
    rows = []
    # ---- =X daily 2010-2026
    px = load_px()
    idx = px.index
    usd = usd_per_ccy(px)
    fxl = np.log(usd)
    for k in (3, 6, 12):
        d = lag_to_fx(tot_change(cmd, 21 * k), idx, lag=1)
        for kind, f in (("xs", xs_lin), ("bil", bil)):
            W = hold_monthly(f(d), idx)
            net, gross, turn, st = backtest(W, px, cost=None)
            t = split_table(net)
            rows.append({"data": "=X", "sig": f"MOM{k}", "book": kind, "FULL": t.loc["FULL", "Sharpe"],
                         "IS": t.loc["IS", "Sharpe"], "OOS": t.loc["OOS", "Sharpe"], "t": t.loc["FULL", "t_NW"],
                         "turn": st["Turnover_ann"]})
    d12 = lag_to_fx(tot_change(cmd, 252), idx, lag=1)
    dfx = (fxl - fxl.shift(252)).assign(USD=0.0)[G8]
    gap = zxs(d12) - zxs(dfx)
    for kind, f in (("xs", xs_lin), ("bil", bil)):
        W = hold_monthly(f(gap), idx)
        net, gross, turn, st = backtest(W, px, cost=None)
        t = split_table(net)
        rows.append({"data": "=X", "sig": "GAP12", "book": kind, "FULL": t.loc["FULL", "Sharpe"],
                     "IS": t.loc["IS", "Sharpe"], "OOS": t.loc["OOS", "Sharpe"], "t": t.loc["FULL", "t_NW"],
                     "turn": st["Turnover_ann"]})
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(df.round(2).to_string())

    # ---- H.10 2000-2026 monthly
    h = h10_fx().loc["1999-01-01":].ffill().dropna()
    me = h.resample("ME").last()
    r = me.pct_change()
    cm = cmd.reindex(cmd.index.union(me.index)).ffill().reindex(me.index)
    out = []
    for k in (3, 6, 12):
        d = tot_change(cm, k)
        for kind, f in (("xs", xs_lin), ("bil", None)):
            if f is None:
                dd = d[CCYS].sub(d["USD"], axis=0)
                W = (np.sign(dd) / len(CCYS)).where(dd.abs() > 0, 0.0)
            else:
                W = f(d)
            net = (W.shift(1) * r[CCYS]).sum(axis=1) - (W.shift(1) - W.shift(2)).abs().sum(axis=1) * 1e-4
            row = {"sig": f"MOM{k}", "book": kind}
            for per, a, b in (("00-09", "2000", "2009"), ("10-19", "2010", "2019"), ("20-26", "2020", "2026"), ("ALL", "2000", "2026")):
                row[per] = perf_stats(net.loc[a:b], ann=12)["Sharpe"]
            out.append(row)
    fxm = np.log(me)
    gapm = zxs(tot_change(cm, 12)) - zxs((fxm - fxm.shift(12)).assign(USD=0.0)[G8])
    W = xs_lin(gapm)
    net = (W.shift(1) * r[CCYS]).sum(axis=1) - (W.shift(1) - W.shift(2)).abs().sum(axis=1) * 1e-4
    row = {"sig": "GAP12", "book": "xs"}
    for per, a, b in (("00-09", "2000", "2009"), ("10-19", "2010", "2019"), ("20-26", "2020", "2026"), ("ALL", "2000", "2026")):
        row[per] = perf_stats(net.loc[a:b], ann=12)["Sharpe"]
    out.append(row)
    dh = pd.DataFrame(out)
    print("H.10 monthly 2000-2026:")
    print(dh.round(2).to_string())
    df.to_csv(os.path.join(HERE, "01_screen_fx.csv"))
    dh.to_csv(os.path.join(HERE, "01_screen_h10.csv"))


if __name__ == "__main__":
    main()
