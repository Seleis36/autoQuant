"""Calibrate the two fixed blend constants on IS (2001-07 -> 2012) only:
  k = vol(intl-relative-trend) / vol(FOMC sleeve at gross 1)  -> equal risk
  L = 0.10 / vol(0.5*A + 0.5*k*B)                             -> 10 % book vol"""
import sys, importlib.util
sys.path.insert(0, "../shared")
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
import data as D, xs
def load_mod(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
A = load_mod("irt", "../intl-relative-trend/strategy.py"); B = load_mod("fomc", "../fomc-global-beta/strategy.py")
C = D.load_panel(A.COUNTRIES + ["SPY"], "Close", start="1998-12-01")
wa = A.target_weights(C); wb = B.target_weights(C).reindex(columns=wa.columns).fillna(0.0)
na, *_ = xs.run(wa.loc["2001":], C.loc["2001":], cost_bps=5.0, spy_cost_bps=1.0)
nb, *_ = xs.run(wb.loc["2001":], C.loc["2001":], cost_bps=5.0, spy_cost_bps=1.0)
IS = slice("2001-07-02", "2012-12-31")
k = na.loc[IS].std() / nb.loc[IS].std()
comb = 0.5 * na + 0.5 * k * nb
L = 0.10 / (comb.loc[IS].std() * np.sqrt(252))
print(f"k = {k:.3f}   L = {L:.3f}")
