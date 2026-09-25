"""eth-btc-premium-spread 01: does ETH's USD-venue premium *relative to BTC's* predict the ETH/BTC ratio?

z_e, z_b = 720h z-scores of (Coinbase/Binance - 1) for ETH and BTC; spread s = z_e - z_b.
Also the raw premium difference (prem_e - prem_b) z-scored. Target: forward ETH/BTC log-ratio return
over 1/4/24/72 h (Binance closes). Decile spreads and Spearman IC, IS <= 2023 / OOS 2024+.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "eth-venue-premium"))
import numpy as np, pandas as pd
from ethdata import bars, IS_END, OOS_START
from fetch_coinbase import load as cb_load
be = bars("ETHUSDT", "1h")["Close"]; bb = bars("BTCUSDT", "1h")["Close"].reindex(be.index)
ce = cb_load("ETH-USD")["Close"].reindex(be.index); cbb = cb_load("BTC-USD")["Close"].reindex(be.index)
pe, pb = ce / be - 1, cbb / bb - 1
z = lambda p, w=720: (p - p.rolling(w, min_periods=w // 2).mean()) / p.rolling(w, min_periods=w // 2).std()
S = pd.DataFrame({"z_e - z_b": z(pe) - z(pb), "z(pe - pb)": z(pe - pb), "z_e": z(pe), "z_b": z(pb)})
lr = np.log(be / bb)
rows = []
for H in [1, 4, 24, 72]:
    fwd = lr.shift(-H) - lr
    for s in S:
        r = dict(sig=s, H=H)
        for p, (a, b) in {"IS": ("2017-10-01", IS_END), "OOS": (OOS_START, None)}.items():
            x = pd.concat([S[s], fwd], axis=1, keys=["s", "f"]).loc[a:b].dropna()
            r[f"IC_{p}"] = x.s.corr(x.f, method="spearman")
            q = pd.qcut(x.s, 10, labels=False)
            m = x.groupby(q).f.mean() * 1e4
            r[f"D10-D1_bp_{p}"] = m.iloc[-1] - m.iloc[0]
        rows.append(r)
pd.set_option("display.width", 200)
print(pd.DataFrame(rows).round(3).to_string(index=False))
