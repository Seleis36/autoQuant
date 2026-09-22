"""Daily, never-revised FRED series -> data/FRED_<ID>_d.parquet.

These are all daily market quotes (constant-maturity Treasury yields, effective fed
funds, BofA OAS indices). None of them is revised, so a vintage store is unnecessary
-- but the OAS indices are *published T+1*, so every consumer must lag them one bar.
"""
import io, os, sys, urllib.request
import pandas as pd

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
DATA = os.path.join(_ROOT, "data")
SERIES = ["DGS3MO", "DGS1", "DGS2", "DGS5", "DGS10", "DGS20", "DGS30",
          "DFF", "BAMLH0A0HYM2", "BAMLC0A0CM"]


def fred(sid, force=False):
    path = os.path.join(DATA, f"FRED_{sid}_d.parquet")
    if os.path.exists(path) and not force:
        s = pd.read_parquet(path)[sid]
        s.index = pd.to_datetime(s.index)
        return s
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    raw = urllib.request.urlopen(url, timeout=60).read().decode()
    df = pd.read_csv(io.StringIO(raw))
    df.columns = ["date", sid]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df[sid] = pd.to_numeric(df[sid], errors="coerce")
    df = df.dropna()
    tmp = f"{path}.{os.getpid()}.tmp"
    df.to_parquet(tmp); os.replace(tmp, path)
    return df[sid]


if __name__ == "__main__":
    force = "--force" in sys.argv
    for s in SERIES:
        x = fred(s, force=force)
        print(f"{s:14s} {x.index.min().date()} -> {x.index.max().date()}  n={len(x)}")
