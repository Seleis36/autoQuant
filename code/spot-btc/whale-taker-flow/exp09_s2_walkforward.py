"""S2 (coinbase-premium AND whale confirmation): selection-adjusted evidence.

1. Walk-forward over the 15-cell S2 neighbourhood (whale window 12/24/48/72/168 h x exit
   -1/-1.5/-2) PLUS the unfiltered coinbase-premium as a 16th candidate, re-selected every
   January on expanding IS from 2018; concatenated 2020-2026 out-of-sample.
2. vectorbt from_orders cross-check with the correct timing (order at close t = weight w_t).
3. Daily P&L correlation S2 vs coinbase-premium; drawdown episodes compared.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_hourly  # noqa: E402
from exp01_screen import FLOW  # noqa: E402
from exp05_hourly_state import HPY, IS, OOS, hysteresis, stats  # noqa: E402
from exp06_blend import load_cbp  # noqa: E402
from exp08_validate import groups, sh, whale_z  # noqa: E402


def main():
    h = btc_hourly().loc[:OOS[1]]
    close = h.Close
    raw = pd.read_parquet(FLOW).reindex(close.index)
    fl = groups(raw, [3, 4], [0])
    r = close.pct_change()
    ewv = r.ewm(halflife=480, min_periods=480).std() * np.sqrt(HPY)
    vs = (0.40 / ewv).clip(0, 1).fillna(0)
    trend = (close > close.rolling(1200).mean()).astype(float)
    cbp = load_cbp()
    cbc = pd.read_parquet(os.path.join(REPO, "data", "COINBASE_BTCUSD_1h.parquet"))["Close"].reindex(close.index).ffill(limit=3)
    sp = cbp.hysteresis_state(cbp.premium_zscore(close, cbc, 720), 0.0, -1.5)
    cand = {"cbprem (no filter)": sp * trend * vs}
    for W in (12, 24, 48, 72, 168):
        z = whale_z(fl, W)
        for ex in (-1.0, -1.5, -2.0):
            cand[f"W{W} exit{ex}"] = sp * hysteresis(z, 0.0, ex) * trend * vs
    nets = {k: stats(w, close)[0] for k, w in cand.items()}
    wf, picks = [], {}
    for y in range(2020, 2027):
        best = max(nets, key=lambda k: sh(nets[k], IS[0], f"{y - 1}-12-31"))
        picks[y] = best
        wf.append(nets[best].loc[f"{y}-01-01":min(f"{y}-12-31", OOS[1])])
    wfn = pd.concat(wf)
    print("S2 walk-forward picks:", picks)
    print(f"S2 walk-forward 2020-26: {wfn.mean() / wfn.std() * np.sqrt(HPY):.2f} | 2023+: {sh(wfn, OOS[0], OOS[1]):.2f}"
          f" || cbprem 2020-26: {sh(nets['cbprem (no filter)'], '2020-01-01', OOS[1]):.2f}"
          f" | 2023+: {sh(nets['cbprem (no filter)'], OOS[0], OOS[1]):.2f}"
          f" || fixed S2 (W24,-1.5) 2020-26: {sh(nets['W24 exit-1.5'], '2020-01-01', OOS[1]):.2f}")
    allsh = pd.Series({k: sh(n, IS[0], OOS[1]) for k, n in nets.items()})
    print("neighbourhood full-sample Sharpe: median", round(allsh.drop('cbprem (no filter)').median(), 2),
          " min", round(allsh.drop('cbprem (no filter)').min(), 2), " cbprem", round(allsh['cbprem (no filter)'], 2))

    import vectorbt as vbt
    w2 = cand["W24 exit-1.5"].loc[IS[0]:OOS[1]]
    px = close.loc[IS[0]:OOS[1]]
    pf = vbt.Portfolio.from_orders(px, size=w2, size_type="targetpercent", fees=0.001, freq="1h", init_cash=1e6)
    vr = pf.returns()
    cr = nets["W24 exit-1.5"].loc[IS[0]:OOS[1]]
    print(f"vectorbt S2 (order at close t = w_t): Sharpe {vr.mean() / vr.std() * np.sqrt(HPY):.3f} vs custom "
          f"{cr.mean() / cr.std() * np.sqrt(HPY):.3f}  corr {vr.corr(cr):.4f}  max|diff| {np.abs(vr - cr).max():.5f}")

    d2 = nets["W24 exit-1.5"].loc[IS[0]:OOS[1]].resample("1D").sum()
    dc = nets["cbprem (no filter)"].loc[IS[0]:OOS[1]].resample("1D").sum()
    print("daily P&L corr S2 vs cbprem:", round(d2.corr(dc), 3))
    for nm, d in (("S2", d2), ("cbprem", dc)):
        eq = (1 + d).cumprod()
        dd = eq / eq.cummax() - 1
        print(nm, "worst drawdown", round(dd.min(), 3), "at", dd.idxmin().date(),
              "| time under water >20%:", round((dd < -0.2).mean(), 3))


if __name__ == "__main__":
    main()
