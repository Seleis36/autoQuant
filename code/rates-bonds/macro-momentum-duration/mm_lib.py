"""Point-in-time macro momentum for timing duration and credit.

At each month-end decision date t the signal uses, for every series, the vintage that was
public at t (`fetch_alfred.as_of`): the whole history as known then, revisions and release
lag included. The shared vintage grid is monthly (1st of the month), so a number released
on the 12th is first seen at the following month's grid point -- late, never early.

For each series: k-month change (level change for the unemployment rate and sentiment,
log change for the rest), measured on the latest value in the vintage, then z-scored against
the history of the same k-month change inside that same vintage (1970+). No statistic ever
mixes vintages.

    growth    = mean z of  -d(UNRATE), d ln PAYEMS, d ln INDPRO, d ln real RSAFS, d ln HOUST, d UMCSENT
    inflation = mean z of  the change in k-month CPI inflation and core PCE inflation
                           versus the k months before (inflation ACCELERATION)
    macro     = (growth + inflation) / 2          -> bearish for duration when positive
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "rates-bonds", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "rates-bonds", "rates-carry-trend"))
import research_lib as rl  # noqa: E402
from fetch_alfred import load_vintages  # noqa: E402
from rb_data import etf_close, cmt_returns  # noqa: E402
from fetch_fred_daily import fred  # noqa: E402

GROWTH = {"UNRATE": ("diff", -1), "PAYEMS": ("log", 1), "INDPRO": ("log", 1), "RSAFS": ("real", 1),
          "HOUST": ("log", 1), "UMCSENT": ("diff", 1)}
INFL = ["CPIAUCSL", "PCEPILFE"]
HIST_START = "1970-01-01"


class Vintages:
    """All vintages of the needed series, indexed for fast `as_of`."""

    def __init__(self):
        self.v = {}
        for s in list(GROWTH) + INFL:
            df = load_vintages(s)
            self.v[s] = {vd: g.set_index("obs_date")["value"].sort_index() for vd, g in df.groupby("vintage_date")}
        self.dates = {s: np.array(sorted(d)) for s, d in self.v.items()}

    def as_of(self, s, when):
        ds = self.dates[s]
        i = np.searchsorted(ds, np.datetime64(pd.Timestamp(when)), side="right") - 1
        return None if i < 0 else self.v[s][pd.Timestamp(ds[i])]

    def first(self):
        """First date with a vintage for the four core series (CPI, payrolls, unemployment,
        industrial production). The others join the averages when their vintages begin
        (core PCE 2000-08, retail sales and sentiment later)."""
        return max(pd.Timestamp(self.dates[s][0]) for s in ("CPIAUCSL", "PAYEMS", "UNRATE", "INDPRO"))


def _z_last(change):
    c = change.loc[HIST_START:].dropna()
    if len(c) < 120:
        return np.nan
    return float((c.iloc[-1] - c.mean()) / c.std())


def signal_at(vt, when, k):
    """(growth, inflation, n_growth, n_infl, age_days) as known at `when`."""
    g, age = [], []
    cpi = vt.as_of("CPIAUCSL", when)
    for s, (kind, sign) in GROWTH.items():
        x = vt.as_of(s, when)
        if x is None or len(x) < 200:
            continue
        if kind == "real":
            if cpi is None:
                continue
            j = x.index.intersection(cpi.index)
            x = x.loc[j] / cpi.loc[j]
            kind = "log"
        y = np.log(x) if kind == "log" else x
        g.append(sign * _z_last(y.diff(k)))
        age.append((pd.Timestamp(when) - x.index[-1]).days)
    f = []
    for s in INFL:
        x = vt.as_of(s, when)
        if x is None or len(x) < 200:
            continue
        infl = np.log(x).diff(k)
        f.append(_z_last(infl - infl.shift(k)))
    gz = np.nanmean(g) if len(g) else np.nan
    fz = np.nanmean(f) if len(f) else np.nan
    return gz, fz, len(g), len(f), (np.mean(age) if age else np.nan)


def build_signals(dates, ks=(3, 6, 12)):
    vt = Vintages()
    rows = []
    for d in dates:
        if pd.Timestamp(d) < vt.first():
            continue
        row = {"date": d}
        for k in ks:
            gz, fz, ng, nf, age = signal_at(vt, d, k)
            row.update({f"growth{k}": gz, f"infl{k}": fz, f"n{k}": ng + nf})
        row["age_days"] = age
        rows.append(row)
    return pd.DataFrame(rows).set_index("date")


def monthly_returns():
    """Month-end-to-month-end excess returns: syn10 (1982+), IEF, TLT, HYG, and the
    duration-stripped credit premium HYG - beta x IEF (trailing 36-month beta)."""
    syn = cmt_returns(maturities=(10,), excess=True)[10]
    etf = etf_close(["IEF", "TLT", "HYG", "SHY", "LQD"])
    dff = fred("DFF")
    rf_d = (dff / 100 / 360).reindex(pd.date_range(dff.index[0], dff.index[-1])).ffill()
    m = pd.DataFrame({"syn10": (1 + syn).resample("ME").prod() - 1})
    rf_m = (1 + rf_d).resample("ME").prod() - 1
    for t in etf:
        m[t] = etf[t].resample("ME").last().pct_change() - rf_m
    b = m["HYG"].rolling(36, min_periods=18).cov(m["IEF"]) / m["IEF"].rolling(36, min_periods=18).var()
    m["credit"] = m["HYG"] - b.shift(1) * m["IEF"]
    return m


def sharpe_m(r, a=None, b=None):
    r = r.loc[a:b].dropna()
    return r.mean() / r.std() * np.sqrt(12) if len(r) > 24 and r.std() > 0 else np.nan
