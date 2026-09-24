"""Binance USD-M funding history for a cross-section of coins, from the keyless REST API.

`fetch_funding_rest(sym)` pages `/fapi/v1/fundingRate` (1000 rows/call) from the perp's
listing and writes `data/<SYM>_fundingRate.parquet` with the same schema as the archive
fetcher in `code/shared/fetch_binance_vision.py` (`last_funding_rate`,
`funding_interval_hours`), so both sources are interchangeable. Files that already exist
are only extended, never overwritten with less history.

`daily_funding(syms)` turns settlements into a daily panel indexed by calendar date D that
contains only settlements stamped strictly before D+1 00:00 UTC minus `lag_hours`, i.e.
information available when the yfinance daily bar of D closes.

Yahoo ticker -> Binance perp symbol mapping lives in `PERP_OF`.
"""
import os
import sys
import time
import json
import urllib.request
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
DATA_DIR = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
import research_lib as rl  # noqa: E402

API = "https://fapi.binance.com/fapi/v1/fundingRate"

# yfinance ticker -> Binance USDT-M perp. 1000x contracts quote 1000 coins; the funding
# *rate* is unit-free so the multiplier does not matter.
PERP_OF = {
    "BTC-USD": "BTCUSDT", "ETH-USD": "ETHUSDT", "SOL-USD": "SOLUSDT", "XRP-USD": "XRPUSDT",
    "ADA-USD": "ADAUSDT", "AVAX-USD": "AVAXUSDT", "LINK-USD": "LINKUSDT", "DOT-USD": "DOTUSDT",
    "LTC-USD": "LTCUSDT", "BCH-USD": "BCHUSDT", "XLM-USD": "XLMUSDT", "EOS-USD": "EOSUSDT",
    "TRX-USD": "TRXUSDT", "ETC-USD": "ETCUSDT", "XMR-USD": "XMRUSDT", "NEO-USD": "NEOUSDT",
    "IOTA-USD": "IOTAUSDT", "DASH-USD": "DASHUSDT", "ZEC-USD": "ZECUSDT", "ATOM-USD": "ATOMUSDT",
    "DOGE-USD": "DOGEUSDT", "BNB-USD": "BNBUSDT", "VET-USD": "VETUSDT", "ALGO-USD": "ALGOUSDT",
    "FIL-USD": "FILUSDT", "AAVE-USD": "AAVEUSDT", "XTZ-USD": "XTZUSDT", "NEAR-USD": "NEARUSDT",
    "QTUM-USD": "QTUMUSDT", "OMG-USD": "OMGUSDT", "ICP-USD": "ICPUSDT", "OP-USD": "OPUSDT",
    "SHIB-USD": "1000SHIBUSDT", "HBAR-USD": "HBARUSDT", "THETA-USD": "THETAUSDT",
    "EGLD-USD": "EGLDUSDT", "SAND-USD": "SANDUSDT", "MANA-USD": "MANAUSDT", "AXS-USD": "AXSUSDT",
    "MKR-USD": "MKRUSDT", "SNX-USD": "SNXUSDT", "CRV-USD": "CRVUSDT", "LDO-USD": "LDOUSDT",
    "INJ-USD": "INJUSDT", "RUNE-USD": "RUNEUSDT", "KSM-USD": "KSMUSDT", "WAVES-USD": "WAVESUSDT",
    "ZIL-USD": "ZILUSDT", "ONT-USD": "ONTUSDT", "BAT-USD": "BATUSDT", "ENJ-USD": "ENJUSDT",
    "CHZ-USD": "CHZUSDT", "FLOW-USD": "FLOWUSDT", "KAVA-USD": "KAVAUSDT", "ONE-USD": "ONEUSDT",
    "CAKE-USD": "CAKEUSDT", "TIA-USD": "TIAUSDT", "SEI-USD": "SEIUSDT", "WIF-USD": "WIFUSDT",
    "RENDER-USD": "RENDERUSDT", "FET-USD": "FETUSDT", "BONK-USD": "1000BONKUSDT",
    "XEM-USD": "XEMUSDT", "BSV-USD": "BSVUSDT",
}


