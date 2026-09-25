"""Live-data substitution check: RATE sleeve fed with yfinance ^TNX (refreshed by the live
runners) instead of FRED DGS10 (a separate fetcher). Only the sign of the 21-day change and the
betas matter, so the books should be near-identical."""
import sys, os
_H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(_H, "..", "shared"))
import importlib.util as iu, numpy as np, pandas as pd, data, sxlib as sx
sp = iu.spec_from_file_location("bs", os.path.join(_H, "strategy.py")); m = iu.module_from_spec(sp); sp.loader.exec_module(m)
c = data.load_panel(); o = data.load_panel(field="Open")
tnx = data.load_ohlcv("^TNX")["Close"]
Wd = m.target_weights(c, o); Wt = m.target_weights(c, o, y10=tnx)
a, na = sx.summary_rf(Wd, c, name="DGS10", start="2002-01-01"); b, nb = sx.summary_rf(Wt, c, name="^TNX", start="2002-01-01")
print(sx.fmt(pd.DataFrame([a, b]).rename(columns={"CAGRx": "CAGR"})))
print("daily corr", round(na.corr(nb), 4), "; sign agreement of 21d change:",
      round((np.sign(tnx.diff(21)).reindex(c.index) == np.sign(pd.read_parquet(os.path.join(sx.rl.DATA_DIR, 'FRED_DGS10_d.parquet'))['DGS10'].reindex(c.index).ffill().diff(21))).loc['2002':].mean(), 3))
