"""oil-lagged-country -- Driesprong, Jacobsen & Maat (JFE 2008) "Striking oil: another puzzle?"

Oil price changes in month m predict lower equity returns in month m+1 across developed and
emerging markets (12 of 18 countries + world, 1973-2003), read as under-reaction to oil news.
Here: (a) time series -- the country-ETF basket / SPY timed by last month's oil change;
(b) cross-section -- the delayed reaction should scale with each country's own oil exposure
(exporters EWC/EWZ/EWA/EWU vs importers EWJ/EWY/INDA/FXI/EWG).

Data: WTI spot (FRED DCOILWTICO, 1986+) month-end; ETF total returns 2001+; backcast with local
price indices x FRED H.10 month-end FX, 1987-2000 (never used for a choice).
Split: IS 2001-2012, OOS 2013-2026 (post-publication 2004+ throughout)."""
import os, sys
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
import data as D  # noqa: E402
import research_lib as rl  # noqa: E402

COUNTRIES = ["EWJ", "EWG", "EWU", "EWZ", "EWY", "EWA", "EWC", "FXI", "INDA"]
SPL = {"FULL": ("2001-01-01", "2026-12-31"), "IS": ("2001-01-01", "2012-12-31"), "OOS": ("2013-01-01", "2026-12-31")}
BACK = {"1988-2000": ("1988-01-01", "2000-12-31")}


def me(s):
    return s.resample("ME").last()


def wti_daily():
    """EIA Cushing WTI spot (RWTC), daily 1986+, cached at data/EIA_WTI_d.parquet (source:
    https://www.eia.gov/dnav/pet/hist_xls/RWTCd.xls; FRED's DCOILWTICO mirror timed out).
    Spot prints are ~1 week late on EIA; the live edge would use CL=F (see 02)."""
    w = pd.read_parquet(os.path.join(rl.DATA_DIR, "EIA_WTI_d.parquet"))["Close"]
    w.index = pd.to_datetime(w.index)
    return w[w > 0].sort_index()


def oil_monthly():
    return np.log(me(wti_daily())).diff().rename("oil")


def etf_monthly():
    C = D.load_panel(COUNTRIES + ["SPY", "EFA", "EEM"], "Close", start="1998-12-01")
    M = me(C)
    R = M.pct_change(fill_method=None)
    av = R[COUNTRIES].notna().sum(axis=1)
    R["BASKET"] = R[COUNTRIES].mean(axis=1).where(av >= 2)
    R["WORLD"] = 0.5 * R["SPY"] + 0.5 * R["BASKET"]
    return R


def idx_long(t):
    a = pd.read_parquet(rl.daily_cache_path(t).replace("_d.parquet", "_d_long.parquet"))["Close"]
    a.index = pd.to_datetime(a.index)
    b = D.load_ohlcv(t)["Close"]
    s = pd.concat([a[a.index < b.index.min()], b]).sort_index()
    return s[~s.index.duplicated()]


def back_monthly():
    """USD price returns of local indices (month-end x H.10 month-end FX), 1984-2000."""
    fx = {"JP": 1 / D.load_fred("DEXJPUS"), "UK": D.load_fred("DEXUSUK"), "CA": 1 / D.load_fred("DEXCAUS"),
          "AU": D.load_fred("DEXUSAL"), "HK": 1 / D.load_fred("DEXHKUS")}   # cached H.10 files
    loc = {"JP": "^N225", "UK": "^FTSE", "CA": "^GSPTSE", "AU": "^AXJO", "HK": "^HSI"}
    L = pd.DataFrame({c: (me(idx_long(t)) * me(fx[c])) for c, t in loc.items()})
    R = L.pct_change(fill_method=None)
    R["US"] = me(idx_long("^GSPC")).pct_change()
    R["BASKET"] = R[list(loc)].mean(axis=1)
    R["WORLD"] = 0.5 * R["US"] + 0.5 * R["BASKET"]
    return R.loc[:"2000-12-31"]


def sr_m(x, a=None, b=None):
    x = x.loc[a:b].dropna()
    return x.mean() / x.std() * np.sqrt(12) if len(x) > 12 and x.std() > 0 else np.nan


def ols_t(y, x):
    d = pd.concat([y, x], axis=1).dropna()
    if len(d) < 24:
        return np.nan, np.nan, len(d)
    X = d.iloc[:, 1] - d.iloc[:, 1].mean(); Y = d.iloc[:, 0]
    b = (X * Y).sum() / (X ** 2).sum(); res = Y - Y.mean() - b * X
    return b, b / np.sqrt((res ** 2).sum() / (len(d) - 2) / (X ** 2).sum()), len(d)
