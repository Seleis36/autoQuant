"""CFTC Commitments of Traders for the CME currency futures, cached flat in data/.

Two reports:
  legacy  (1986+)  non-commercial ("speculator") and commercial long/short, open interest.
          -> data/CFTC_COT_legacy_fx_w.parquet
  tff     (2006+)  Traders in Financial Futures: dealer, asset manager, leveraged funds.
          -> data/CFTC_COT_tff_fx_w.parquet

Timing. Positions are as of Tuesday's close; the CFTC publishes them Friday 15:30 ET
(19:30/20:30 UTC), later after some federal holidays and weeks late in the 2013, 2018-19
and 2025 shutdowns. `avail_utc` below is set conservatively to the report Tuesday + 4 days
at 21:00 UTC (i.e. Saturday 21:00 UTC -- after the Friday New York close), clipped to the
shutdown backlog release dates. A consumer must only use a report on `=X` rows whose
00:00 UTC stamp is later than `avail_utc` -- the first such row is the Monday/Tuesday row.
Contract size is irrelevant: every signal here is a share of open interest.
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
CODES = {"099741": "EUR", "097741": "JPY", "096742": "GBP", "232741": "AUD",
         "090741": "CAD", "092741": "CHF", "112741": "NZD", "098662": "USD"}
SHUTDOWNS = [("2013-09-30", "2013-11-12", "2013-11-22"),
             ("2018-12-18", "2019-03-05", "2019-03-11"),
             ("2025-09-30", "2025-12-31", "2026-01-15")]
UA = {"User-Agent": "curl/8.5.0"}


def _zip_csv(name):
    raw = urllib.request.urlopen(urllib.request.Request(BASE + name, headers=UA), timeout=120).read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    return pd.read_csv(z.open(z.namelist()[0]), dtype=str, low_memory=False)


def _avail(dates):
    """Normal week: released Friday 15:30 ET -> usable after Saturday 21:00 UTC.
    Holiday week (a US federal holiday on the as-of Tuesday through that Friday -- New
    Year, July 4, Veterans Day, Thanksgiving, Christmas...): the CFTC releases on the
    following Monday (occasionally Tuesday) -> usable after Tuesday 21:00 UTC."""
    from pandas.tseries.holiday import USFederalHolidayCalendar
    hol = USFederalHolidayCalendar().holidays(start="1985-01-01", end="2035-12-31")
    dates = pd.Series(pd.to_datetime(dates.values), index=dates.index)
    a = dates + pd.Timedelta(days=4, hours=21)
    hit = np.zeros(len(dates), dtype=bool)
    for k in range(0, 4):                       # Tue, Wed, Thu, Fri of the release week
        hit |= (dates + pd.Timedelta(days=k)).isin(hol).values
    a[hit] = dates[hit] + pd.Timedelta(days=7, hours=21)
    for lo, hi, rel in SHUTDOWNS:
        m = (dates >= lo) & (dates <= hi)
        a[m] = a[m].clip(lower=pd.Timestamp(rel) + pd.Timedelta(hours=21))
    return a


FILES = {"legacy": ("CFTC_COT_legacy_fx_w.parquet", "deacot1986_2016.zip", "deacot{y}.zip"),
         "tff": ("CFTC_COT_tff_fx_w.parquet", "fin_fut_txt_2006_2016.zip", "fut_fin_txt_{y}.zip")}


def _parse(kind, fname):
    d = _zip_csv(fname)
    d.columns = [c.strip() for c in d.columns]
    if kind == "legacy":
        d["code"] = d["CFTC Contract Market Code"].str.strip()
        d = d[d["code"].isin(CODES)]
        return pd.DataFrame({
            "date": pd.to_datetime(d["As of Date in Form YYYY-MM-DD"]),
            "ccy": d["code"].map(CODES), "name": d["Market and Exchange Names"].str.strip(),
            "oi": d["Open Interest (All)"].astype(float),
            "nc_long": d["Noncommercial Positions-Long (All)"].astype(float),
            "nc_short": d["Noncommercial Positions-Short (All)"].astype(float),
            "c_long": d["Commercial Positions-Long (All)"].astype(float),
            "c_short": d["Commercial Positions-Short (All)"].astype(float)})
    d["code"] = d["CFTC_Contract_Market_Code"].str.strip()
    d = d[d["code"].isin(CODES)]
    f = pd.DataFrame({"date": pd.to_datetime(d["Report_Date_as_YYYY-MM-DD"]),
                      "ccy": d["code"].map(CODES), "name": d["Market_and_Exchange_Names"].str.strip(),
                      "oi": d["Open_Interest_All"].astype(float)})
    for grp, col in (("dealer", "Dealer"), ("am", "Asset_Mgr"), ("lev", "Lev_Money")):
        f[f"{grp}_long"] = d[f"{col}_Positions_Long_All"].astype(float)
        f[f"{grp}_short"] = d[f"{col}_Positions_Short_All"].astype(float)
    return f


def _finish(frames, path):
    df = pd.concat(frames).drop_duplicates(["date", "ccy"], keep="last").sort_values(["ccy", "date"])
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
    """Weekly live update: re-download only this year's legacy and TFF files (a few hundred
    KB each, vs ~30 MB for the full history) and merge them into the caches."""
    y = pd.Timestamp.today().year
    for kind in FILES:
        fname, _, yearly = FILES[kind]
        old = _fetch(kind)
        _finish([old[old["date"].dt.year < y].drop(columns="avail_utc"),
                 _parse(kind, yearly.format(y=y))], os.path.join(DATA_DIR, fname))


def net_share(df, grp):
    """Net long of a trader group as a share of open interest, wide: REPORT (as-of) date x
    ccy. Build signals on this grid (diffs and rolling windows count reports, not release
    stamps), then map them to trading rows with `on_fx_rows(..., avail=report_avail(df))`."""
    v = (df[f"{grp}_long"] - df[f"{grp}_short"]) / df["oi"]
    return df.assign(v=v).pivot_table(index="date", columns="ccy", values="v")


def report_avail(df):
    """Series: report as-of date -> first moment it is public (UTC)."""
    return df.groupby("date")["avail_utc"].max()


def on_fx_rows(wide, fx_index, avail):
    """Row stamped D (00:00 UTC on D) takes the value of the LATEST report (by as-of date)
    released strictly before D. Backlogs released together (shutdowns) resolve to the
    newest report in the batch, and a newer report released earlier than an older one is
    never overwritten by it."""
    a = avail.reindex(wide.index).dropna().sort_values()
    known = pd.Series(a.index, index=a.values).cummax()           # latest as-of date public
    known = known[~known.index.duplicated(keep="last")]
    known.index = known.index + pd.Timedelta(microseconds=1)
    kd = known.reindex(known.index.union(fx_index)).ffill().reindex(fx_index)
    out = wide.reindex(kd.values)
    out.index = fx_index
    return out


if __name__ == "__main__":
    lg = fetch_legacy(refresh=True)
    print(lg.groupby("ccy").agg(first=("date", "min"), last=("date", "max"), n=("date", "size"),
                                name=("name", "last")))
    tf = fetch_tff(refresh=True)
    print(tf.groupby("ccy").agg(first=("date", "min"), last=("date", "max"), n=("date", "size")))
