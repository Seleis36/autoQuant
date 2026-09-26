"""policy-rate-momentum -- screen.

Hypothesis (Dahlquist & Hasseltoft 2020 "economic momentum"; Brooks 2017 "macro
momentum"): policy cycles are persistent and FX under-reacts to them, so the currencies
whose central bank has been tightening relative to the others keep appreciating. The
observable, never-revised summary of a policy cycle is the change in the policy rate.

Universe: 8 currencies (USD + the 7 =X pairs). Signal at each month-end row = change of
the policy rate over k months (BIS, lagged one day). Book = demeaned signal across the
8 currencies (dollar-neutral across the G8; USD leg is implied), sum|w| = 1, held one
month, then scaled to a 5 % ex-ante vol with the book's own trailing vol sampled at the
rebalance. Spot-only P&L (the sim book accrues no carry); carry reported separately.

Pre-registered primary: k = 12, linear XS. Variants listed in VARIANTS, all reported.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from fx_panel import (CCYS, backtest, carry_return, hold_monthly, lag_to_fx, load_px,  # noqa: E402
                      month_end_rows, split_table, usd_per_ccy, ANN)
from macro_data import short_rates  # noqa: E402

G8 = ["USD"] + CCYS


def xs_linear(sig8):
    s = sig8.sub(sig8.mean(axis=1), axis=0)
    d = s.abs().sum(axis=1).replace(0, np.nan)
    return s.div(d, axis=0).fillna(0.0)[CCYS]


def xs_rank(sig8):
    r = sig8.rank(axis=1)
    s = r.sub(r.mean(axis=1), axis=0)
    d = s.abs().sum(axis=1).replace(0, np.nan)
    return s.div(d, axis=0).fillna(0.0)[CCYS]


def bilateral(sig8):
    """Each pair on its own: long ccy if its signal beats USD's, equal gross per pair."""
    d = sig8[CCYS].sub(sig8["USD"], axis=0)
    return np.sign(d) / len(CCYS)


def monthly_vol_target(Wm, px, target=0.05, halflife=126, cap=4.0):
    """Wm: month-held unit book. Scale factor from trailing daily vol of the unit book,
    sampled at month-end rows only (so the scale does not create daily turnover)."""
    _, g, _, _ = backtest(Wm, px, cost=0.0)
    v = g.ewm(halflife=halflife, min_periods=60).std() * np.sqrt(ANN)
    k = (target / v).clip(upper=cap)
    k = hold_monthly(k, px.index)
    return Wm.mul(k, axis=0)


def rate_signal(rates, idx, months):
    lag_days = int(round(months * 30.4375))
    r = rates[G8]
    past = r.shift(lag_days)                       # calendar-day index
    return lag_to_fx(r - past, idx, lag=1)


def main():
    px = load_px()
    idx = px.index
    rates = short_rates()
    carry = carry_return(rates, idx)
    rows, tabs, nets = [], [], {}

    def run(name, Wunit, cost=1.0):
        W = monthly_vol_target(hold_monthly(Wunit, idx).reindex(idx), px)
        # hold_monthly on each column
        net, gross, turn, st = backtest(W, px, cost=cost, name=name, carry=carry)
        nets[name] = net
        st["Sharpe_gross"] = perf(gross)
        rows.append(st)
        tabs.append(split_table(net, name))

    def perf(x):
        return x.mean() / x.std() * np.sqrt(ANN)

    for k in (3, 6, 12, 24):
        sig = rate_signal(rates, idx, k)
        run(f"dpol{k}_lin", xs_linear(sig))
        run(f"dpol{k}_rank", xs_rank(sig))
        run(f"dpol{k}_bilat", bilateral(sig))
    # level (carry) as a reference point
    lvl = lag_to_fx(rates[G8], idx, lag=1)
    run("carry_lin", xs_linear(lvl))
    run("carry_rank", xs_rank(lvl))

    st = pd.DataFrame(rows)
    cols = ["Sharpe", "Sharpe_gross", "Sharpe_w_carry", "Carry_ann", "CAGR", "Vol", "MaxDD", "t_NW",
            "Turnover_ann", "AvgGross", "CostDrag_bp"]
    pd.set_option("display.width", 200)
    print(st[cols].round(2).to_string())
    print(pd.concat(tabs).round(2).to_string())
    st.to_csv(os.path.join(HERE, "01_screen.csv"))
    pd.DataFrame(nets).to_parquet(os.path.join(HERE, "01_screen_nets.parquet"))


if __name__ == "__main__":
    main()
