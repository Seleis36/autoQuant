"""equity-flow-rebalance -- screen.

Hypothesis (Hau & Rey 2006 RFS; Camanho, Hau & Rey 2022 RFS "Global portfolio rebalancing
and exchange rates"): global investors rebalance toward target weights. When a foreign
equity market outperforms (in local currency), foreign holders are overweight it and sell,
and repatriating the proceeds depreciates that currency -- slowly, over months, because
institutional rebalancing is sluggish. Predicted sign: past relative LOCAL-currency equity
outperformance -> FUTURE depreciation. The opposite sign (equity momentum -> currency
appreciation, Brooks 2017 macro momentum) is the rival hypothesis; both are reported.

Local equity return, two sources (both reported):
  px  -- local price/performance indices (^GSPC ^GDAXI ^FTSE ^N225 ^AXJO ^GSPTSE ^SSMI ^NZ50)
  tr  -- US-listed country ETFs (SPY EWG EWU EWJ EWA EWC EWL ENZL), total return with
         dividends, converted to local currency by removing the FX move.
Monthly rebalance on the last row of each month; signal uses data stamped <= that date.
Long sample: Fed H.10 noon rates 1999-2026 (monthly). Short sample: =X daily 2010-2026 with
measured costs. Pre-registered primary: Hau-Rey sign, 3-month lookback, linear G8 XS, tr.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from fx_panel import CCYS, ANN, backtest, hold_monthly, lag_to_fx, load_px, split_table, usd_per_ccy  # noqa: E402
from macro_data import h10_fx  # noqa: E402
from research_lib import perf_stats  # noqa: E402

G8 = ["USD"] + CCYS
IDX = {"USD": "^GSPC", "EUR": "^GDAXI", "GBP": "^FTSE", "JPY": "^N225", "AUD": "^AXJO",
       "CAD": "^GSPTSE", "CHF": "^SSMI", "NZD": "^NZ50"}
ETF = {"USD": "SPY", "EUR": "EWG", "GBP": "EWU", "JPY": "EWJ", "AUD": "EWA", "CAD": "EWC",
       "CHF": "EWL", "NZD": "ENZL"}
DATA = os.path.abspath(os.path.join(HERE, "..", "..", "..", "data"))


def _load(t):
    base = t.replace("^", "IDX_")
    parts = []
    for suf in ("_d_pre2010", "_d"):
        f = os.path.join(DATA, f"{base}{suf}.parquet")
        if os.path.exists(f):
            parts.append(pd.read_parquet(f)["Close"])
    s = pd.concat(parts).sort_index()
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")]


def equity_local(kind, fx_usd_per):
    """Daily local-currency equity level per currency (calendar-aligned, ffilled)."""
    if kind == "px":
        e = pd.DataFrame({c: _load(t) for c, t in IDX.items()})
    else:
        e = pd.DataFrame({c: _load(t) for c, t in ETF.items()})
        f = fx_usd_per.reindex(e.index.union(fx_usd_per.index)).ffill().reindex(e.index)
        f["USD"] = 1.0
        e = e / f[G8]                                   # USD price / (USD per ccy) = local
        # ENZL starts 2010-09: NZD simply sits out of the tr cross-section before that
    return e.sort_index().ffill()


def xs_linear(sig8):
    s = sig8.sub(sig8.mean(axis=1), axis=0)
    d = s.abs().sum(axis=1).replace(0, np.nan)
    return s.div(d, axis=0).fillna(0.0)[CCYS]


def signal_monthly(eq, me, k):
    m = eq.reindex(eq.index.union(me)).ffill().reindex(me)
    return np.log(m / m.shift(k))


def monthly_returns(fx_m, W):
    r = fx_m.pct_change()
    g = (W.shift(1) * r).sum(axis=1)
    turn = (W.shift(1) - W.shift(2)).abs().sum(axis=1)
    return (g - turn * 1e-4).iloc[1:]


def main():
    h10 = h10_fx().loc["1999-01-01":].ffill().dropna()
    fx_m = h10.resample("ME").last()
    me = fx_m.index
    out = []
    for kind in ("tr", "px"):
        eq = equity_local(kind, h10)
        for k in (1, 3, 6, 12):
            s = signal_monthly(eq, me, k)
            for sign, lab in ((-1, "HR"), (1, "MOM")):
                W = xs_linear(sign * s.dropna(axis=1, how="all"))
                W = W.reindex(columns=CCYS).fillna(0.0)
                net = monthly_returns(fx_m, W)
                net = net[net.index >= "2000-01-01"]
                row = {"src": kind, "k": k, "sign": lab}
                for per, a, b in (("1999-2009", "2000", "2009"), ("2010-2019", "2010", "2019"),
                                  ("2020-2026", "2020", "2026"), ("ALL", "2000", "2026")):
                    row[per] = perf_stats(net.loc[a:b], ann=12)["Sharpe"]
                out.append(row)
    df = pd.DataFrame(out)
    pd.set_option("display.width", 200)
    print("H.10 monthly, Sharpe (1 bp/side), spot only")
    print(df.round(2).to_string())
    df.to_csv(os.path.join(HERE, "01_screen_h10.csv"))

    # daily =X, measured cost, 2010-2026
    px = load_px()
    usd = usd_per_ccy(px)
    tabs = []
    for kind in ("tr", "px"):
        eq = equity_local(kind, usd)
        eqL = lag_to_fx(eq, px.index, lag=1)              # stamped <= D-1
        for k in (1, 3, 6, 12):
            s = np.log(eqL / eqL.shift(int(21 * k)))
            for sign, lab in ((-1, "HR"), (1, "MOM")):
                W = hold_monthly(xs_linear(sign * s), px.index)
                net, gross, turn, st = backtest(W, px, cost=1.0, name=f"{kind}_{k}_{lab}")
                t = split_table(net, f"{kind}_k{k}_{lab}")
                t["Turn"] = st["Turnover_ann"]
                tabs.append(t)
    print(pd.concat(tabs).round(2).to_string())


if __name__ == "__main__":
    main()
