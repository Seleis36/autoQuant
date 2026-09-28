"""Fetch TIPS / nominal ETFs and the NSA CPI index needed by tips-seasonal-carry.

* STIP (0-5y TIPS, 2010-12), VTIP (0-5y TIPS, 2012-10), SCHP (2010-08), LTPZ (15y+ TIPS, 2009-09),
  IEI (3-7y Treasuries, 2007-01), VGSH (1-3y, 2009-11) -> flat cache data/<T>_d.parquet (2010+).
* TIP (2003-12) pre-2010 copy -> data/TIP_d_pre2010.parquet, IEI_d_pre2010.parquet.
* FRED CPIAUCNS (CPI-U NSA, the TIPS reference index; never revised) and the constant-maturity
  TIPS real yields DFII5/DFII10 -> data/FRED_<ID>_d.parquet via fetch_fred_daily.fred.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
import pandas as pd, yfinance as yf
from rb_data import rl, fred

for t in ["STIP", "VTIP", "SCHP", "LTPZ", "IEI", "VGSH", "TIP", "SHY", "IEF"]:
    df = rl.load_series(t)
    print(t, df.index.min().date(), df.index.max().date(), len(df))
for t in ["TIP", "IEI"]:
    path = rl.daily_cache_path(t).replace("_d.parquet", "_d_pre2010.parquet")
    if not os.path.exists(path):
        df = yf.download(t, start="2002-01-01", end="2010-01-05", auto_adjust=True,
                         progress=False, multi_level_index=False).dropna()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        rl._atomic_parquet(df, path)
    d = pd.read_parquet(path); print(t, "pre2010", d.index.min().date(), d.index.max().date(), len(d))
for sid in ["CPIAUCNS", "DFII5", "DFII10", "T5YIE", "T10YIE"]:
    s = fred(sid, force=True); print(sid, s.index.min().date(), s.index.max().date(), len(s))
