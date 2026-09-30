"""exp03 — re-framing: market-wide leverage as a TIME-SERIES timer (leverage cycles).

  L_btc = log(BTCUSDT OI value / BTC market cap)                          2020-09+
  L_agg = log(sum OI value of the 64 perps / sum of their market caps)    2021-12+
  z     = (L - trailing 365d mean) / trailing 365d std   (past only; min 180 obs)
Forward BTC (and EW-top-20-alt) spot returns over 7 / 30 days by z tercile, and two
pre-declared rules on BTC spot (10 bp):
  R1 long/flat: hold BTC unless z > +1 (de-lever when leverage is extreme)
  R2 long/flat: hold BTC only when z < 0
vs buy & hold over the same dates. IS through 2023-12, OOS 2024+.
"""
import os
import importlib.util
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("rcx", os.path.join(_HERE, "..", "retail-crowding-xs", "common.py"))
rcx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rcx)
import sys  # noqa: E402
sys.path.insert(0, os.path.join(rcx.ROOT, "code", "crypto-alts", "shared"))
import cmc  # noqa: E402
import metrics_panel as mp  # noqa: E402
import research_lib as rl  # noqa: E402

close, vol, met, mask = rcx.load(start="2020-01-01")
idmap = cmc.yahoo_map(close)
mcap = (cmc.wide("circulatingSupply", idmap, index=close.index) * close).where(lambda d: d > 0)
btc_m = mp.daily_metrics(["BTCUSDT"])["sum_open_interest_value"]["BTCUSDT"].reindex(close.index)
L_btc = np.log(btc_m / mcap["BTC-USD"])
oiv = met["sum_open_interest_value"]
ok = oiv.notna() & mcap.notna()
n_ok = ok.sum(axis=1)
L_agg = np.log(oiv.where(ok).sum(axis=1) / mcap.where(ok).sum(axis=1)).where(n_ok >= 40)


def z(L):
    return (L - L.rolling(365, min_periods=180).mean()) / L.rolling(365, min_periods=180).std()


btc = close["BTC-USD"]
alt = (1 + close.pct_change(fill_method=None).where(mask).drop(columns="BTC-USD").mean(axis=1).fillna(0)).cumprod()
for nm, L in {"L_btc": L_btc, "L_agg": L_agg}.items():
    zz = z(L)
    for tgt_nm, px in {"BTC": btc, "ALT-EW": alt}.items():
        for h in (7, 30):
            f = px.shift(-h) / px - 1
            d = pd.DataFrame({"z": zz, "f": f}).dropna()
            for per, (a, b) in {"IS": ("2020-01-01", "2023-12-31"), "OOS": ("2024-01-01", "2026-12-31")}.items():
                g = d.loc[a:b]
                if len(g) < 100:
                    continue
                t = pd.qcut(g.z, 3, labels=["low", "mid", "high"])
                m = g.groupby(t, observed=True).f.mean() * 1e2
                ic = g.z.corr(g.f, method="spearman")
                print(f"{nm} {tgt_nm} h{h} {per}: n={len(g)} IC={ic:+.3f}  fwd% by z tercile "
                      + " ".join(f"{k}:{v:+.2f}" for k, v in m.items()))
    rows = []
    for rule, w in {"R1 flat if z>1": (zz <= 1).astype(float), "R2 long if z<0": (zz < 0).astype(float),
                    "buy&hold": pd.Series(1.0, index=zz.index)}.items():
        w = w.where(zz.notna())
        start = zz.dropna().index[0]
        net, st = rl.backtest(w.fillna(0).loc[start:], btc.loc[start:], cost_bps=10)
        r = {"L": nm, "rule": rule, "start": start.date()}
        for per, (a, b) in {"full": (start, "2026-12-31"), "IS": (start, "2023-12-31"), "OOS": ("2024-01-01", "2026-12-31")}.items():
            r[f"SR_{per}"] = rl.perf_stats(net.loc[a:b])["Sharpe"]
        r["MaxDD"] = st["MaxDD"]
        r["exposure"] = st["AvgExposure"]
        rows.append(r)
    print(pd.DataFrame(rows).round(2).to_string(index=False))
