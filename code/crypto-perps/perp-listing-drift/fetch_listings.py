"""Event data for perp-listing-drift: every Binance USDT-M perpetual's listing date, its first
funding settlements, its daily perp klines, and the Binance spot <BASE>USDT daily klines.

Outputs
  data/BINANCE_PERP_LISTINGS.parquet      one row per perp: symbol, base, spot_base, status,
                                          onboard (exchangeInfo), first_funding (REST),
                                          spot_first (first spot bar), spot_last
  data/BINANCE_<SYM>_PERP_1d.parquet      perp daily klines (fapi), bar-open stamps, UTC
  data/<SYM>_fundingRate.parquet          first <=1000 funding settlements (REST); full
                                          history is kept where a longer file already exists
  data/BINANCE_<BASE>USDT_1d.parquet      spot daily klines (crypto-alts venues.binance_daily)

Delisted perps still listed as SETTLING in exchangeInfo are included; contracts that have
vanished from exchangeInfo altogether cannot be recovered (a bias *against* a short-the-listing
strategy, since those are mostly coins that collapsed).

The fundingRate endpoint is limited to 500 requests / 5 min / IP, hence the pacing.
"""
import json
import os
import urllib.parse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "crypto-alts", "shared"))
from research_lib import DATA_DIR, _atomic_parquet  # noqa: E402
import venues  # noqa: E402

FAPI = "https://fapi.binance.com"
LIST_PATH = os.path.join(DATA_DIR, "BINANCE_PERP_LISTINGS.parquet")
MULT = re.compile(r"^(1000000|100000|10000|1000|1M)(?=[A-Z])")


def spot_base(base):
    return MULT.sub("", base)


def perp_path(sym):
    return os.path.join(DATA_DIR, f"BINANCE_{sym}_PERP_1d.parquet")


def _json(url):
    try:
        return json.loads(venues._get(url, allow_404=True) or b"null")
    except RuntimeError as e:  # e.g. a non-ASCII symbol the endpoint rejects
        print("skip", url, e, flush=True)
        return None


def perp_daily(sym, refresh=False):
    p = perp_path(sym)
    if os.path.exists(p) and not refresh:
        return pd.read_parquet(p)
    out, t = [], int(pd.Timestamp("2019-09-01").timestamp() * 1000)
    while True:
        rows = _json(f"{FAPI}/fapi/v1/klines?symbol={urllib.parse.quote(sym)}&interval=1d&startTime={t}&limit=1500")
        if not rows:
            break
        out += rows
        if len(rows) < 1500:
            break
        t = rows[-1][0] + 86_400_000
    if not out:
        return None
    df = venues._klines_frame(out)
    today = pd.Timestamp.now("UTC").tz_convert(None).normalize()
    df = df[df.index < today]
    _atomic_parquet(df, p)
    return df


def first_funding(sym):
    """First <=1000 settlements. Never shortens an existing longer file."""
    p = os.path.join(DATA_DIR, f"{sym}_fundingRate.parquet")
    if os.path.exists(p):
        return pd.read_parquet(p)
    rows = _json(f"{FAPI}/fapi/v1/fundingRate?symbol={urllib.parse.quote(sym)}&startTime=1&limit=1000")
    time.sleep(0.65)                        # 500 req / 5 min
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["fundingTime"], unit="ms").dt.floor("min")
    df = df.set_index("ts")[["fundingRate"]].astype(float)
    df.columns = ["last_funding_rate"]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df["funding_interval_hours"] = (df.index.to_series().diff().dt.total_seconds() / 3600
                                    ).round().fillna(8.0)
    _atomic_parquet(df, p)
    return df


def build():
    ex = _json(f"{FAPI}/fapi/v1/exchangeInfo")
    s = pd.DataFrame(ex["symbols"])
    s = s[(s.contractType == "PERPETUAL") & (s.quoteAsset == "USDT")].copy()
    s["onboard"] = pd.to_datetime(s.onboardDate, unit="ms")
    s["spot_base"] = s.baseAsset.map(spot_base)
    s = s[["symbol", "baseAsset", "spot_base", "status", "onboard", "underlyingType"]]
    print(len(s), "USDT perps", flush=True)

    # funding (rate-limited, serial)
    ff = {}
    for i, sym in enumerate(s.symbol):
        f = first_funding(sym)
        ff[sym] = f.index.min() if f is not None and len(f) else pd.NaT
        if i % 50 == 0:
            print("funding", i, sym, ff[sym], flush=True)
    s["first_funding"] = s.symbol.map(ff)

    # perp and spot klines (threaded)
    with ThreadPoolExecutor(6) as exr:
        list(exr.map(perp_daily, s.symbol))
    print("perp klines done", flush=True)

    def _spot(b):
        p = venues.binance_path(b)
        stale = (not os.path.exists(p) or
                 pd.read_parquet(p).index.max() < pd.Timestamp.now() - pd.Timedelta(days=5))
        try:
            return b, venues.binance_daily(b, refresh=stale)
        except Exception as e:  # noqa: BLE001
            print("spot fail", b, e, flush=True)
            return b, None
    with ThreadPoolExecutor(6) as exr:
        spots = dict(exr.map(_spot, sorted(set(s.spot_base))))
    s["spot_first"] = s.spot_base.map(lambda b: spots[b].index.min() if spots.get(b) is not None and len(spots[b]) else pd.NaT)
    s["spot_last"] = s.spot_base.map(lambda b: spots[b].index.max() if spots.get(b) is not None and len(spots[b]) else pd.NaT)
    _atomic_parquet(s.reset_index(drop=True), LIST_PATH)
    print(s.describe(include="all").T.to_string(), flush=True)
    return s


if __name__ == "__main__":
    build()
