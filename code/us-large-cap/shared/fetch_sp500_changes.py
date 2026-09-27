"""Refresh the S&P 500 constituent and change tables from Wikipedia, and roll the point-in-time
membership file forward.

    python code/us-large-cap/shared/fetch_sp500_changes.py [--out-dir DIR]

Writes (default: this folder):
  sp500_current_raw.csv      today's constituents (Symbol, GICS Sector, ..., CIK)
  sp500_changes_raw.csv      'Selected changes' table (two header rows, as the research read it)
  sp500_ticker_start_end.csv every change dated after the file's last start/end date is applied:
                             an addition opens a span (start_date = effective date), a removal
                             closes the open span (end_date = effective date).
Live use: run daily before the strategies. `index-reconstitution` shorts additions at the close of
their effective session, so a change must be in the table by then (Wikipedia is normally edited
on the announcement day, days ahead of the effective date).
"""
import os, io, sys, argparse, urllib.request
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# the 'Selected changes' table moved off the constituents page in 2026
URL_CHANGES = "https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500"


def _tables(url):
    html = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 autoquant-research/1.0"}),
                                  timeout=60).read().decode("utf8")
    return pd.read_html(io.StringIO(html))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=HERE)
    a = ap.parse_args()
    tabs = _tables(URL) + _tables(URL_CHANGES)
    cur = next(t for t in tabs if "Symbol" in t.columns and "GICS Sector" in t.columns)
    chg = next(t for t in tabs if isinstance(t.columns, pd.MultiIndex) and "Effective Date" in t.columns.get_level_values(0))
    if len(cur) < 480 or len(chg) < 300:
        sys.exit(f"refusing to write: parsed {len(cur)} constituents / {len(chg)} changes")
    os.makedirs(a.out_dir, exist_ok=True)
    cur.to_csv(os.path.join(a.out_dir, "sp500_current_raw.csv"), index=False)
    chg.to_csv(os.path.join(a.out_dir, "sp500_changes_raw.csv"), index=False)

    se = pd.read_csv(os.path.join(HERE, "sp500_ticker_start_end.csv"), parse_dates=["start_date", "end_date"])
    last = max(se.start_date.max(), se.end_date.max())
    c = chg.copy(); c.columns = ["date", "add", "add_name", "rem", "rem_name", "reason", "refs"]
    c["date"] = pd.to_datetime(c.date, errors="coerce")
    c = c[c.date > last].sort_values("date")
    for _, r in c.iterrows():
        if isinstance(r["rem"], str) and r["rem"].strip():
            open_ = (se.ticker == r["rem"].strip()) & se.end_date.isna()
            se.loc[open_, "end_date"] = r.date
        if isinstance(r["add"], str) and r["add"].strip():
            t = r["add"].strip()
            if not ((se.ticker == t) & se.end_date.isna()).any():
                se = pd.concat([se, pd.DataFrame([{"ticker": t, "start_date": r.date, "end_date": pd.NaT}])], ignore_index=True)
    se = se.sort_values(["ticker", "start_date"])
    se.to_csv(os.path.join(a.out_dir, "sp500_ticker_start_end.csv"), index=False, date_format="%Y-%m-%d")
    print(f"{len(cur)} constituents, {len(chg)} changes, {len(c)} applied after {last.date()} -> {a.out_dir}")


if __name__ == "__main__":
    main()
