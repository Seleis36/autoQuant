"""Full Treasury note/bond auction RESULTS from TreasuryDirect -> data/UST_auctions.parquet.

One row per auction (nominal notes/bonds and TIPS), with the demand metrics published at the
close of bidding (13:00 ET; `updatedTimestamp` is ~13:01-13:05):
  high_yield, median_yield (averageMedianYield), low_yield, bid_to_cover,
  competitive_accepted, primary_dealer_accepted, direct_accepted, indirect_accepted,
  offering_amt, soma_accepted, reopening, tips.
Investor-class allocations (dealer / direct / indirect) are populated from 2003.
Everything is knowable at the auction-day close (results ~3 hours before the 16:00 close).
"""
import json
import os
import sys
import time
import urllib.request

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "code", "shared"))
from research_lib import DATA_DIR, _atomic_parquet  # noqa: E402

PATH = os.path.join(DATA_DIR, "UST_auctions.parquet")
URL = ("https://www.treasurydirect.gov/TA_WS/securities/search?format=json"
       "&type={typ}&dateFieldName=auctionDate&startDate={a}&endDate={b}")
UA = {"User-Agent": "Mozilla/5.0 autoquant-research/1.0"}
NUM = {"highYield": "high_yield", "averageMedianYield": "median_yield", "lowYield": "low_yield",
       "bidToCoverRatio": "bid_to_cover", "competitiveAccepted": "competitive_accepted",
       "competitiveTendered": "competitive_tendered",
       "primaryDealerAccepted": "primary_dealer_accepted", "directBidderAccepted": "direct_accepted",
       "indirectBidderAccepted": "indirect_accepted", "offeringAmount": "offering_amt",
       "somaAccepted": "soma_accepted", "totalAccepted": "total_accepted",
       "allocationPercentage": "alloc_pct_at_high"}


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def tenor_of(term, tips):
    import re
    m = re.match(r"(\d+)-Year", term or "")
    if not m:
        return None
    y = int(m.group(1)) + (1 if "Month" in term else 0)
    return ("tips" if tips else "") + str(y) + "y"


def fetch(start_year=1990, refresh=False):
    if os.path.exists(PATH) and not refresh:
        return pd.read_parquet(PATH)
    rows = []
    for typ in ("Note", "Bond", "TIPS"):
        for y in range(start_year, pd.Timestamp.today().year + 1):
            for x in _get(URL.format(typ=typ, a=f"01/01/{y}", b=f"12/31/{y}")):
                r = {"auction_date": x["auctionDate"][:10], "issue_date": x["issueDate"][:10],
                     "announcement_date": (x.get("announcementDate") or "")[:10],
                     "type": x.get("securityType"), "term": x.get("securityTerm"),
                     "cusip": x.get("cusip"), "reopening": x.get("reopening") == "Yes",
                     "tips": x.get("tips") == "Yes", "updated": x.get("updatedTimestamp")}
                for k, v in NUM.items():
                    try:
                        r[v] = float(x.get(k)) if x.get(k) not in ("", None) else float("nan")
                    except ValueError:
                        r[v] = float("nan")
                rows.append(r)
            time.sleep(0.2)
    df = pd.DataFrame(rows).drop_duplicates(["auction_date", "cusip"])
    for c in ("auction_date", "issue_date", "announcement_date"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["tenor"] = [tenor_of(t, tp) for t, tp in zip(df.term, df.tips)]
    df = df.sort_values("auction_date").reset_index(drop=True)
    _atomic_parquet(df, PATH)
    return df


if __name__ == "__main__":
    d = fetch(refresh=True)
    print(d.groupby("tenor").agg(n=("auction_date", "size"), first=("auction_date", "min"),
                                 last=("auction_date", "max"),
                                 pd_first=("primary_dealer_accepted", lambda s: d.loc[s.dropna().index, "auction_date"].min())))
