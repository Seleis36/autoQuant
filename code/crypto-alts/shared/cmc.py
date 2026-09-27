"""CoinMarketCap historical listing snapshots (keyless `data-api/v3`, the endpoint behind
coinmarketcap.com/historical/). One snapshot per week (Sundays), top `limit` coins by market cap,
INCLUDING coins that later died -- a survivorship-free weekly panel with supply fields.

Cache: data/CMC_listings_weekly.parquet, long format, one row per (date, id):
    date, id, symbol, slug, name, cmcRank, circulatingSupply, totalSupply, maxSupply,
    dateAdded, price, marketCap, volume24h, tags

Timing: the snapshot stamped D carries quotes stamped D 00:00 and supplies last updated late on
D. Treat it as known at the close of D+1 (`known_lag_days=1`) before using it as a signal.
Supply figures are what CMC displayed at the time (methodology changes show up as jumps).
"""
import json, os, sys, time, urllib.request
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(_HERE)), "shared"))
from research_lib import DATA_DIR, _atomic_parquet  # noqa: E402

URL = ("https://api.coinmarketcap.com/data-api/v3/cryptocurrency/listings/historical"
       "?date={date}&limit={limit}&start=1&convertId=2781")
PATH = os.path.join(DATA_DIR, "CMC_listings_weekly.parquet")
UA = {"User-Agent": "Mozilla/5.0 autoquant-research", "accept": "application/json"}


def _get(url, tries=6):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception:  # noqa: BLE001
            time.sleep(3 * (a + 1))
    raise RuntimeError(url)


def snapshot(date, limit=300):
    js = _get(URL.format(date=pd.Timestamp(date).strftime("%Y-%m-%d"), limit=limit))
    rows = []
    for c in js.get("data", []):
        q = (c.get("quotes") or [{}])[0]
        rows.append(dict(date=pd.Timestamp(date), id=c["id"], symbol=c["symbol"], slug=c.get("slug"),
                         name=c.get("name"), cmcRank=c.get("cmcRank"),
                         circulatingSupply=c.get("circulatingSupply"), totalSupply=c.get("totalSupply"),
                         maxSupply=c.get("maxSupply"), dateAdded=c.get("dateAdded"),
                         price=q.get("price"), marketCap=q.get("marketCap"), volume24h=q.get("volume24h"),
                         tags=",".join(c.get("tags") or [])))
    return pd.DataFrame(rows)


def fetch_weekly(start="2017-01-01", end=None, limit=300, refresh=False, verbose=True):
    have = pd.read_parquet(PATH) if os.path.exists(PATH) and not refresh else pd.DataFrame()
    done = set(have["date"].unique()) if len(have) else set()
    end = pd.Timestamp(end) if end else pd.Timestamp.now("UTC").tz_convert(None).normalize() - pd.Timedelta(days=1)
    dates = pd.date_range(pd.Timestamp(start), end, freq="W-SUN")
    parts, n = [have] if len(have) else [], 0
    for d in dates:
        if d in done:
            continue
        try:
            df = snapshot(d, limit)
        except RuntimeError as e:
            print("fail", d.date(), e, flush=True)
            continue
        parts.append(df); n += 1
        if verbose:
            print(d.date(), len(df), flush=True)
        if n % 25 == 0:
            _atomic_parquet(pd.concat(parts, ignore_index=True), PATH)
        time.sleep(0.4)
    out = pd.concat(parts, ignore_index=True)
    out["dateAdded"] = pd.to_datetime(out["dateAdded"], errors="coerce", utc=True).dt.tz_convert(None)
    for c in ("circulatingSupply", "totalSupply", "maxSupply", "price", "marketCap", "volume24h", "cmcRank"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    _atomic_parquet(out, PATH)
    return out


def load_weekly():
    return pd.read_parquet(PATH)


def yahoo_map(close, snaps=None, min_overlap=8, max_med_err=0.05):
    """Map each yfinance ticker (columns of `close`) to the CMC id whose weekly snapshot price
    tracks it: candidates share the base symbol; pick the id with the smallest median
    |log(price_cmc / close_yahoo)| over overlapping snapshot dates. Returns {ticker: id}."""
    import numpy as np
    snaps = load_weekly() if snaps is None else snaps
    out = {}
    for t in close.columns:
        sym = t.split("-")[0].replace("TON11419", "TON")
        cand = snaps[snaps["symbol"] == sym]
        best, best_err = None, np.inf
        for cid, g in cand.groupby("id"):
            p = g.set_index("date")["price"]
            y = close[t].reindex(p.index)
            ok = p.notna() & y.notna() & (p > 0)
            if ok.sum() < min_overlap:
                continue
            err = np.median(np.abs(np.log(p[ok] / y[ok])))
            if err < best_err:
                best, best_err = cid, err
        if best is not None and best_err < max_med_err:
            out[t] = int(best)
    return out


def wide(field, idmap, snaps=None, index=None, known_lag_days=1):
    """Weekly CMC field for the mapped tickers, re-stamped to the day it is known
    (snapshot date + `known_lag_days`) and forward-filled onto `index` (daily)."""
    snaps = load_weekly() if snaps is None else snaps
    cols = {}
    for t, cid in idmap.items():
        g = snaps[snaps["id"] == cid].set_index("date")[field].sort_index()
        g = g[~g.index.duplicated(keep="last")]
        g.index = g.index + pd.Timedelta(days=known_lag_days)
        cols[t] = g
    df = pd.DataFrame(cols).sort_index()
    if index is not None:
        df = df.reindex(df.index.union(index)).ffill(limit=10).reindex(index)
    return df


if __name__ == "__main__":
    df = fetch_weekly()
    print(df.shape, df["date"].min(), df["date"].max())
