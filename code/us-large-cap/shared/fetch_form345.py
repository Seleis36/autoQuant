"""Open-market insider trades (Form 4, codes P/S) in S&P 500 panel names, from the SEC
"Insider Transactions Data Sets" (quarterly zips, 2006+).

    python code/us-large-cap/shared/fetch_form345.py

Output: data/SP500_insider_trades.parquet, one row per non-derivative transaction:
    ticker issuer_cik accn filing_date trans_date owner_cik owner_name relationship title
    code shares price acq_disp shares_after direct form
`filing_date` is the EDGAR acceptance date -- the first day the trade was public (insiders
have two business days to file since Aug-2002). Trade on it, never on `trans_date`.
Issuer CIKs come from fetch_xbrl.cik_map() plus the holdco predecessors.
"""
import os, sys, re, io, time, zipfile, urllib.request
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
sys.path.insert(0, HERE)
from research_lib import DATA_DIR, _atomic_parquet, daily_cache_path
from fetch_xbrl import cik_map, PREDECESSORS, UA
from universe import all_tickers_since

RAW = os.environ.get("AQ_FORM345_RAW", "/tmp/form345")
OUT = os.path.join(DATA_DIR, "SP500_insider_trades.parquet")
INDEX = "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets"


def zip_urls():
    with urllib.request.urlopen(urllib.request.Request(INDEX, headers=UA), timeout=60) as r:
        html = r.read().decode("utf8", "ignore")
    return sorted(set("https://www.sec.gov" + h for h in re.findall(r'href="(/files/[^"]*form345\.zip)"', html)))


def get(url):
    os.makedirs(RAW, exist_ok=True)
    p = os.path.join(RAW, url.rsplit("/", 1)[1])
    if not os.path.exists(p):
        for a in range(5):
            try:
                time.sleep(0.3)
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                    data = r.read()
                open(p + ".tmp", "wb").write(data); os.replace(p + ".tmp", p)
                break
            except Exception as e:
                print("retry", url, e); time.sleep(5 * (a + 1))
    return p


def parse(path, cik2tick):
    z = zipfile.ZipFile(path)
    rd = lambda n, cols: pd.read_csv(z.open(n), sep="\t", usecols=cols, dtype=str, quoting=3, on_bad_lines="skip")
    sub = rd("SUBMISSION.tsv", ["ACCESSION_NUMBER", "FILING_DATE", "ISSUERCIK", "DOCUMENT_TYPE"])
    sub["cik"] = pd.to_numeric(sub.ISSUERCIK, errors="coerce")
    sub = sub[sub.cik.isin(cik2tick.keys())]
    tr = rd("NONDERIV_TRANS.tsv", ["ACCESSION_NUMBER", "TRANS_DATE", "TRANS_CODE", "TRANS_SHARES",
                                   "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD", "SHRS_OWND_FOLWNG_TRANS",
                                   "DIRECT_INDIRECT_OWNERSHIP"])
    tr = tr[tr.TRANS_CODE.isin(["P", "S"])]
    own = rd("REPORTINGOWNER.tsv", ["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME", "RPTOWNER_RELATIONSHIP", "RPTOWNER_TITLE"])
    own = own.drop_duplicates("ACCESSION_NUMBER")      # joint filings: keep the first owner
    d = tr.merge(sub, on="ACCESSION_NUMBER").merge(own, on="ACCESSION_NUMBER", how="left")
    if not len(d):
        return None
    out = pd.DataFrame({
        "issuer_cik": d.cik.astype(int), "accn": d.ACCESSION_NUMBER,
        "filing_date": pd.to_datetime(d.FILING_DATE, format="%d-%b-%Y", errors="coerce"),
        "trans_date": pd.to_datetime(d.TRANS_DATE, format="%d-%b-%Y", errors="coerce"),
        "owner_cik": pd.to_numeric(d.RPTOWNERCIK, errors="coerce"), "owner_name": d.RPTOWNERNAME,
        "relationship": d.RPTOWNER_RELATIONSHIP, "title": d.RPTOWNER_TITLE, "code": d.TRANS_CODE,
        "shares": pd.to_numeric(d.TRANS_SHARES, errors="coerce"),
        "price": pd.to_numeric(d.TRANS_PRICEPERSHARE, errors="coerce"),
        "acq_disp": d.TRANS_ACQUIRED_DISP_CD,
        "shares_after": pd.to_numeric(d.SHRS_OWND_FOLWNG_TRANS, errors="coerce"),
        "direct": d.DIRECT_INDIRECT_OWNERSHIP, "form": d.DOCUMENT_TYPE,
    })
    out["tickers"] = out.issuer_cik.map(cik2tick)
    return out


def main():
    m = cik_map()
    tickers = [t for t in all_tickers_since("2010-01-01") if t in m and os.path.exists(daily_cache_path(t))]
    cik2tick = {}
    for t in tickers:
        for c in PREDECESSORS.get(t, []) + [m[t]]:
            cik2tick.setdefault(c, []).append(t)
    cik2tick = {c: ",".join(sorted(set(v))) for c, v in cik2tick.items()}
    urls = [u for u in zip_urls() if int(re.search(r"(\d{4})q", u).group(1)) >= 2006]
    print(len(urls), "quarterly zips")
    frames = []
    for u in urls:
        d = parse(get(u), cik2tick)
        if d is not None:
            frames.append(d)
        print(u.rsplit("/", 1)[1], 0 if d is None else len(d), flush=True)
    df = pd.concat(frames, ignore_index=True)
    # one row per ticker (GOOG/GOOGL, FOX/FOXA share an issuer)
    df = df.assign(ticker=df.tickers.str.split(",")).explode("ticker").drop(columns="tickers")
    df = df.drop_duplicates(["ticker", "accn", "trans_date", "code", "shares", "price", "owner_cik"])
    _atomic_parquet(df, OUT)
    print(df.shape, df.ticker.nunique(), "tickers ->", OUT)


if __name__ == "__main__":
    main()