def _get_json(url, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def fetch_funding_rest(sym, start="2019-09-01", verbose=False):
    path = os.path.join(DATA_DIR, f"{sym}_fundingRate.parquet")
    old = pd.read_parquet(path) if os.path.exists(path) else None
    t0 = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    rows = []
    while True:
        page = _get_json(f"{API}?symbol={sym}&startTime={t0}&limit=1000")
        if not page:
            break
        rows += page
        last = page[-1]["fundingTime"]
        if len(page) < 1000:
            break
        t0 = last + 1
        time.sleep(0.25)
    if not rows:
        return old
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["fundingTime"], unit="ms").dt.floor("min")
    df = df.set_index("ts")[["fundingRate"]].astype(float)
    df.columns = ["last_funding_rate"]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df["funding_interval_hours"] = (df.index.to_series().diff().dt.total_seconds() / 3600
                                    ).round().fillna(8.0)
    if old is not None:
        old = old.copy()
        old.index = pd.DatetimeIndex(old.index).tz_localize(None).floor("min")
        df = pd.concat([old, df])
        df = df[~df.index.duplicated(keep="first")].sort_index()
    rl._atomic_parquet(df, path)
    if verbose:
        print(f"  {sym}: {len(df)} stamps {df.index[0]} -> {df.index[-1]}", flush=True)
    return df


def load_funding(sym):
    path = os.path.join(DATA_DIR, f"{sym}_fundingRate.parquet")
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
    return df["last_funding_rate"].astype(float)


def daily_funding(tickers, lag_hours=8):
    """Sum of funding settled per calendar day, dated to the day whose close it is known at.

    A settlement at time s is usable at the close of date D (= D+1 00:00 UTC) iff
    s <= D+1 00:00 - lag_hours, i.e. D = ceil_day(s + lag_hours) - 1 day. With lag_hours=8
    the D+1 00:00 settlement is pushed to D+1, so the signal on D uses the stamps
    D 00:00, D 08:00, D 16:00 -- a full 8h safety margin.
    Returns (daily_sum, n_stamps) DataFrames, columns = yfinance tickers.
    """
    out, cnt = {}, {}
    for t in tickers:
        f = load_funding(PERP_OF.get(t, ""))
        if f is None:
            continue
        usable_day = (f.index + pd.Timedelta(hours=lag_hours)).ceil("D") - pd.Timedelta(days=1)
        g = f.groupby(usable_day)
        out[t] = g.sum()
        cnt[t] = g.count()
    return pd.DataFrame(out).sort_index(), pd.DataFrame(cnt).sort_index()


if __name__ == "__main__":
    for t, s in PERP_OF.items():
        try:
            fetch_funding_rest(s, verbose=True)
        except Exception as e:  # noqa: BLE001
            print(f"  {s}: FAILED {e}")


# ------------------------------------------------------------------ premium index (perp vs index basis)

PREMIUM_API = "https://fapi.binance.com/fapi/v1/premiumIndexKlines"


def fetch_premium_rest(sym, interval="4h", start="2019-09-01", verbose=False):
    """Premium-index klines ((mark-ish perp price - spot index) / index), written to
    data/<SYM>_premium_<interval>.parquet. Index = bar OPEN time (UTC)."""
    path = os.path.join(DATA_DIR, f"{sym}_premium_{interval}.parquet")
    t0 = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    rows = []
    while True:
        page = _get_json(f"{PREMIUM_API}?symbol={sym}&interval={interval}&startTime={t0}&limit=1500")
        if not page:
            break
        rows += page
        if len(page) < 1500:
            break
        t0 = page[-1][0] + 1
        time.sleep(0.25)
    if not rows:
        return None
    df = pd.DataFrame([r[:5] for r in rows], columns=["ts", "open", "high", "low", "close"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    df = df.set_index("ts").astype(float)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    rl._atomic_parquet(df, path)
    if verbose:
        print(f"  {sym}: {len(df)} bars {df.index[0]} -> {df.index[-1]}", flush=True)
    return df


def daily_premium(tickers, interval="4h", drop_last_bars=1):
    """Daily mean of the premium-index bar closes, dated to the day whose close it is known at.

    Bars are stamped by open time; a bar opening at o closes at o + interval. The value for
    date D averages the bars that close within (D 00:00, D+1 00:00], minus the last
    `drop_last_bars` of them as a safety margin (default: the D 20:00-24:00 bar is dropped,
    so the latest input closed at D 20:00, four hours before the trade).
    """
    step = pd.Timedelta(interval)
    out = {}
    for t in tickers:
        path = os.path.join(DATA_DIR, f"{PERP_OF.get(t, '')}_premium_{interval}.parquet")
        if not os.path.exists(path):
            continue
        p = pd.read_parquet(path)["close"]
        close_t = p.index + step
        slot = ((close_t - close_t.floor("D")) / step).astype(int)  # 0 => closes at midnight
        day = close_t.floor("D") - pd.Timedelta(days=1)
        day = day.where(slot == 0, close_t.floor("D"))
        slot = pd.Index(slot).where(slot != 0, int(pd.Timedelta("1D") / step))
        keep = slot <= int(pd.Timedelta("1D") / step) - drop_last_bars
        out[t] = pd.Series(p.values[keep], index=day[keep]).groupby(level=0).mean()
    return pd.DataFrame(out).sort_index()
