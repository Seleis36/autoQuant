"""CFTC Disaggregated Futures-Only Commitments of Traders, 2010 -> now, cached flat in data/.

Positions are as of Tuesday; the CFTC publishes them Friday 15:30 ET (Monday or later after
some federal holidays, and weeks late during the Oct-2013 and 2018-19 shutdowns).
`avail_date` is therefore set conservatively: max(report Tuesday + 6 days, CFTC release lag
is not in the file) -- use `cot_panel(..., lag_days=6)` and trade on the close of that day.
"""
import io, os, sys, zipfile, urllib.request
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
from research_lib import DATA_DIR, _atomic_parquet

PATH = os.path.join(DATA_DIR, "CFTC_COT_disagg_w.parquet")
URL = "https://www.cftc.gov/files/dea/history/fut_disagg_txt_{y}.zip"

CODES = {  # commodity -> CFTC contract market code
    "gold": "088691", "silver": "084691", "copper": "085692", "crude": "067651",
    "natgas": "023651", "corn": "002602", "soy": "005602", "wheat": "001602",
}
# (report dates from, to, conservative date by which the backlog was published)
SHUTDOWNS = [("2013-09-30", "2013-11-12", "2013-11-22"),
             ("2018-12-18", "2019-03-05", "2019-03-11"),
             ("2025-09-30", "2025-12-31", "2026-01-15")]

COLS = {"Report_Date_as_YYYY-MM-DD": "date", "CFTC_Contract_Market_Code": "code",
        "Open_Interest_All": "oi", "Prod_Merc_Positions_Long_All": "pm_long",
        "Prod_Merc_Positions_Short_All": "pm_short", "Swap_Positions_Long_All": "sw_long",
        "Swap__Positions_Short_All": "sw_short", "M_Money_Positions_Long_All": "mm_long",
        "M_Money_Positions_Short_All": "mm_short", "NonRept_Positions_Long_All": "nr_long",
        "NonRept_Positions_Short_All": "nr_short"}


def fetch(first=2010, last=None, refresh=False):
    if os.path.exists(PATH) and not refresh:
        return pd.read_parquet(PATH)
    last = last or pd.Timestamp.today().year
    frames = []
    for y in range(first, last + 1):
        req = urllib.request.Request(URL.format(y=y), headers={"User-Agent": "curl/8.5.0"})
        raw = urllib.request.urlopen(req, timeout=60).read()
        z = zipfile.ZipFile(io.BytesIO(raw))
        df = pd.read_csv(z.open(z.namelist()[0]), dtype={"CFTC_Contract_Market_Code": str}, low_memory=False)
        df.columns = [c.strip() for c in df.columns]
        df = df.rename(columns={c: "Report_Date_as_YYYY-MM-DD" for c in df.columns
                                if c.startswith("Report_Date_as")})
        frames.append(df[list(COLS)].rename(columns=COLS))
    df = pd.concat(frames)
    df["code"] = df["code"].str.strip()
    df = df[df["code"].isin(CODES.values())]
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(["date", "code"]).sort_values(["code", "date"]).reset_index(drop=True)
    _atomic_parquet(df, PATH)
    return df


def cot_panel(field_fn, index, lag_days=6):
    """field_fn(df)->Series computed per row; returns date x commodity frame on `index`,
    each report usable from report Tuesday + lag_days (forward-filled)."""
    df = fetch()
    inv = {v: k for k, v in CODES.items()}
    df = df.assign(val=field_fn(df), name=df["code"].map(inv))
    df["avail"] = df["date"] + pd.Timedelta(days=lag_days)
    for lo, hi, avail in SHUTDOWNS:  # publication backlogs: never use a report before its release
        m = df["date"].between(lo, hi)
        df.loc[m, "avail"] = df.loc[m, "avail"].clip(lower=pd.Timestamp(avail))
    p = df.pivot_table(index="avail", columns="name", values="val")
    return p.reindex(p.index.union(index)).ffill().reindex(index)


if __name__ == "__main__":
    d = fetch(refresh=True)
    print(d.groupby("code")["date"].agg(["min", "max", "count"]))
