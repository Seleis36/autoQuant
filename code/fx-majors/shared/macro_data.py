"""Rates and macro inputs for fx-majors ideas, cached flat under data/.

* `policy_rates()`  -- BIS WS_CBPOL daily central-bank policy rates, one column per
  currency. Policy rates are announced, never revised, and known the day they change,
  so they are point-in-time by construction. Cached as data/BIS_CBPOL_d.parquet.
* `fred(sid)`       -- any FRED series (daily or monthly), cached as
  data/FRED_<sid>_d.parquet (the naming the rest of the repo already uses).
* `h10_fx()`        -- Federal Reserve H.10 noon New York buying rates (FRED DEX*),
  USD per foreign unit, 1971+ (EUR 1999+). An independent, longer price history than
  `=X` for validating slow monthly signals before 2010. Noon ET = 16:00/17:00 UTC.
* `long_yields_m()` -- OECD monthly-average 10-year government yields (FRED IRLTLT01),
  euro leg = Germany. A monthly average for month M is only complete at the end of M
  and is published in early M+1, so callers must lag it (see `available_monthly`).
"""
import io
import os
import sys
import urllib.request

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
DATA = os.path.join(REPO, "data")
sys.path.insert(0, os.path.join(REPO, "code", "shared"))
from research_lib import _atomic_parquet  # noqa: E402

CCYS = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
BIS_AREA = {"USD": "US", "EUR": "XM", "GBP": "GB", "JPY": "JP", "AUD": "AU",
            "CAD": "CA", "CHF": "CH", "NZD": "NZ"}
# FRED H.10 ids; `inv` means the series is foreign units per USD
H10 = {"EUR": ("DEXUSEU", False), "GBP": ("DEXUSUK", False), "JPY": ("DEXJPUS", True),
       "AUD": ("DEXUSAL", False), "CAD": ("DEXCAUS", True), "CHF": ("DEXSZUS", True),
       "NZD": ("DEXUSNZ", False)}
LY10 = {"USD": "IRLTLT01USM156N", "EUR": "IRLTLT01DEM156N", "GBP": "IRLTLT01GBM156N",
        "JPY": "IRLTLT01JPM156N", "AUD": "IRLTLT01AUM156N", "CAD": "IRLTLT01CAM156N",
        "CHF": "IRLTLT01CHM156N", "NZD": "IRLTLT01NZM156N"}
UA = {"User-Agent": "autoquant-research/1.0"}


def _http(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def policy_rates(refresh=False, start="1990-01-01"):
    path = os.path.join(DATA, "BIS_CBPOL_d.parquet")
    if refresh or not os.path.exists(path):
        keys = "+".join(BIS_AREA.values())
        raw = _http(f"https://stats.bis.org/api/v1/data/WS_CBPOL/D.{keys}"
                    f"?startPeriod={start}&format=csv", timeout=300)
        d = pd.read_csv(io.BytesIO(raw), usecols=["REF_AREA", "TIME_PERIOD", "OBS_VALUE"])
        w = d.pivot_table(index="TIME_PERIOD", columns="REF_AREA", values="OBS_VALUE")
        w.index = pd.to_datetime(w.index)
        w = w.rename(columns={v: k for k, v in BIS_AREA.items()})[list(BIS_AREA)]
        _atomic_parquet(w.sort_index(), path)
    return pd.read_parquet(path)


def short_rates(refresh=False):
    """Daily policy-rate proxy for the market short rate, calendar-day index, ffilled.
    EUR: the ECB main refi rate until 2008, the deposit rate from 2009 -- under full
    allotment (Oct 2008 on) EONIA/ESTR trade at the deposit floor, and the refi rate
    overstated euro short rates by 50-100 bp through the negative-rate years."""
    r = policy_rates(refresh=refresh)
    r = r.reindex(pd.date_range(r.index.min(), pd.Timestamp.today().normalize())).ffill()
    dfr = fred("ECBDFR", refresh=refresh)
    dfr = dfr.reindex(r.index).ffill()
    r.loc["2009-01-01":, "EUR"] = dfr.loc["2009-01-01":]
    return r


def fred(sid, refresh=False):
    path = os.path.join(DATA, f"FRED_{sid}_d.parquet")
    if refresh or not os.path.exists(path):
        raw = _http(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}")
        d = pd.read_csv(io.BytesIO(raw), na_values=["."])
        d.columns = ["date", sid]
        d["date"] = pd.to_datetime(d["date"])
        d = d.set_index("date").astype(float)
        _atomic_parquet(d, path)
    s = pd.read_parquet(path).iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    return s.dropna()


def h10_fx(refresh=False):
    """USD per foreign unit, noon NY, business days. Positive return = foreign ccy up."""
    out = {}
    for c, (sid, inv) in H10.items():
        s = fred(sid, refresh=refresh)
        out[c] = 1.0 / s if inv else s
    return pd.DataFrame(out).sort_index()


def long_yields_m(refresh=False):
    """Monthly-average 10y yields, indexed by the first day of the observation month."""
    return pd.DataFrame({c: fred(s, refresh=refresh) for c, s in LY10.items()}).sort_index()


def available_monthly(m, lag_months=1):
    """Re-index a monthly frame (stamped at month start) to the date it is safely known:
    observation month M becomes usable at the END of month M+lag_months."""
    m = m.copy()
    m.index = (m.index.to_period("M") + lag_months).to_timestamp(how="end").normalize()
    return m


if __name__ == "__main__":
    r = policy_rates(refresh=True)
    print(r.tail(3)); print(r.loc["2010":].describe().T[["count", "min", "max"]])
    h = h10_fx(refresh=True); print(h.dropna().index.min(), h.tail(2))
    y = long_yields_m(refresh=True); print(y.tail(3))
