"""CFTC Commitments of Traders for CBOE VIX futures, cached flat in data/.

Reuses the download / release-timing logic of `code/fx-majors/shared/fetch_cot_fx.py`
(same CFTC zip files, same `avail_utc` rule: report Tuesday + 4 days 21:00 UTC, holiday
weeks + 7 days, shutdown backlogs clipped to their release dates).

  tff     (2006+)  dealer / asset manager / leveraged funds / other reportables
          -> data/CFTC_COT_tff_vix_w.parquet
  legacy  (2004+)  non-commercial / commercial
          -> data/CFTC_COT_legacy_vix_w.parquet

VIX futures CFTC contract code: 1170E1 ("VIX FUTURES - CBOE FUTURES EXCHANGE"; the CFE
renamed the market line a few times, the code is stable). The mini-VIX (VXM, 2020+) has
its own code and is ignored: it is < 2 % of VX open interest.

Usage on daily US-session bars: `on_session_rows(wide, idx, avail)` gives, for the bar
stamped session date D, the latest report whose avail_utc is strictly before D 00:00 UTC
-- i.e. a Friday release is first used at MONDAY's close (conservative by one session).
"""
import os
import sys

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "code", "shared"))
sys.path.insert(0, os.path.join(REPO, "code", "fx-majors", "shared"))
from research_lib import DATA_DIR, _atomic_parquet  # noqa: E402
import fetch_cot_fx as fx  # noqa: E402

CODES = {"1170E1": "VX"}
TFF_PATH = os.path.join(DATA_DIR, "CFTC_COT_tff_vix_w.parquet")
LEG_PATH = os.path.join(DATA_DIR, "CFTC_COT_legacy_vix_w.parquet")


def _parse_tff(fname):
    d = fx._zip_csv(fname)
    d.columns = [c.strip() for c in d.columns]
    d["code"] = d["CFTC_Contract_Market_Code"].str.strip()
    d = d[d["code"].isin(CODES)]
    f = pd.DataFrame({"date": pd.to_datetime(d["Report_Date_as_YYYY-MM-DD"]),
                      "name": d["Market_and_Exchange_Names"].str.strip(),
                      "oi": d["Open_Interest_All"].astype(float)})
    for grp, col in (("dealer", "Dealer"), ("am", "Asset_Mgr"), ("lev", "Lev_Money"),
                     ("oth", "Other_Rept"), ("nonrep", "NonRept")):
        f[f"{grp}_long"] = d[f"{col}_Positions_Long_All"].astype(float)
        f[f"{grp}_short"] = d[f"{col}_Positions_Short_All"].astype(float)
    if "Dealer_Positions_Spread_All" in d:
        f["dealer_spread"] = d["Dealer_Positions_Spread_All"].astype(float)
    f["lev_spread"] = d["Lev_Money_Positions_Spread_All"].astype(float)
    f["am_spread"] = d["Asset_Mgr_Positions_Spread_All"].astype(float)
    return f


def _parse_legacy(fname):
    d = fx._zip_csv(fname)
    d.columns = [c.strip() for c in d.columns]
    d["code"] = d["CFTC Contract Market Code"].str.strip()
    d = d[d["code"].isin(CODES)]
    return pd.DataFrame({
        "date": pd.to_datetime(d["As of Date in Form YYYY-MM-DD"]),
        "name": d["Market and Exchange Names"].str.strip(),
        "oi": d["Open Interest (All)"].astype(float),
        "nc_long": d["Noncommercial Positions-Long (All)"].astype(float),
        "nc_short": d["Noncommercial Positions-Short (All)"].astype(float),
        "nc_spread": d["Noncommercial Positions-Spreading (All)"].astype(float),
        "c_long": d["Commercial Positions-Long (All)"].astype(float),
        "c_short": d["Commercial Positions-Short (All)"].astype(float)})


def _finish(frames, path):
    df = pd.concat(frames).drop_duplicates(["date"], keep="last").sort_values("date")
    df = df.reset_index(drop=True)
    df["avail_utc"] = fx._avail(df["date"]).values
    _atomic_parquet(df, path)
    return df


def fetch_tff(refresh=False, years=None):
    if os.path.exists(TFF_PATH) and not refresh:
        return pd.read_parquet(TFF_PATH)
    last = pd.Timestamp.today().year
    names = ["fin_fut_txt_2006_2016.zip"] + [f"fut_fin_txt_{y}.zip" for y in range(2017, last + 1)]
    return _finish([_parse_tff(n) for n in names], TFF_PATH)


def fetch_legacy(refresh=False):
    if os.path.exists(LEG_PATH) and not refresh:
        return pd.read_parquet(LEG_PATH)
    last = pd.Timestamp.today().year
    names = ["deacot1986_2016.zip"] + [f"deacot{y}.zip" for y in range(2017, last + 1)]
    return _finish([_parse_legacy(n) for n in names], LEG_PATH)


def refresh_current_year():
    """Weekly live update: re-download only this year's files and merge."""
    y = pd.Timestamp.today().year
    old = fetch_tff()
    _finish([old[old["date"].dt.year < y].drop(columns="avail_utc"),
             _parse_tff(f"fut_fin_txt_{y}.zip")], TFF_PATH)
    old = fetch_legacy()
    _finish([old[old["date"].dt.year < y].drop(columns="avail_utc"),
             _parse_legacy(f"deacot{y}.zip")], LEG_PATH)


def on_session_rows(weekly, idx, avail):
    """weekly: Series/DataFrame indexed by report as-of date. idx: daily session dates.
    Bar D takes the latest report (by as-of date) whose avail_utc < D 00:00 UTC."""
    a = avail.reindex(weekly.index).dropna().sort_values()
    known = pd.Series(a.index, index=a.values).cummax()
    known = known[~known.index.duplicated(keep="last")]
    known.index = known.index + pd.Timedelta(microseconds=1)
    kd = known.reindex(known.index.union(idx)).ffill().reindex(idx)
    out = weekly.reindex(kd.values)
    out.index = idx
    return out


if __name__ == "__main__":
    t = fetch_tff(refresh=True)
    print(t[["date", "name", "oi"]].head(), t[["date", "name", "oi"]].tail(), len(t))
    lg = fetch_legacy(refresh=True)
    print(lg[["date", "name", "oi"]].head(), lg[["date", "name", "oi"]].tail(), len(lg))
