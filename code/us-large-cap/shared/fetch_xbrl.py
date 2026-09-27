"""Point-in-time fundamentals for the S&P 500 panel from SEC EDGAR XBRL `companyfacts`.

    python code/us-large-cap/shared/fetch_xbrl.py            # fetch + extract all panel names
    python code/us-large-cap/shared/fetch_xbrl.py --extract  # re-extract from the raw json cache
    python code/us-large-cap/shared/fetch_xbrl.py --refresh  # live: re-download anything older than 20 h

Output: data/SP500_xbrl_facts.parquet, long format, one row per reported fact:
    ticker cik concept unit start end val form fp fy filed accn
`filed` is the EDGAR filing date -- the first day the number was public. Every fact is kept
(original 10-Q value AND the later 10-K comparative / restatement), so a point-in-time reader
can take the first-filed value per (concept, start, end). See xbrl.py.

CIK mapping: current members from the Wikipedia table (sp500_current_raw.csv, authoritative);
past members from SEC company_tickers.json (current registrants only) -- a past ticker that
now belongs to a different registrant is caught by `xbrl.py`'s membership-window check.
The SEC asks for a descriptive User-Agent and <= 10 requests/s.
"""
import os, sys, json, gzip, time, argparse, urllib.request
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from research_lib import DATA_DIR, _atomic_parquet, daily_cache_path
from universe import all_tickers_since, _yf

UA = {"User-Agent": "autoquant-research/1.0 research-bot"}
RAW = os.environ.get("AQ_XBRL_RAW", "/tmp/sec_companyfacts")
OUT = os.path.join(DATA_DIR, "SP500_xbrl_facts.parquet")

CONCEPTS = {
    # income statement / cash flow (durations)
    "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "SalesRevenueGoodsNet",
    "SalesRevenueServicesNet", "RevenuesNetOfInterestExpense", "InterestAndDividendIncomeOperating",
    "CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices",
    "GrossProfit", "OperatingIncomeLoss", "NetIncomeLoss", "ProfitLoss",
    "NetIncomeLossAvailableToCommonStockholdersBasic",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeTaxExpenseBenefit", "InterestExpense",
    "NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForRepurchaseOfCommonStock",
    "PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "ProceedsFromIssuanceOfCommonStock",
    "ResearchAndDevelopmentExpense", "SellingGeneralAndAdministrativeExpense",
    "DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
    "EarningsPerShareDiluted", "EarningsPerShareBasic",
    "WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic",
    "CommonStockDividendsPerShareDeclared",
    # balance sheet (instants)
    "Assets", "Liabilities", "AssetsCurrent", "LiabilitiesCurrent", "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "CashAndCashEquivalentsAtCarryingValue", "LongTermDebt", "LongTermDebtNoncurrent",
    "LongTermDebtCurrent", "DebtCurrent", "CommonStockSharesOutstanding",
    "RetainedEarningsAccumulatedDeficit", "Goodwill", "IntangibleAssetsNetExcludingGoodwill",
    "InventoryNet", "AccountsReceivableNetCurrent", "PropertyPlantAndEquipmentNet",
    # cover page
    "EntityCommonStockSharesOutstanding", "EntityPublicFloat",
}


# past members whose ticker SEC now attributes to another registrant, pinned by hand
CIK_OVERRIDES = {"PARA": 813828}   # Paramount Global (ex-CBS); PARA was reassigned after Skydance

# holding-company reorganisations: the listed ticker's current CIK only starts at the reorg, the
# history lives under the predecessor registrant (checked via data.sec.gov/submissions names)
PREDECESSORS = {
    "XOM": [34088], "BLK": [1364742], "DIS": [1001039], "CI": [701221], "GOOGL": [1288776],
    "GOOG": [1288776], "MDT": [64670], "AVGO": [1441634, 1649338], "ICE": [1174746], "ETN": [31277],
    "APA": [6769], "XRX": [108772], "FOXA": [1308161], "FOX": [1308161], "DINO": [48039],
    "BKR": [808362], "FTI": [1135152], "DXC": [23082], "VTRS": [69499, 1623613], "PRGO": [820096],
    "NE": [1458891],
}


def cik_map():
    cur = pd.read_csv(os.path.join(HERE, "sp500_current_raw.csv"))
    m = {_yf(s): int(c) for s, c in zip(cur["Symbol"], cur["CIK"])}
    m.update(CIK_OVERRIDES)
    p = os.path.join(RAW, "company_tickers.json")
    if not os.path.exists(p):
        os.makedirs(RAW, exist_ok=True)
        with urllib.request.urlopen(urllib.request.Request(
                "https://www.sec.gov/files/company_tickers.json", headers=UA), timeout=60) as r:
            open(p, "wb").write(r.read())
    sec = {v["ticker"].replace(".", "-"): int(v["cik_str"]) for v in json.load(open(p)).values()}
    for t in all_tickers_since("2010-01-01"):
        if t not in m and t in sec:
            m[t] = sec[t]
    return m


def _get(cik, max_age_h=None):
    """Cached raw JSON path; re-downloaded when older than `max_age_h` hours (None = never)."""
    path = os.path.join(RAW, f"CIK{cik:010d}.json.gz")
    if os.path.exists(path) and (max_age_h is None or time.time() - os.path.getmtime(path) < max_age_h * 3600):
        return path
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    for attempt in range(5):
        try:
            time.sleep(0.15)
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                data = r.read()
            with gzip.open(path + ".tmp", "wb") as f:
                f.write(data)
            os.replace(path + ".tmp", path)
            return path
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None


def extract(ticker, cik, path):
    d = json.load(gzip.open(path))
    rows = []
    for ns in ("us-gaap", "dei"):
        for concept, body in d.get("facts", {}).get(ns, {}).items():
            if concept not in CONCEPTS:
                continue
            for unit, facts in body["units"].items():
                for f in facts:
                    rows.append((ticker, cik, d.get("entityName"), concept, unit, f.get("start"), f["end"],
                                 f["val"], f.get("form"), f.get("fp"), f.get("fy"), f["filed"], f.get("accn")))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="re-download raw JSON older than 20 h (live use)")
    a = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    m = cik_map()
    tickers = [t for t in all_tickers_since("2010-01-01") if t in m and os.path.exists(daily_cache_path(t))]
    print(len(tickers), "priced tickers with a CIK")
    ciks = sorted(set(m[t] for t in tickers) | {c for t in tickers for c in PREDECESSORS.get(t, [])})
    if not a.extract:
        with ThreadPoolExecutor(4) as ex:
            paths = dict(zip(ciks, ex.map(lambda c: _get(c, 20 if a.refresh else None), ciks)))
    else:
        paths = {c: os.path.join(RAW, f"CIK{c:010d}.json.gz") for c in ciks}
    rows = []
    for t in tickers:
        for c in PREDECESSORS.get(t, []) + [m[t]]:
            p = paths.get(c)
            if p and os.path.exists(p):
                rows += extract(t, c, p)
    df = pd.DataFrame(rows, columns=["ticker", "cik", "entity", "concept", "unit", "start", "end", "val",
                                     "form", "fp", "fy", "filed", "accn"])
    for c in ("start", "end", "filed"):
        df[c] = pd.to_datetime(df[c])
    df["val"] = df["val"].astype(float)
    _atomic_parquet(df, OUT)
    print(df.shape, df.ticker.nunique(), "tickers ->", OUT)


if __name__ == "__main__":
    main()
