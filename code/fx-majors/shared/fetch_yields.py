"""Daily government yields for rate-differential work, cached flat as data/YLD_<CCY><TENOR>_d.parquet.

Sources (all free, all end-of-local-day values stamped on their local trading date):
  USD  FRED DGS2 / DGS5                       (~US close)
  EUR  Bundesbank Svensson curve, Bunds 2y/5y (~Frankfurt close)
  JPY  MoF Japan JGB constant-maturity 2Y/5Y  (~Tokyo close); history file + current month
  CAD  Bank of Canada Valet BD.CDN.2YR/5YR    (~Toronto close)
  GBP  Bank of England IADB IUDSNZC (5y nominal zero coupon; no 2y in the IADB)
Not available: AUD (RBA site blocks scripted access), CHF (SNB cube stops 2025-07), NZD.
Every value stamped D is final by 00:00 UTC D+1, i.e. usable for the =X row D+1 weight
under the lag rule in fx_panel.lag_to_fx(lag=1).
"""
import io
import os
import sys
import urllib.request

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "code", "shared"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from research_lib import DATA_DIR, _atomic_parquet  # noqa: E402
from macro_data import fred  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0"}


def _get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()


def _bbk(tenor):
    key = f"BBSIS/D.I.ZST.ZI.EUR.S1311.B.A604.R{tenor:02d}XX.R.A.A._Z._Z.A"
    raw = _get(f"https://api.statistiken.bundesbank.de/rest/data/{key}?format=csv&lang=en")
    d = pd.read_csv(io.BytesIO(raw), skiprows=5, header=None, usecols=[0, 1], names=["date", "v"])
    d = d[pd.to_datetime(d["date"], errors="coerce").notna()]
    s = pd.to_numeric(d["v"], errors="coerce")
    s.index = pd.to_datetime(d["date"])
    return s.dropna()


def _mof(tenor):
    base = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/"
    parts = []
    for url in (base + "historical/jgbcme_all.csv", base + "jgbcme.csv"):
        d = pd.read_csv(io.BytesIO(_get(url)), skiprows=1, encoding="shift_jis")
        d["Date"] = pd.to_datetime(d["Date"], errors="coerce")
        d = d.dropna(subset=["Date"]).set_index("Date")
        parts.append(pd.to_numeric(d[f"{tenor}Y"], errors="coerce"))
    s = pd.concat(parts).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def _boc(tenor):
    raw = _get(f"https://www.bankofcanada.ca/valet/observations/BD.CDN.{tenor}YR.DQ.YLD/csv?start_date=1995-01-01")
    txt = raw.decode()
    body = txt[txt.index('"date"'):]
    d = pd.read_csv(io.StringIO(body))
    s = pd.to_numeric(d.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(d["date"])
    return s.dropna()


def _boe(code):
    raw = _get("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes"
               f"&Datefrom=01/Jan/1998&Dateto=now&SeriesCodes={code}&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")
    d = pd.read_csv(io.BytesIO(raw))
    s = pd.to_numeric(d[code], errors="coerce")
    s.index = pd.to_datetime(d["DATE"], format="%d %b %Y")
    return s.dropna()


SOURCES = {
    "USD2": lambda: fred("DGS2", refresh=True), "USD5": lambda: fred("DGS5", refresh=True),
    "EUR2": lambda: _bbk(2), "EUR5": lambda: _bbk(5),
    "JPY2": lambda: _mof(2), "JPY5": lambda: _mof(5),
    "CAD2": lambda: _boc(2), "CAD5": lambda: _boc(5),
    "GBP5": lambda: _boe("IUDSNZC"),
}


def yields(refresh=False):
    out = {}
    for k, fn in SOURCES.items():
        path = os.path.join(DATA_DIR, f"YLD_{k}_d.parquet")
        if refresh or not os.path.exists(path):
            s = fn().sort_index()
            _atomic_parquet(s.rename(k).to_frame(), path)
        out[k] = pd.read_parquet(path).iloc[:, 0]
    return pd.DataFrame(out).sort_index()


if __name__ == "__main__":
    y = yields(refresh=True)
    print(y.apply(lambda s: pd.Series({"first": s.first_valid_index(), "last": s.last_valid_index(),
                                       "n": s.count()})).T)
    print(y.dropna().tail(3))
