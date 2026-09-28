"""CFTC Commitments of Traders for the CBOT Treasury futures, cached flat in data/.

Two reports, same layout as `code/fx-majors/shared/fetch_cot_fx.py`:
  legacy  (1986+)  non-commercial and commercial long/short, open interest, per contract.
          -> data/CFTC_COT_legacy_ust_w.parquet
  tff     (2006+)  Traders in Financial Futures: dealer, asset manager, leveraged funds, other.
          -> data/CFTC_COT_tff_ust_w.parquet

Contracts (column `tenor`): 2y (042601), 5y (044601), 10y (043602), ultra-10y (043607, 2016+),
bond (020601, classic 30y), ultra-bond (020604, 2010+).

Timing. Positions are as of Tuesday's close; the CFTC publishes them Friday 15:30 ET (the
following Monday in US-holiday weeks; weeks late after the 2013, 2018-19 and 2025 shutdowns).
`avail_utc` is the conservative moment the report is public: Tuesday + 4 days 21:00 UTC
(Saturday), or Tuesday + 7 days 21:00 UTC in holiday weeks, clipped to the shutdown backlog
dates. A daily ETF bar stamped D (US close) may only use a report whose `avail_utc` falls on a
calendar date strictly before D -- so a normal report first trades at Monday's close.
"""
import io
import os
import sys
import urllib.request
import zipfile

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "code", "shared"))
from research_lib import DATA_DIR, _atomic_parquet  # noqa: E402

BASE = "https://www.cftc.gov/files/dea/history/"
CODES = {"042601": "2y", "044601": "5y", "043602": "10y", "043607": "u10y",
         "020601": "bond", "020604": "ubond"}
SHUTDOWNS = [("2013-09-30", "2013-11-12", "2013-11-22"),
             ("2018-12-18", "2019-03-05", "2019-03-11"),
             ("2025-09-30", "2025-12-31", "2026-01-15")]
UA = {"User-Agent": "curl/8.5.0"}
FILES = {"legacy": ("CFTC_COT_legacy_ust_w.parquet", "deacot1986_2016.zip", "deacot{y}.zip"),
         "tff": ("CFTC_COT_tff_ust_w.parquet", "fin_fut_txt_2006_2016.zip", "fut_fin_txt_{y}.zip")}


def _zip_csv(name):
    raw = urllib.request.urlopen(urllib.request.Request(BASE + name, headers=UA), timeout=180).read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    return pd.read_csv(z.open(z.namelist()[0]), dtype=str, low_memory=False)


def _avail(dates):
    from pandas.tseries.holiday import USFederalHolidayCalendar
    hol = USFederalHolidayCalendar().holidays(start="1985-01-01", end="2035-12-31")
    dates = pd.Series(pd.to_datetime(dates.values), index=dates.index)
    a = dates + pd.Timedelta(days=4, hours=21)
    hit = np.zeros(len(dates), dtype=bool)
    for k in range(0, 4):
        hit |= (dates + pd.Timedelta(days=k)).isin(hol).values
    a[hit] = dates[hit] + pd.Timedelta(days=7, hours=21)
    for lo, hi, rel in SHUTDOWNS:
        m = (dates >= lo) & (dates <= hi)
        a[m] = a[m].clip(lower=pd.Timestamp(rel) + pd.Timedelta(hours=21))
    return a


