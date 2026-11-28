"""country-iv-premium -- option-implied fear premia of country ETFs vs SPY.

Bollerslev, Marrone, Xu & Zhou (2014): variance risk premia predict international equity
returns. Cross-sectional angle here: a country whose implied vol is high relative to its own
realized vol (VRP) or relative to the VIX (abnormal country fear) should earn a premium over
SPY in the following weeks, if fear is compensated; or under-perform, if implied vol leads bad
news.

IVs: VIX (SPY), CBOE VXEFA (EFA), VXEEM (EEM), VXEWZ (EWZ), VXFXI (FXI; missing 2022-03 -> 2025),
NSE India VIX (INDA), S&P/ASX 200 VIX (EWA). CBOE values settle 16:15 ET, after the ETF close,
so EVERY IV is lagged one session (the local ones too, for uniformity).
Pre-registered split (fixed before any result): IS 2011-03 -> 2018, OOS 2019 -> 2026."""
import os, sys
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
import data as D  # noqa: E402
import research_lib as rl  # noqa: E402

IVMAP = {"EFA": "CBOE_VXEFA", "EEM": "CBOE_VXEEM", "EWZ": "CBOE_VXEWZ", "FXI": "CBOE_VXFXI",
         "INDA": "IDX_INDIAVIX", "EWA": "IDX_AXVI"}
NAMES = list(IVMAP)
SPL = {"FULL": ("2011-03-16", "2026-12-31"), "IS": ("2011-03-16", "2018-12-31"), "OOS": ("2019-01-01", "2026-12-31")}


def _read(name):
    df = pd.read_parquet(os.path.join(rl.DATA_DIR, name + "_d.parquet"))
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df["Close"][~df.index.duplicated(keep="last")].sort_index()


def load():
    C = D.load_panel(NAMES + ["SPY"], "Close", start="2007-01-01")
    vix = D.load_panel(["^VIX"], "Close", start="2007-01-01")["^VIX"]
    IV = pd.DataFrame({k: _read(v).reindex(C.index) for k, v in IVMAP.items()})
    IV["SPY"] = vix
    IV = IV.shift(1)                     # known at close t: yesterday's settle
    return C, C.pct_change(), IV


def hedged(R, names=NAMES, win=252):
    x = R["SPY"]
    b = pd.DataFrame({n: R[n].rolling(win, min_periods=126).cov(x) / x.rolling(win, min_periods=126).var() for n in names})
    return R[names] - b.shift(1).mul(x, axis=0), b
