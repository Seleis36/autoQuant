"""trend-flow-blend -- four uncorrelated country-ETF sleeves at (capped) equal risk.

  w_t = 0.490 * intl_relative_trend.target_weights      (slow US-vs-ex-US trend, market-neutral)
      + 0.605 * fomc_global_beta.target_weights         (long EW country basket, FOMC -1/0)
      + 0.861 * global_rebalance_pressure.target_weights (stock/bond month-end pressure, last 4 sessions)
      + 0.672 * intl_rebalance_flow.target_weights      (US-vs-EFA month-end pressure, last session)
then, per session, if sum|w| > GROSS_CAP (4.0) the whole row is scaled down to 4.0.

Multipliers fixed on 2003-03 -> 2012 data only (`01_calibrate.py`, `calib.json`): equal risk
(1 / IS vol) with the one-session sleeve capped at gross 3 on its active day, and the book
scaled to 10 % IS vol. Sleeve code is imported unmodified from the four sibling folders.

`target_weights(close)` -> daily target weights (fraction of equity) for the 9 country ETFs,
SPY and EFA, known at the close of t, applied to t+1's return. `close` must also contain IEF
(signal only, never traded).
"""
import os
import importlib.util
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


IRT = _load("tfb_intl_relative_trend", "../intl-relative-trend/strategy.py")
FOMC = _load("tfb_fomc_global_beta", "../fomc-global-beta/strategy.py")
GRP = _load("tfb_global_rebalance_pressure", "../global-rebalance-pressure/strategy.py")
IRF = _load("tfb_intl_rebalance_flow", "../intl-rebalance-flow/strategy.py")

COUNTRIES = IRT.COUNTRIES
COLUMNS = COUNTRIES + ["SPY", "EFA"]
SIGNAL_ONLY = ["IEF"]
MULT = {"trend": 0.490, "fomc": 0.605, "rebalance": 0.861, "intl_flow": 0.672}
GROSS_CAP = 4.0


def sleeve_weights(close):
    base = COUNTRIES + ["SPY"]
    return {"trend": IRT.target_weights(close[base]),
            "fomc": FOMC.target_weights(close[base]),
            "rebalance": GRP.target_weights(close[["SPY", "EFA", "IEF"]]),
            "intl_flow": IRF.target_weights(close[["EFA", "SPY"]])}


def target_weights(close, mult=MULT, gross_cap=GROSS_CAP):
    close = close.sort_index()
    W = sleeve_weights(close)
    w = sum(mult[k] * W[k].reindex(index=close.index, columns=COLUMNS).fillna(0.0) for k in W)
    g = w.abs().sum(axis=1)
    scale = (gross_cap / g).where(g > gross_cap, 1.0)
    return w.mul(scale, axis=0)[COLUMNS]
