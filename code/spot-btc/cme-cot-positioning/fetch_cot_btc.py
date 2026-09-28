"""CFTC Traders-in-Financial-Futures (TFF) and legacy COT for CME Bitcoin futures.

Reuses the download and release-timing logic of `code/fx-majors/shared/fetch_cot_fx.py`
(same CFTC zip files, same conservative `avail_utc` rule: report Tuesday + 4 days 21:00
UTC, holiday weeks + 7 days, shutdown backlogs clipped to their release dates).

Contracts (CFTC code -> BTC per contract):
  133741  BITCOIN - CHICAGO MERCANTILE EXCHANGE          5 BTC   (2017-12 ->)
  133742  MICRO BITCOIN - CHICAGO MERCANTILE EXCHANGE    0.1 BTC (2021-05 ->)

Positions are stored per contract in contracts AND in BTC, so a consumer can build the
combined (standard + micro) book in BTC units.

  -> data/CFTC_COT_tff_btc_w.parquet
  -> data/CFTC_COT_legacy_btc_w.parquet
  -> data/CFTC_COT_tffcomb_btc_w.parquet   (futures + delta-adjusted options)
"""
import os
import sys

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "code", "shared"))
sys.path.insert(0, os.path.join(REPO, "code", "fx-majors", "shared"))
from research_lib import DATA_DIR, _atomic_parquet  # noqa: E402
import fetch_cot_fx as fx  # noqa: E402

CODES = {"133741": ("BTC", 5.0), "133742": ("MBT", 0.1)}
TFF_PATH = os.path.join(DATA_DIR, "CFTC_COT_tff_btc_w.parquet")
LEG_PATH = os.path.join(DATA_DIR, "CFTC_COT_legacy_btc_w.parquet")
COMB_PATH = os.path.join(DATA_DIR, "CFTC_COT_tffcomb_btc_w.parquet")   # futures + options (delta)
GROUPS = (("dealer", "Dealer"), ("am", "Asset_Mgr"), ("lev", "Lev_Money"),
          ("oth", "Other_Rept"), ("nonrep", "NonRept"))


def _parse_tff(fname):
    d = fx._zip_csv(fname)
    d.columns = [c.strip() for c in d.columns]
    d["code"] = d["CFTC_Contract_Market_Code"].str.strip()
    d = d[d["code"].isin(CODES)]
    f = pd.DataFrame({"date": pd.to_datetime(d["Report_Date_as_YYYY-MM-DD"]),
                      "contract": d["code"].map(lambda c: CODES[c][0]),
                      "name": d["Market_and_Exchange_Names"].str.strip(),
                      "oi": d["Open_Interest_All"].astype(float)})
    for grp, col in GROUPS:
        f[f"{grp}_long"] = d[f"{col}_Positions_Long_All"].astype(float)
        f[f"{grp}_short"] = d[f"{col}_Positions_Short_All"].astype(float)
        sp = f"{col}_Positions_Spread_All"
        if sp in d:
            f[f"{grp}_spread"] = pd.to_numeric(d[sp], errors="coerce")
    for grp, col in (("am", "Asset_Mgr"), ("lev", "Lev_Money")):
        for side in ("Long", "Short"):
            c = f"Traders_{col}_{side}_All"
            if c in d:
                f[f"{grp}_n{side.lower()}"] = pd.to_numeric(d[c], errors="coerce")
    return f


def _parse_legacy(fname):
    d = fx._zip_csv(fname)
    d.columns = [c.strip() for c in d.columns]
    d["code"] = d["CFTC Contract Market Code"].str.strip()
    d = d[d["code"].isin(CODES)]
    return pd.DataFrame({
        "date": pd.to_datetime(d["As of Date in Form YYYY-MM-DD"]),
        "contract": d["code"].map(lambda c: CODES[c][0]),
        "name": d["Market and Exchange Names"].str.strip(),
        "oi": d["Open Interest (All)"].astype(float),
        "nc_long": d["Noncommercial Positions-Long (All)"].astype(float),
        "nc_short": d["Noncommercial Positions-Short (All)"].astype(float),
        "nc_spread": d["Noncommercial Positions-Spreading (All)"].astype(float),
        "c_long": d["Commercial Positions-Long (All)"].astype(float),
        "c_short": d["Commercial Positions-Short (All)"].astype(float),
        "nr_long": d["Nonreportable Positions-Long (All)"].astype(float),
        "nr_short": d["Nonreportable Positions-Short (All)"].astype(float)})


