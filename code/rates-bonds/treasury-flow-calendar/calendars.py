"""Event calendars for the Treasury flow-calendar study.

Every calendar here is *knowable in advance* -- Treasury announces auctions a week
ahead and publishes a tentative schedule quarterly, the Fed publishes FOMC dates a
year ahead, and the BLS publishes CPI / employment release dates a year ahead. None
of these is a revised series, so the only lookahead risk is using a date that was
rescheduled (rare: shutdowns, e.g. Oct-Dec 2025). The snapshots committed alongside
this module are what the research used; `refresh()` re-pulls them.

Sources
-------
* Auctions: TreasuryDirect TA_WS `securities/search` (history) and `securities/upcoming`
  (announced, not yet auctioned). Keyed on `auctionDate`, `securityType`, `securityTerm`.
* FOMC: banana815/financial-info `FOMC_Rate_Decisions_Extended.csv` (statement day of
  each scheduled meeting, 1982-2026-07) plus the Fed's published 2026-2027 calendar.
* CPI / payrolls release dates: the ALFRED vintage-date list for CPIAUCSL / PAYEMS. A
  vintage date on ALFRED *is* the release date of that print.
"""
from __future__ import annotations

import io
import json
import os
import re
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "calendar_snapshots")
UA = {"User-Agent": "Mozilla/5.0 autoquant-research/1.0"}

TD_SEARCH = ("https://www.treasurydirect.gov/TA_WS/securities/search?format=json"
             "&type={typ}&dateFieldName=auctionDate&startDate={a}&endDate={b}")
TD_UPCOMING = "https://www.treasurydirect.gov/TA_WS/securities/upcoming?format=json"
ALFRED_DL = "https://alfred.stlouisfed.org/series/downloaddata?seid={sid}"
FOMC_CSV = ("https://raw.githubusercontent.com/banana815/financial-info/main/"
            "FOMC_Rate_Decisions_Extended.csv")

# Fed calendar as published 2026-09 (statement day of each scheduled meeting).
FOMC_EXTRA = [
    "2026-09-16", "2026-10-28", "2026-12-09",
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09",
    "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-08",
]

# Map TreasuryDirect securityTerm -> tenor bucket. Reopenings show as e.g. "9-Year 11-Month".
def tenor_of(term: str) -> str | None:
    m = re.match(r"(\d+)-Year", term or "")
    if not m:
        return None
    y = int(m.group(1))
    if "Month" in term:      # reopening: 9-Year 11-Month is the 10y, 29-Year 10-Month the 30y
        y += 1
    return {2: "2y", 3: "3y", 5: "5y", 7: "7y", 10: "10y", 20: "20y", 30: "30y"}.get(y)


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


# ----------------------------------------------------------------------- auctions

def fetch_auctions(start_year=2002, end_year=None) -> pd.DataFrame:
    end_year = end_year or (pd.Timestamp.today().year + 1)
    rows = []
    for typ in ("Note", "Bond"):
        for y in range(start_year, end_year + 1):
            blob = _get(TD_SEARCH.format(typ=typ, a=f"01/01/{y}", b=f"12/31/{y}"))
            for x in json.loads(blob):
                rows.append({
                    "auction_date": x["auctionDate"][:10],
                    "issue_date": x["issueDate"][:10],
                    "announcement_date": x["announcementDate"][:10],
                    "type": typ, "term": x["securityTerm"], "cusip": x["cusip"],
                    "reopening": "Month" in x["securityTerm"],
                    "offering_amt": x.get("offeringAmount", ""),
                    "bid_to_cover": x.get("bidToCoverRatio", ""),
                })
    up = json.loads(_get(TD_UPCOMING))
    for x in up:
        if x.get("securityType") not in ("Note", "Bond"):
            continue
        rows.append({
            "auction_date": x["auctionDate"][:10], "issue_date": x["issueDate"][:10],
            "announcement_date": (x.get("announcementDate") or "")[:10],
            "type": x["securityType"], "term": x["securityTerm"], "cusip": x.get("cusip", ""),
            "reopening": "Month" in x["securityTerm"], "offering_amt": x.get("offeringAmount", ""),
            "bid_to_cover": "",
        })
    df = pd.DataFrame(rows).drop_duplicates(["auction_date", "term", "cusip"])
    df["tenor"] = df["term"].map(tenor_of)
    df = df.dropna(subset=["tenor"])
    for c in ("auction_date", "issue_date", "announcement_date"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    return df.sort_values(["auction_date", "tenor"]).reset_index(drop=True)


# --------------------------------------------------------------------------- FOMC

def fetch_fomc() -> pd.Series:
    df = pd.read_csv(io.StringIO(_get(FOMC_CSV)))
    d = pd.to_datetime(df["meeting_date"])
    d = pd.concat([d, pd.Series(pd.to_datetime(FOMC_EXTRA))]).drop_duplicates().sort_values()
    return d.reset_index(drop=True)


# ------------------------------------------------------------------ BLS releases

def fetch_release_dates(series_id: str) -> pd.Series:
    """Every vintage date ALFRED holds for `series_id` == every release date."""
    html = _get(ALFRED_DL.format(sid=series_id))
    m = re.search(r'<select id="form_selected_vintage_dates".*?</select>', html, re.S)
    blob = m.group(0) if m else html
    dates = sorted(set(re.findall(r"(?:19|20)\d\d-\d\d-\d\d", blob)))
    return pd.Series(pd.to_datetime(dates))


# ----------------------------------------------------------------------- snapshots

def refresh():
    os.makedirs(SNAP, exist_ok=True)
    fetch_auctions().to_csv(os.path.join(SNAP, "auctions.csv"), index=False)
    fetch_fomc().to_csv(os.path.join(SNAP, "fomc.csv"), index=False, header=["date"])
    for sid, name in (("CPIAUCSL", "cpi"), ("PAYEMS", "payrolls")):
        fetch_release_dates(sid).to_csv(os.path.join(SNAP, f"{name}.csv"),
                                        index=False, header=["date"])


def load(name: str):
    p = os.path.join(SNAP, f"{name}.csv")
    if name == "auctions":
        df = pd.read_csv(p, parse_dates=["auction_date", "issue_date", "announcement_date"])
        return df
    return pd.to_datetime(pd.read_csv(p)["date"])


if __name__ == "__main__":
    refresh()
    a = load("auctions")
    print(a.groupby("tenor")["auction_date"].agg(["count", "min", "max"]))
    for n in ("fomc", "cpi", "payrolls"):
        s = load(n)
        print(n, len(s), s.min().date(), s.max().date())