def _parse(kind, fname):
    d = _zip_csv(fname)
    d.columns = [c.strip() for c in d.columns]
    if kind == "legacy":
        d["code"] = d["CFTC Contract Market Code"].str.strip()
        d = d[d["code"].isin(CODES)]
        return pd.DataFrame({
            "date": pd.to_datetime(d["As of Date in Form YYYY-MM-DD"]),
            "tenor": d["code"].map(CODES), "name": d["Market and Exchange Names"].str.strip(),
            "oi": d["Open Interest (All)"].astype(float),
            "nc_long": d["Noncommercial Positions-Long (All)"].astype(float),
            "nc_short": d["Noncommercial Positions-Short (All)"].astype(float),
            "nc_spread": d["Noncommercial Positions-Spreading (All)"].astype(float),
            "c_long": d["Commercial Positions-Long (All)"].astype(float),
            "c_short": d["Commercial Positions-Short (All)"].astype(float),
            "nr_long": d["Nonreportable Positions-Long (All)"].astype(float),
            "nr_short": d["Nonreportable Positions-Short (All)"].astype(float)})
    d["code"] = d["CFTC_Contract_Market_Code"].str.strip()
    d = d[d["code"].isin(CODES)]
    f = pd.DataFrame({"date": pd.to_datetime(d["Report_Date_as_YYYY-MM-DD"]),
                      "tenor": d["code"].map(CODES), "name": d["Market_and_Exchange_Names"].str.strip(),
                      "oi": d["Open_Interest_All"].astype(float)})
    for grp, col in (("dealer", "Dealer"), ("am", "Asset_Mgr"), ("lev", "Lev_Money"),
                     ("oth", "Other_Rept"), ("nr", "NonRept")):
        f[f"{grp}_long"] = d[f"{col}_Positions_Long_All"].astype(float)
        f[f"{grp}_short"] = d[f"{col}_Positions_Short_All"].astype(float)
    return f


def _finish(frames, path):
    df = pd.concat(frames).drop_duplicates(["date", "tenor"], keep="last").sort_values(["tenor", "date"])
    df = df.reset_index(drop=True)
    df["avail_utc"] = _avail(df["date"]).values
    _atomic_parquet(df, path)
    return df


def _fetch(kind, refresh=False):
    fname, hist, yearly = FILES[kind]
    path = os.path.join(DATA_DIR, fname)
    if os.path.exists(path) and not refresh:
        return pd.read_parquet(path)
    names = [hist] + [yearly.format(y=y) for y in range(2017, pd.Timestamp.today().year + 1)]
    return _finish([_parse(kind, n) for n in names], path)


def fetch_legacy(refresh=False):
    return _fetch("legacy", refresh)


def fetch_tff(refresh=False):
    return _fetch("tff", refresh)


def refresh_current_year():
    """Weekly live update: re-download only this year's files and merge them into the caches."""
    y = pd.Timestamp.today().year
    for kind in FILES:
        fname, _, yearly = FILES[kind]
        old = _fetch(kind)
        _finish([old[old["date"].dt.year < y].drop(columns="avail_utc"),
                 _parse(kind, yearly.format(y=y))], os.path.join(DATA_DIR, fname))


def net_share(df, grp, tenors=None):
    """Net long of a trader group as a share of open interest, wide: report date x tenor."""
    v = (df[f"{grp}_long"] - df[f"{grp}_short"]) / df["oi"]
    w = df.assign(v=v).pivot_table(index="date", columns="tenor", values="v")
    return w if tenors is None else w.reindex(columns=list(tenors))


def report_avail(df):
    """Series: report as-of date -> first moment it is public (UTC)."""
    return df.groupby("date")["avail_utc"].max()


def on_daily_rows(wide, index, avail):
    """Daily bar stamped D (US close) takes the value of the LATEST report (by as-of date)
    whose release falls on a calendar date strictly before D."""
    a = avail.reindex(wide.index).dropna()
    usable_from = (a.dt.normalize() + pd.Timedelta(days=1)).sort_values()
    known = pd.Series(usable_from.index, index=usable_from.values).cummax()
    known = known[~known.index.duplicated(keep="last")]
    kd = known.reindex(known.index.union(index)).ffill().reindex(index)
    out = wide.reindex(kd.values)
    out.index = index
    return out


if __name__ == "__main__":
    lg = fetch_legacy(refresh=True)
    print(lg.groupby("tenor").agg(first=("date", "min"), last=("date", "max"), n=("date", "size"),
                                  name=("name", "last")))
    tf = fetch_tff(refresh=True)
    print(tf.groupby("tenor").agg(first=("date", "min"), last=("date", "max"), n=("date", "size")))