def _finish(frames, path):
    df = pd.concat(frames).drop_duplicates(["date", "contract"], keep="last")
    df = df.sort_values(["contract", "date"]).reset_index(drop=True)
    df["btc_per_contract"] = df["contract"].map({v[0]: v[1] for v in CODES.values()})
    df["avail_utc"] = fx._avail(df["date"]).values
    _atomic_parquet(df, path)
    return df


def fetch_tff(refresh=False):
    if os.path.exists(TFF_PATH) and not refresh:
        return pd.read_parquet(TFF_PATH)
    last = pd.Timestamp.today().year
    return _finish([_parse_tff(f"fut_fin_txt_{y}.zip") for y in range(2017, last + 1)], TFF_PATH)


def fetch_tff_combined(refresh=False):
    """TFF futures-and-options-combined report (options delta-adjusted). Options
    positions of a group = combined - futures-only."""
    if os.path.exists(COMB_PATH) and not refresh:
        return pd.read_parquet(COMB_PATH)
    last = pd.Timestamp.today().year
    return _finish([_parse_tff(f"com_fin_txt_{y}.zip") for y in range(2017, last + 1)], COMB_PATH)


def fetch_legacy(refresh=False):
    if os.path.exists(LEG_PATH) and not refresh:
        return pd.read_parquet(LEG_PATH)
    last = pd.Timestamp.today().year
    return _finish([_parse_legacy(f"deacot{y}.zip") for y in range(2017, last + 1)], LEG_PATH)


def refresh_current_year():
    """Weekly live update: re-download only this year's files and merge."""
    y = pd.Timestamp.today().year
    old = fetch_tff()
    _finish([old[old["date"].dt.year < y].drop(columns=["avail_utc", "btc_per_contract"]),
             _parse_tff(f"fut_fin_txt_{y}.zip")], TFF_PATH)
    old = fetch_legacy()
    _finish([old[old["date"].dt.year < y].drop(columns=["avail_utc", "btc_per_contract"]),
             _parse_legacy(f"deacot{y}.zip")], LEG_PATH)


def combined_btc(df, cols):
    """Sum standard + micro contracts in BTC units, indexed by report as-of date."""
    x = df[cols].mul(df["btc_per_contract"], axis=0)
    x["date"] = df["date"]
    return x.groupby("date").sum()


def report_avail(df):
    """Series: report as-of date -> first moment it is public (UTC)."""
    return df.groupby("date")["avail_utc"].max()


def on_daily_rows(weekly, idx, avail):
    """Row stamped D (a daily bar whose decision is made at D's close = D+1 00:00 UTC)
    takes the latest report whose avail_utc is strictly before D+1 00:00 UTC, i.e. known
    at the time the weight is set. Backlogs resolve to the newest report in the batch."""
    a = avail.reindex(weekly.index).dropna().sort_values()
    known = pd.Series(a.index, index=a.values).cummax()
    known = known[~known.index.duplicated(keep="last")]
    known.index = known.index + pd.Timedelta(microseconds=1)
    decision = idx + pd.Timedelta(days=1)                     # close of bar D
    kd = known.reindex(known.index.union(decision)).ffill().reindex(decision)
    out = weekly.reindex(kd.values)
    out.index = idx
    return out


if __name__ == "__main__":
    t = fetch_tff(refresh=True)
    print(t.groupby("contract").agg(first=("date", "min"), last=("date", "max"),
                                    n=("date", "size"), name=("name", "last")))
    cb = fetch_tff_combined(refresh=True)
    print(cb.groupby("contract").agg(first=("date", "min"), last=("date", "max"), n=("date", "size")))
    lg = fetch_legacy(refresh=True)
    print(lg.groupby("contract").agg(first=("date", "min"), last=("date", "max"),
                                     n=("date", "size"), name=("name", "last")))
