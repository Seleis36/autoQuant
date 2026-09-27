"""Year-over-year textual similarity of 10-K / 10-Q filings ("Lazy Prices", Cohen-Malloy-Nguyen
2020) for the S&P 500 panel, straight from EDGAR.

    python code/us-large-cap/shared/fetch_filing_text.py [--workers 10] [--tickers AAPL,MSFT]
    python code/us-large-cap/shared/fetch_filing_text.py --update --workers 10   # live: new filings only

For every 10-K/10-Q (2008+) of every panel issuer (current CIK + holdco predecessors) the primary
document is downloaded, stripped to lowercase alphabetic tokens, and compared with the SAME form
for the period one year earlier (10-Q Q2-2015 vs Q2-2014; 10-K vs prior 10-K). Nothing but the
similarity metrics is kept -- raw documents are ~2 MB each and are discarded.

Output: data/SP500_filing_similarity.parquet, one row per filing:
    ticker cik form accn filing_date acceptance report_date n_words
    cos (term-frequency cosine vs prior-year doc)   cos_log (same on 1+log tf)   jac (Jaccard on word sets)
    len_ratio (log words / prior words)   prev_accn
`acceptance` is the EDGAR acceptance timestamp (ET): a filing accepted after 16:00 is only
tradeable at the NEXT close. Per-ticker results are checkpointed in $AQ_FILING_TMP so a rerun
resumes where it stopped.
"""
import os, sys, re, json, time, math, argparse, threading, urllib.request, html
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
sys.path.insert(0, HERE)
from research_lib import DATA_DIR, _atomic_parquet, daily_cache_path
from fetch_xbrl import cik_map, PREDECESSORS, UA
from universe import all_tickers_since

TMP = os.environ.get("AQ_FILING_TMP", "/tmp/filing_sim")
OUT = os.path.join(DATA_DIR, "SP500_filing_similarity.parquet")
FORMS = {"10-K", "10-Q", "10-K405", "10-KT"}
_lock = threading.Lock(); _last = [0.0]
PACE = 0.125          # seconds between requests per process; main() sets it to workers/8


def _fetch(url, tries=5):
    for a in range(tries):
        with _lock:                                  # global pacing: <= ~8 requests/s
            wait = PACE - (time.time() - _last[0])
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(3 * (a + 1))
        except Exception:
            time.sleep(3 * (a + 1))
    return None


