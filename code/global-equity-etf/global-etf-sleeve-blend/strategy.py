"""global-etf-sleeve-blend -- intl-relative-trend + fomc-global-beta at equal risk.

  w_t = A_WEIGHT * intl_relative_trend.target_weights(close)      (market-neutral, 10 % vol sleeve)
      + B_WEIGHT * fomc_global_beta.target_weights(close)         (long EW country basket, FOMC -1/0)

A_WEIGHT = L * 0.5 and B_WEIGHT = L * 0.5 * k, with k = 1.29 (IS vol ratio A/B -> equal risk) and
L = 1.342 (IS scalar to a 10 % book vol). Both constants were fixed on 2001-07 -> 2012 data only.
The two sleeves are uncorrelated (daily corr -0.06).

`target_weights(close)` -> daily weights for the 9 country ETFs + SPY, known at the close of t.
"""
import os, importlib.util
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


IRT = _load("intl_relative_trend_strategy", "../intl-relative-trend/strategy.py")
FOMC = _load("fomc_global_beta_strategy", "../fomc-global-beta/strategy.py")
COLUMNS = IRT.COUNTRIES + [IRT.BENCH]
A_WEIGHT = 0.67
B_WEIGHT = 0.87


def target_weights(close, a_weight=A_WEIGHT, b_weight=B_WEIGHT):
    wa = IRT.target_weights(close)
    wb = FOMC.target_weights(close).reindex(columns=COLUMNS).fillna(0.0)
    return (a_weight * wa + b_weight * wb)[COLUMNS]
