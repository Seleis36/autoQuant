"""fx-sleeve-blend -- the four sleeve definitions, each in CURRENCY space (EUR..NZD,
positive = long ccy / short USD), unit-gross, at its own rebalance frequency.

Inclusion rule (declared before the blend was run): every sleeve found this session whose
PRE-SPECIFIED composite form is positive net on both =X 2010-2026 and H.10 -- not its
best cell.
  COT  cot-positioning book C (strategy.target_weights, already vol-targeted to 5 %)
  EQM  equity momentum, lookback composite z(1/3/6/12m local-index return), G8 demeaned,
       weekly  (equity-flow-rebalance 02, px source, skip 0: 0.39 =X, 0.36 H.10)
  TOTB commodity-bloc ToT gap, mean of the 6m and 12m gap signals, AUD/CAD/NZD demeaned,
       monthly (terms-of-trade-fx 02/03: 6m 0.60 / 12m 0.21-0.45 =X; 0.30-0.38 H.10)
  RDL  rate-differential composite z(dd 5/20/60d, 2y+5y), EUR/GBP/JPY/CAD vs USD, weekly
       (rate-diff-lag 02 COMP_bil: 0.36 =X, 0.24 H.10)
Each function takes the =X close frame and returns a DataFrame on its index.
"""
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
FX = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(FX, "shared"))
from fx_panel import CCYS, TICKER, lag_to_fx, usd_per_ccy  # noqa: E402


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def _tocc(Wt):
    return pd.DataFrame({c: TICKER[c][1] * Wt[TICKER[c][0]] for c in CCYS})


def cot(px):
    st = _load(os.path.join(FX, "cot-positioning", "strategy.py"), "cot_strategy")
    _, lg, tf = st.load_inputs()
    return _tocc(st.target_weights(px, lg, tf)).reindex(px.index).fillna(0.0)


def eqm(px):
    e1 = _load(os.path.join(FX, "equity-flow-rebalance", "01_screen.py"), "efr01")
    sys.modules["01_screen"] = e1
    e2 = _load(os.path.join(FX, "equity-flow-rebalance", "02_refine.py"), "efr02")
    eq = e1.equity_local("px", usd_per_ccy(px))
    eqL = lag_to_fx(eq, px.index, lag=1)
    return e2.hold(e1.xs_linear(e2.composite(eqL, 0)), px.index, "W")


def totb(px):
    t1 = _load(os.path.join(FX, "terms-of-trade-fx", "01_screen.py"), "tot01")
    sys.modules["01_screen"] = t1
    b = _load(os.path.join(FX, "terms-of-trade-fx", "02_bloc.py"), "tot02")
    cmd = t1.load_cmd()
    fxl = np.log(usd_per_ccy(px))
    idx = px.index
    sig = 0
    for k in (6, 12):
        d = lag_to_fx(t1.tot_change(cmd, 21 * k), idx, lag=1)
        sig = sig + (b.zb(d) - b.zb(fxl - fxl.shift(21 * k))) / 2
    return b.hold(b.bloc_book(sig), idx, "M")


def rdl(px):
    r1 = _load(os.path.join(FX, "rate-diff-lag", "01_screen.py"), "rdl01")
    sys.modules["01_screen"] = r1
    r2 = _load(os.path.join(FX, "rate-diff-lag", "02_regime.py"), "rdl02")
    from fetch_yields import yields
    y = yields()
    idx = px.index
    d2 = lag_to_fx(r1.diffs(y, 2), idx, lag=1)
    d5 = lag_to_fx(r1.diffs(y, 5), idx, lag=1)
    return r1.hold(r1.bil(r2.composite(d2, d5)), idx, "W")


SLEEVES = {"COT": cot, "EQM": eqm, "TOTB": totb, "RDL": rdl}
