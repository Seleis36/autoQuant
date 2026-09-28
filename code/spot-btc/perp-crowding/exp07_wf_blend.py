"""Selection-adjusted evidence and portfolio value of the retail-crowding sleeve.

1. Walk-forward: family = {glob, topacc, toppos, top_m_glob(sign +)} x {exprank, z90} x
   {A standalone, B trend gate} = 16 candidates (contrarian sign fixed from IS for each ratio),
   re-selected every January 2022..2026 on expanding history from 2021-03; concatenated OOS.
2. Portfolio: daily P&L of P1 blended 50/50 (weights) with coinbase-premium (live spec,
   hourly weights sampled at 00:00) and with SMA50 x vol; and P3 (cbprem AND not-crowded).
"""
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_daily, btc_hourly, evaluate  # noqa: E402
import research_lib as rl  # noqa: E402
from exp01_screen import daily_metrics  # noqa: E402
from exp02_backtest import START, exp_rank  # noqa: E402
from exp04_validate import load_cbp  # noqa: E402

HPY = 365 * 24


def sh(x, ann=365):
    return x.mean() / x.std() * np.sqrt(ann)


def main():
    d = btc_daily()
    close = d.Close
    r = close.pct_change()
    vs = rl.vol_target_scalar(r, target=0.40, halflife=20, cap=1.0)
    trend = (close > close.rolling(50).mean()).astype(float)
    met = daily_metrics(close.index)
    ratios = {"glob": np.log(met.count_long_short_ratio), "topacc": np.log(met.count_toptrader_long_short_ratio),
              "toppos": np.log(met.sum_toptrader_long_short_ratio)}
    ratios["top_m_glob"] = ratios["toppos"] - ratios["glob"]
    sign = {"glob": -1, "topacc": -1, "toppos": -1, "top_m_glob": +1}   # IS partial-IC signs (exp01)
    cand = {}
    for k, x in ratios.items():
        x = x.replace([np.inf, -np.inf], np.nan)
        for nk, s in (("exprank", exp_rank(x)), ("z90", (x - x.rolling(90, min_periods=45).mean()) / x.rolling(90, min_periods=45).std())):
            on = (sign[k] * s > 0).astype(float).where(s.notna(), 0.0)
            cand[f"A {k} {nk}"] = evaluate(on * vs, close, start=START)[0]
            cand[f"B {k} {nk}"] = evaluate(on * trend * vs, close, start=START)[0]
    full = pd.Series({k: sh(v.loc[START:]) for k, v in cand.items()})
    oos = pd.Series({k: sh(v.loc["2023-01-01":]) for k, v in cand.items()})
    print("family (16): median full", round(full.median(), 2), " median OOS", round(oos.median(), 2),
          " min/max OOS", round(oos.min(), 2), round(oos.max(), 2))
    print(pd.DataFrame({"full": full, "OOS": oos}).round(2).sort_values("full", ascending=False).to_string())
    wf, picks = [], {}
    for y in range(2022, 2027):
        best = max(cand, key=lambda k: sh(cand[k].loc[START:f"{y - 1}-12-31"]))
        picks[y] = best
        wf.append(cand[best].loc[f"{y}-01-01":f"{y}-12-31"])
    wfn = pd.concat(wf)
    vb = evaluate(vs, close, start=START)[0]
    tb = evaluate(trend * vs, close, start=START)[0]
    print("walk-forward picks:", picks)
    print(f"walk-forward 2022-26: {sh(wfn):.2f} | 2023+: {sh(wfn.loc['2023-01-01':]):.2f} || vol B&H 2022-26 {sh(vb.loc['2022-01-01':]):.2f}"
          f" | SMA50xvol 2022-26 {sh(tb.loc['2022-01-01':]):.2f} | 2023+ {sh(tb.loc['2023-01-01':]):.2f}")

    # portfolio value vs coinbase-premium, daily-sampled
    g = ratios["glob"]
    on = (exp_rank(g) < 0).astype(float).where(exp_rank(g).notna(), 0.0)
    wP1 = on * vs
    cbp = load_cbp()
    hh = btc_hourly()
    hc = hh.Close
    cbc = pd.read_parquet(os.path.join(REPO, "data", "COINBASE_BTCUSD_1h.parquet"))["Close"].reindex(hc.index).ffill(limit=3)
    wc_h = cbp.target_weight(hc, cbc)
    on_h = on.copy()
    on_h.index = on_h.index + pd.Timedelta(days=1) - pd.Timedelta(hours=1)
    on_h = on_h.reindex(hc.index, method="ffill").fillna(0)
    wP1_h = wP1.copy()
    wP1_h.index = wP1_h.index + pd.Timedelta(days=1) - pd.Timedelta(hours=1)
    wP1_h = wP1_h.reindex(hc.index, method="ffill").fillna(0)
    books = {"cbprem": wc_h, "P1 (hourly-held)": wP1_h, "50/50 cbprem + P1": 0.5 * (wc_h + wP1_h),
             "P3 cbprem AND not-crowded": wc_h * on_h}
    out = []
    for k, w in books.items():
        n, _ = rl.backtest(w, hc, cost_bps=10, ann=HPY)
        n = n.loc[START:]
        eq = (1 + n).cumprod()
        out.append(pd.Series({"full": sh(n, HPY), "IS": sh(n.loc[:"2022-12-31"], HPY), "OOS": sh(n.loc["2023-01-01":], HPY),
                              "CAGR": eq.iloc[-1] ** (HPY / len(n)) - 1, "MaxDD": (eq / eq.cummax() - 1).min(),
                              "Expo": w.shift(1).loc[START:].mean()}, name=k))
    print(pd.DataFrame(out).round(2).to_string())


if __name__ == "__main__":
    main()
