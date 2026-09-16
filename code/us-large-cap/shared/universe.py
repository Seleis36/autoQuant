"""Point-in-time S&P 500 membership from fja05680/sp500 `sp500_ticker_start_end.csv`
(1996+), cross-checked against Wikipedia's 'Historical components' table.

Tickers are converted to yfinance style ('BRK.B' -> 'BRK-B'). Known renames whose price
history yfinance keeps under the new symbol are aliased so the old membership window
attaches to the surviving series.

    from universe import membership_matrix, all_tickers_since
    M = membership_matrix(dates)          # DataFrame[bool], index=dates, columns=tickers
"""
import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

# old ticker -> yfinance ticker that carries the full history
ALIASES = {
    "FB": "META", "ANTM": "ELV", "FISV": "FI", "RE": "EG", "PKI": "RVTY", "ABC": "COR",
    "WLTW": "WTW", "FBHS": "FBIN", "NLOK": "GEN", "SIVB": "SIVBQ", "FRC": "FRCB",
    "KORS": "CPRI", "MYL": "VTRS", "TSO": "ANDV", "DOW": "DOW", "HRS": "LHX",
    "CTL": "LUMN", "FLIR": "FLIR", "COG": "CTRA", "VAR": "VAR", "PCLN": "BKNG",
    "TWX": "TWX", "ESRX": "ESRX", "XL": "XL", "LB": "BBWI", "WFM": "WFM", "TWC": "TWC",
    "CBS": "PARA", "VIAB": "VIAB", "ADS": "BFH", "KSU": "KSU", "MXIM": "MXIM",
    "XLNX": "XLNX", "CERN": "CERN", "DISCA": "WBD", "DISCK": "DISCK", "CTXS": "CTXS",
    "TWTR": "TWTR", "ATVI": "ATVI", "SPLK": "SPLK", "PXD": "PXD", "WRK": "SW",
    "HFC": "DINO", "INFO": "SPGI", "XEC": "CTRA", "NBL": "CVX", "ETFC": "ETFC",
    "AGN": "AGN", "CELG": "CELG", "RTN": "RTX", "UTX": "RTX", "RHT": "RHT",
    "STI": "STI", "APC": "APC", "LLL": "LHX", "GGP": "GGP", "DPS": "KDP",
    "WYN": "TNL", "WYND": "TNL", "CSRA": "CSRA", "MON": "MON", "AET": "AET",
    "CA": "CA", "TSS": "TSS", "SYMC": "GEN", "CBG": "CBRE", "BRK.B": "BRK-B",
    "BF.B": "BF-B", "PCG": "PCG", "JEC": "J", "AVP": "AVP", "SNI": "SNI",
    "HCP": "DOC", "PEAK": "DOC", "WELL": "WELL", "HCN": "WELL", "FTI": "FTI",
    "DWDP": "DD", "DD": "DD", "ANDV": "ANDV", "GGP": "GGP", "SLG": "SLG", "COL": "COL",
    "NFX": "NFX", "AAL": "AAL", "LUV": "LUV", "ARNC": "HWM", "AA": "AA",
    "BHGE": "BKR", "BHI": "BKR", "DNB": "DNB", "TEG": "WEC", "IR": "TT", "TT": "TT",
    "CXO": "COP", "ALXN": "ALXN", "MXIM": "MXIM", "FLT": "CPAY", "PEAK": "DOC",
    "VNT": "VNT", "OTIS": "OTIS", "CARR": "CARR", "GEHC": "GEHC", "KVUE": "KVUE",
    "CDAY": "DAY", "PKI": "RVTY", "BLL": "BALL", "FLS": "FLS", "AIV": "AIV",
    "NLSN": "NLSN", "CTXS": "CTXS", "DRE": "DRE", "PBCT": "PBCT", "KSU": "KSU",
    "TIF": "TIF", "NBL": "NBL", "ETFC": "ETFC", "COTY": "COTY", "HOG": "HOG",
    "FRC": "FRC", "SBNY": "SBNY", "LUMN": "LUMN", "VFC": "VFC", "DXC": "DXC",
    "NWL": "NWL", "AAP": "AAP", "OGN": "OGN", "LNC": "LNC", "SEE": "SEE",
    "ZION": "ZION", "WHR": "WHR", "CMA": "CMA", "FOXA": "FOXA", "NWSA": "NWSA",
    "FOX": "FOX", "NWS": "NWS", "GOOGL": "GOOGL", "GOOG": "GOOG",
    "PYPL": "PYPL", "SQ": "XYZ", "WBA": "WBA", "MRO": "MRO", "HES": "HES", "K": "K",
    "ALB": "ALB", "ILMN": "ILMN", "DISH": "DISH", "ABMD": "ABMD", "CERN": "CERN",
    "NKTR": "NKTR", "KHC": "KHC", "HSIC": "HSIC", "SWN": "SWN", "AJG": "AJG",
}
_ALIAS = {k: v for k, v in ALIASES.items() if k != v}


def _yf(t: str) -> str:
    t = str(t).strip()
    t = _ALIAS.get(t, t)
    return t.replace(".", "-")


def load_spans() -> pd.DataFrame:
    d = pd.read_csv(os.path.join(HERE, "sp500_ticker_start_end.csv"), parse_dates=["start_date", "end_date"])
    d["ticker"] = d["ticker"].map(_yf)
    return d


def membership_matrix(dates, min_date="2010-01-01") -> pd.DataFrame:
    """bool matrix: was ticker a member at date (start <= date < end)."""
    dates = pd.DatetimeIndex(dates)
    d = load_spans()
    d = d[(d.end_date.isna()) | (d.end_date >= pd.Timestamp(min_date))]
    cols = sorted(d.ticker.unique())
    M = pd.DataFrame(False, index=dates, columns=cols)
    for _, r in d.iterrows():
        end = r.end_date if pd.notna(r.end_date) else pd.Timestamp("2100-01-01")
        M.loc[(dates >= r.start_date) & (dates < end), r.ticker] = True
    return M


def all_tickers_since(min_date="2010-01-01"):
    d = load_spans()
    d = d[(d.end_date.isna()) | (d.end_date >= pd.Timestamp(min_date))]
    return sorted(d.ticker.unique())


def sectors() -> pd.Series:
    """GICS sector for current constituents (Wikipedia snapshot)."""
    cur = pd.read_csv(os.path.join(HERE, "sp500_current_raw.csv"))
    s = pd.Series(cur["GICS Sector"].values, index=cur["Symbol"].map(_yf).values)
    return s[~s.index.duplicated(keep="first")]


if __name__ == "__main__":
    tk = all_tickers_since()
    cur = set(open(os.path.join(HERE, "tickers_current.txt")).read().split())
    hist = [t for t in tk if t not in cur]
    print(len(tk), "tickers since 2010;", len(hist), "not current")
    open(os.path.join(HERE, "tickers_hist.txt"), "w").write("\n".join(hist))
