"""Calibrate trend-flow-blend on IS data only (2003-03 -> 2012-12).

Sleeves (each from its own strategy.py, unmodified):
  A intl-relative-trend      market-neutral country trend, 10 % vol sleeve
  B fomc-global-beta         long EW country basket over FOMC -1/0
  C global-rebalance-pressure  -clip(Z)/2 on 0.6 SPY + 0.4 EFA over the last 4 sessions
  D intl-rebalance-flow      EFA vs beta*SPY on the last session, sized by the MTD gap
Rules fixed before looking at any blended number:
  1. equal risk: multiplier m_i = 1 / IS daily vol of sleeve i (net, zeros included);
  2. book scalar L so the blended IS vol = 10 %, with sparse-sleeve caps in FINAL book terms:
     m_C = min(L/vol_C, 2/maxgross_C), m_D = min(L/vol_D, 3/maxgross_D) (gross they reach on
     their active sessions); L solved by bisection with the caps applied;
  3. (A and B: m = L/vol, i.e. equal risk);
  4. a deterministic per-session cap: if the combined target gross exceeds 4, scale the whole
     row down to 4 (known at the close, no look-ahead).
Writes constants to calib.json."""
import os, sys, json, importlib.util
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
import data as D

def _load(name, rel):
    s = importlib.util.spec_from_file_location(name, os.path.join(_HERE, rel)); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
IRT = _load("irt_s", "../intl-relative-trend/strategy.py")
FOMC = _load("fomc_s", "../fomc-global-beta/strategy.py")
GRP = _load("grp_s", "../global-rebalance-pressure/strategy.py")
IRF = _load("irf_s", "../intl-rebalance-flow/strategy.py")
COUNTRIES = IRT.COUNTRIES
COLS = COUNTRIES + ["SPY", "EFA"]
COST = pd.Series({**{c: 5.0 for c in COUNTRIES}, "SPY": 1.0, "EFA": 2.0})
IS = ("2003-03-01", "2012-12-31")

def sleeves(close):
    W = {"A": IRT.target_weights(close[COUNTRIES + ["SPY"]]),
         "B": FOMC.target_weights(close[COUNTRIES + ["SPY"]]),
         "C": GRP.target_weights(close[["SPY", "EFA", "IEF"]]),
         "D": IRF.target_weights(close[["EFA", "SPY"]])}
    return {k: w.reindex(columns=COLS).fillna(0.0) for k, w in W.items()}

def run(W, close, cost_mult=1.0, lag=0):
    ret = close[COLS].pct_change().fillna(0.0)
    We = W.shift(1 + lag).fillna(0.0)
    dW = (We - We.shift(1).fillna(0.0)).abs()
    net = (We * ret).sum(axis=1) - (dW * COST * cost_mult / 1e4).sum(axis=1)
    return net, dW.sum(axis=1), We

if __name__ == "__main__":
    close = D.load_panel(COLS + ["IEF"], "Close", start="1998-12-01")
    W = sleeves(close)
    vol, mg, sr = {}, {}, {}
    for k, w in W.items():
        n, _, We = run(w, close)
        n = n.loc[IS[0]:IS[1]]
        vol[k] = n.std() * np.sqrt(252); sr[k] = n.mean() / n.std() * np.sqrt(252)
        mg[k] = We.abs().sum(axis=1).loc[IS[0]:IS[1]].max()
    caps = {"C": 2.0, "D": 3.0}
    def mults(L):
        return {k: (min(L / vol[k], caps[k] / mg[k]) if k in caps else L / vol[k]) for k in W}
    def book_vol(L):
        n, _, _ = run(sum(mults(L)[k] * W[k] for k in W), close)
        return n.loc[IS[0]:IS[1]].std() * np.sqrt(252)
    lo, hi = 0.01, 1.0
    for _ in range(40):                       # bisection: IS book vol = 10 %
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if book_vol(mid) < 0.10 else (lo, mid)
    L = 0.5 * (lo + hi)
    mult = {k: float(v) for k, v in mults(L).items()}
    capped = {k: (round(L / vol[k], 3), round(caps[k] / mg[k], 3)) for k in caps if L / vol[k] > caps[k] / mg[k]}
    print("IS sleeve vol:", {k: round(v, 4) for k, v in vol.items()}, "\nIS sleeve SR:", {k: round(v, 2) for k, v in sr.items()},
          "\nIS max gross:", {k: round(v, 2) for k, v in mg.items()}, "\ncaps binding (uncapped, capped m):", capped,
          "\nL =", round(L, 3), "\nfinal multipliers:", {k: round(v, 3) for k, v in mult.items()})
    json.dump({"multipliers": mult, "gross_cap": 4.0, "is_window": IS, "is_vol": vol, "is_sr": sr, "is_maxgross": mg},
              open(os.path.join(_HERE, "calib.json"), "w"), indent=1, default=float)