def filings(cik):
    d = json.loads(_fetch(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    blocks = [d["filings"]["recent"]]
    for f in d["filings"].get("files", []):
        blocks.append(json.loads(_fetch("https://data.sec.gov/submissions/" + f["name"])))
    rows = []
    for b in blocks:
        for i, form in enumerate(b["form"]):
            if form in FORMS and b["filingDate"][i] >= "2008-01-01" and b["primaryDocument"][i]:
                rows.append({"cik": cik, "form": "10-K" if form != "10-Q" else "10-Q",
                             "accn": b["accessionNumber"][i], "filing_date": b["filingDate"][i],
                             "acceptance": b["acceptanceDateTime"][i], "report_date": b["reportDate"][i],
                             "doc": b["primaryDocument"][i]})
    return rows


_TAG = re.compile(r"<[^>]+>")
_HIDDEN = re.compile(r"<ix:header>.*?</ix:header>|<script.*?</script>|<style.*?</style>", re.S | re.I)
_WORD = re.compile(r"[a-z]{2,}")


def tokens(raw):
    t = raw.decode("utf8", "ignore") if isinstance(raw, bytes) else raw
    t = _HIDDEN.sub(" ", t)
    t = html.unescape(_TAG.sub(" ", t)).lower()
    return Counter(_WORD.findall(t))


def cosine(a, b):
    if not a or not b:
        return float("nan")
    small, big = (a, b) if len(a) < len(b) else (b, a)
    dot = sum(v * big.get(k, 0) for k, v in small.items())
    na = math.sqrt(sum(v * v for v in a.values())); nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb)


def cosine_log(a, b):
    """Cosine on 1+log(tf): damps the stop words that push plain TF cosine to ~0.99."""
    la = {k: 1 + math.log(v) for k, v in a.items()}; lb = {k: 1 + math.log(v) for k, v in b.items()}
    return cosine(la, lb)


def jaccard(a, b):
    sa, sb = set(a), set(b)
    return len(sa & sb) / max(1, len(sa | sb))


def _index(t, ciks):
    rows = []
    for c in ciks:
        try:
            rows += filings(c)
        except Exception as e:
            print("index fail", t, c, e, flush=True)
    if not rows:
        return None
    F = pd.DataFrame(rows).drop_duplicates("accn").sort_values(["filing_date"])
    F["report_date"] = pd.to_datetime(F.report_date, errors="coerce")
    F = F.dropna(subset=["report_date"])
    return F.drop_duplicates(["form", "report_date"], keep="first")


def _doc_tokens(r):
    raw = _fetch(f"https://www.sec.gov/Archives/edgar/data/{r.cik}/{r.accn.replace('-', '')}/{r.doc}")
    return None if raw is None else tokens(raw)


def update_ticker(t, ciks):
    """Incremental: compute metrics only for filings not yet in the checkpoint (downloads the new
    filing and its prior-year counterpart). Used live; a full rebuild is `do_ticker`."""
    path = os.path.join(TMP, f"{t}.parquet")
    old = pd.read_parquet(path) if os.path.exists(path) else pd.DataFrame()
    F = _index(t, ciks)
    if F is None:
        return old if len(old) else None
    have = set(old.accn) if len(old) else set()
    new = F[~F.accn.isin(have)]
    out = []
    for _, r in new.iterrows():
        tok = _doc_tokens(r)
        if tok is None:
            continue
        n = sum(tok.values())
        rec = {"ticker": t, "cik": r.cik, "form": r.form, "accn": r.accn, "filing_date": r.filing_date,
               "acceptance": r.acceptance, "report_date": r.report_date, "n_words": n,
               "cos": float("nan"), "cos_log": float("nan"), "jac": float("nan"), "len_ratio": float("nan"), "prev_accn": None}
        pr = F[(F.form == r.form) & ((r.report_date - F.report_date).dt.days.sub(365).abs() <= 20)]
        if len(pr) and n > 1000:
            ptok = _doc_tokens(pr.iloc[-1])
            if ptok:
                rec.update(cos=cosine(tok, ptok), cos_log=cosine_log(tok, ptok), jac=jaccard(tok, ptok),
                           len_ratio=math.log(max(n, 1) / max(sum(ptok.values()), 1)), prev_accn=pr.iloc[-1].accn)
        out.append(rec)
    df = pd.concat([old, pd.DataFrame(out)], ignore_index=True) if out else old
    if out:
        df.to_parquet(path)
        print(t, "+", len(out), "new filings", flush=True)
    return df


def do_ticker(t, ciks):
    path = os.path.join(TMP, f"{t}.parquet")
    if os.path.exists(path):
        return pd.read_parquet(path)
    rows = []
    for c in ciks:
        try:
            rows += filings(c)
        except Exception as e:
            print("index fail", t, c, e, flush=True)
    if not rows:
        pd.DataFrame().to_parquet(path); return None
    F = pd.DataFrame(rows).drop_duplicates("accn").sort_values(["filing_date"])
    F["report_date"] = pd.to_datetime(F.report_date, errors="coerce")
    F = F.dropna(subset=["report_date"])
    # amended/late duplicates: keep the first filing per (form, report_date)
    F = F.drop_duplicates(["form", "report_date"], keep="first")
    cache = {}                                      # (form, report_date) -> (accn, Counter)
    out = []
    for _, r in F.iterrows():
        raw = _fetch(f"https://www.sec.gov/Archives/edgar/data/{r.cik}/{r.accn.replace('-', '')}/{r.doc}")
        if raw is None:
            continue
        tok = tokens(raw)
        n = sum(tok.values())
        prev = None
        for (fm, rd), v in cache.items():
            if fm == r.form and abs((r.report_date - rd).days - 365) <= 20:
                prev = v
        rec = {"ticker": t, "cik": r.cik, "form": r.form, "accn": r.accn, "filing_date": r.filing_date,
               "acceptance": r.acceptance, "report_date": r.report_date, "n_words": n,
               "cos": float("nan"), "cos_log": float("nan"), "jac": float("nan"), "len_ratio": float("nan"), "prev_accn": None}
        if prev is not None and n > 1000:
            pa, ptok = prev
            rec.update(cos=cosine(tok, ptok), cos_log=cosine_log(tok, ptok), jac=jaccard(tok, ptok),
                       len_ratio=math.log(max(n, 1) / max(sum(ptok.values()), 1)), prev_accn=pa)
        out.append(rec)
        cache[(r.form, r.report_date)] = (r.accn, tok)
        # keep only the last ~6 filings in memory
        if len(cache) > 6:
            cache.pop(next(iter(cache)))
    df = pd.DataFrame(out)
    df.to_parquet(path)
    print(t, len(df), "filings", flush=True)
    return df


def _job(args):
    global PACE
    t, ciks, PACE, upd = args
    return update_ticker(t, ciks) if upd else do_ticker(t, ciks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--tickers", default="")
    ap.add_argument("--update", action="store_true", help="live: add filings missing from the checkpoints")
    a = ap.parse_args()
    os.makedirs(TMP, exist_ok=True)
    m = cik_map()
    from xbrl import RECYCLED
    tickers = [t for t in all_tickers_since("2010-01-01")
               if t in m and t not in RECYCLED and os.path.exists(daily_cache_path(t))]
    if a.tickers:
        tickers = a.tickers.split(",")
    jobs = [(t, PREDECESSORS.get(t, []) + [m[t]], a.workers / 8.0, a.update) for t in tickers]
    # tokenising multi-MB inline-XBRL documents is CPU-bound: processes, not threads; the
    # per-process pacing keeps the total under SEC's 10 requests/s
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(_job, jobs))
    df = pd.concat([r for r in res if r is not None and len(r)], ignore_index=True)
    df["filing_date"] = pd.to_datetime(df.filing_date)
    df["report_date"] = pd.to_datetime(df.report_date)
    df["acceptance"] = pd.to_datetime(df.acceptance.astype(str).str.slice(0, 19), errors="coerce")
    if not a.tickers:
        _atomic_parquet(df, OUT)
    print(df.shape, df.ticker.nunique(), "tickers ->", OUT if not a.tickers else "(subset, not saved)")


if __name__ == "__main__":
    main()
