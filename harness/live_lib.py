"""
Live (paper) execution runtime for autoQuant strategies.

A strategy trades in one of **two books**, and the difference is what each can express
and how strong the evidence it produces is:

* `PaperBroker` -- **Binance SPOT TESTNET** (https://testnet.binance.vision).  Real
  orders against a real order book, but long/flat, unlevered and crypto only.
* `SimBroker` -- a self-contained simulated book.  Any instrument a `QuoteSource` can
  price, long or short, fractional, and backed by no shared account at all.
  `portfolio.SimPortfolioBroker` is the same thing holding a basket.

Both are the same ledger and the same fill model; only the mark price and where the
order goes differ.  That split is the point: paper trading used to *mean* the testnet
account, which capped the desk at four strategies (one shared pool) and at crypto
(one venue's instrument list).  Neither limit applies to a book with no account.

On the testnet, signals are computed from REAL Binance market data (api.binance.com)
and only orders and account state touch the venue: a testnet price series is not the
market the research was backtested on.

A deployed strategy only has to supply a `compute_weight()` callable.  Everything
else -- bar scheduling, closed-bar-only data, order sizing, exchange filters,
journalling, crash recovery, graceful shutdown -- lives here.

Minimal runner:

    from live_lib import PaperBroker, MarketData, StrategyRunner

    md = MarketData()

    def compute_weight(now):
        h = md.klines("BTCUSDT", "1h", limit=500)      # closed bars only
        return 1.0 if h["Close"].iloc[-1] > h["Close"].rolling(50).mean().iloc[-1] else 0.0

    StrategyRunner(
        name="spot-btc/example",
        symbol="BTCUSDT",
        schedule="1h",
        compute_weight=compute_weight,
        broker=PaperBroker("BTCUSDT"),
    ).run()

...and the same thing on an instrument no crypto exchange lists:

    from live_lib import SimBroker

    def compute_weight(now):
        c = md.daily("SPY")["Close"]
        return 1.0 if c.iloc[-1] > c.rolling(200).mean().iloc[-1] else 0.0

    StrategyRunner("us-large-cap/example", "SPY", "1d", compute_weight,
                   broker=SimBroker("SPY", allow_short=False)).run()

Conventions
-----------
* `compute_weight(now)` returns the TARGET weight for the bar that is about to
  start, as a fraction of THIS STRATEGY's equity, in [-1, 1].  It is called just
  after a bar boundary and must only use bars that have already closed.  A venue
  book clamps it to [0, 1]; a simulated one honours a short when built to.
* A market that is not open 24/7 needs no calendar: its `QuoteSource` reports which
  bar the price came from, and the runner acts only when that changes.
* All timestamps are tz-aware UTC.
* Nothing here ever touches a production venue.  `BASE_URL` is the testnet host
  and there is no code path that changes it.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- paths

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HARNESS_DIR)
DATA_DIR = os.path.join(REPO_ROOT, "data")
LIVE_DIR = os.path.join(REPO_ROOT, "live")

BASE_URL = "https://testnet.binance.vision"       # PAPER ORDERS ONLY. Never change.
PUBLIC_URL = "https://api.binance.com"            # real spot klines (unauthenticated)
FUTURES_URL = "https://fapi.binance.com"          # real USDS-M perp klines (unauthenticated)

# Spot-testnet credentials.  Binance runs spot testnet, futures testnet
# (testnet.binancefuture.com) and production as separate account databases: a key
# minted on one does not exist on the others, whatever permissions it was given.
# The spot-specific names are preferred; the generic ones are only a fallback.
SPOT_KEY_ENV = "BINANCE_SPOT_API_KEY_PAPER"
SPOT_SECRET_ENV = "BINANCE_SPOT_SECRET_KEY_PAPER"

log = logging.getLogger("live")


# --------------------------------------------------------------------------- env

def load_env(path: Optional[str] = None) -> dict:
    """Parse the repo `.env` into a dict (does not mutate os.environ beyond fill-in)."""
    path = path or os.path.join(REPO_ROOT, ".env")
    out = {}
    if os.path.exists(path):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip("'\"")
    for k, v in out.items():
        os.environ.setdefault(k, v)
    return out


def _spot_credentials():
    """(key, secret, where-they-came-from) for the spot testnet."""
    load_env()
    k = os.environ.get(SPOT_KEY_ENV, "")
    v = os.environ.get(SPOT_SECRET_ENV, "")
    if k and v:
        return k, v, SPOT_KEY_ENV
    k = os.environ.get("BINANCE_API_KEY_PAPER", "")
    v = os.environ.get("BINANCE_SECRET_KEY_PAPER", "")
    return k, v, "BINANCE_API_KEY_PAPER (fallback)"


# --------------------------------------------------------------------------- http

class BinanceError(RuntimeError):
    def __init__(self, code, msg, status=None):
        super().__init__(f"[{code}] {msg}")
        self.code, self.msg, self.status = code, msg, status


def _request(url: str, headers=None, method="GET", timeout=20, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers or {}, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            try:
                payload = json.loads(body)
                err = BinanceError(payload.get("code"), payload.get("msg", body), e.code)
            except Exception:
                err = BinanceError(e.code, body[:300], e.code)
            # 4xx other than rate limits are deterministic -- do not retry
            if e.code not in (418, 429) and 400 <= e.code < 500:
                raise err
            last = err
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = RuntimeError(f"network error: {e}")
        if attempt < retries - 1:
            time.sleep(2 ** attempt)     # no backoff after the last try -- just raise
    raise last


# --------------------------------------------------------------------------- cache io

#: Earliest bar a *shared* daily cache is always filled back to, whatever the caller
#: asked for. `data/` is read by research as well as by live runners, so a runner that
#: only needs 30 days must not be what decides how much history the next backtest sees.
#: Deliberately the same date as `research_lib.load_series`'s default `start`: while the
#: two disagreed, whichever module reached a ticker first decided how far back everyone
#: else could see it.
DAILY_CACHE_START = "2010-01-01"


def daily_cache_path(ticker: str, data_dir: Optional[str] = None) -> str:
    """The one true filename for a daily series, shared by research and live.

    `research_lib.load_series` mapped `^` to `IDX_` and `live_lib.daily` did not, so
    `^GSPC` was cached twice under two names -- two half-depth copies of one series,
    each refreshed independently. Both call this now, so there is exactly one file.
    """
    stem = ticker.replace("-", "_").replace("^", "IDX_")
    return os.path.join(data_dir or DATA_DIR, f"{stem}_d.parquet")


def _atomic_parquet(df: pd.DataFrame, path: str):
    """Write a parquet cache so a concurrent reader never sees a half-written file.

    `data/` is a cache SHARED by every running strategy, and once more than a handful
    of daemons run at once two of them refreshing the same series overlap routinely.
    A plain `to_parquet` truncates in place, so a reader landing mid-write gets a torn
    file -- which surfaces much later as an unreadable cache or, worse, a short series.
    The temp name carries the pid because the writers are separate processes.
    """
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        df.to_parquet(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# --------------------------------------------------------------------------- market data

# source -> (host, klines path, max limit per request)
_SOURCES = {
    "public":  (PUBLIC_URL, "/api/v3/klines", 1000),    # real Binance spot
    "futures": (FUTURES_URL, "/fapi/v1/klines", 1500),  # real Binance USDS-M perp
    "testnet": (BASE_URL, "/api/v3/klines", 1000),      # SIMULATED -- see warning below
}


class MarketData:
    """Closed-bar market data from real, unauthenticated Binance endpoints.

    **Never compute a signal from `source="testnet"`.**  The testnet runs a simulated
    order book, so its klines are not the market the research was backtested on.
    Measured against real spot it tracks to ~0.01% on average but wanders as far as
    0.2% on a bar, and against the research cache `public` matches to 3e-5.

    The venue's own prices are still the right ones for *sizing* an order, and
    `PaperBroker.mark_price()` reads them from the venue for exactly that.  The
    split is deliberate: real data decides the weight, venue data fills it.

    * `public`  - real Binance spot (default; what the research uses).
    * `futures` - real Binance USDS-M perpetual, for perp-native research.
    * `testnet` - the paper venue. Diagnostics only.
    """

    def __init__(self, source: str = "public"):
        if source not in _SOURCES:
            raise ValueError(f"unknown source {source!r}; use one of {sorted(_SOURCES)}")
        if source == "testnet":
            log.warning("MarketData(source='testnet') returns SIMULATED prices -- "
                        "do not build a signal on it")
        self.source = source

    def _base(self):
        return _SOURCES[self.source][0]

    def _path(self):
        return _SOURCES[self.source][1]

    def _max_limit(self):
        return _SOURCES[self.source][2]

    def klines(self, symbol: str, interval: str, limit: int = 500,
               end_time: Optional[datetime] = None) -> pd.DataFrame:
        """OHLCV indexed by UTC bar-open time.  The still-forming bar is dropped."""
        limit = min(int(limit), self._max_limit())
        q = {"symbol": symbol, "interval": interval, "limit": limit}
        if end_time is not None:
            q["endTime"] = int(end_time.timestamp() * 1000)
        rows = _request(f"{self._base()}{self._path()}?{urllib.parse.urlencode(q)}")
        df = pd.DataFrame(rows, columns=[
            "open_time", "Open", "High", "Low", "Close", "Volume", "close_time",
            "qav", "trades", "tbb", "tbq", "ignore"])
        df.index = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
        now_ms = time.time() * 1000
        closed = pd.to_datetime(rows[-1][6], unit="ms", utc=True) if rows else None
        if closed is not None and closed.timestamp() * 1000 > now_ms:
            df = df.iloc[:-1]          # drop the bar still in progress
        return df

    def history(self, symbol: str, interval: str, bars: int = 10_000,
                cache: bool = True) -> pd.DataFrame:
        """Long OHLCV history, paged past the 1500-bar API limit and cached on disk.

        A signal with a 250-day lookback on hourly bars needs ~9000 bars; refetching
        those every hour is wasteful and fragile, so the series is cached under
        `data/` and only the tail is refreshed on later calls.
        """
        os.makedirs(DATA_DIR, exist_ok=True)
        path = os.path.join(DATA_DIR, f"{symbol}_{interval}_{self.source}_live.parquet")
        df = pd.DataFrame()
        if cache and os.path.exists(path):
            try:
                df = pd.read_parquet(path)
                df.index = pd.to_datetime(df.index, utc=True)
            except Exception as e:  # noqa: BLE001
                log.warning("history cache unreadable (%s), refetching: %s", path, e)
                df = pd.DataFrame()

        step = _INTERVAL_SECONDS.get(interval)
        if step is None:
            raise ValueError(f"unsupported interval {interval!r}")

        guard = 0

        # Phase 1: bring an existing cache up to the present. A single tail fetch is
        # enough only if it OVERLAPS the cache. A daemon that was down for longer than
        # one fetch (1000 bars is 41 days of hourly data) would otherwise have the tail
        # spliced straight onto a stale cache, leaving a hole in the middle that every
        # rolling window then quietly spans -- a signal computed across a gap that is
        # never visible in the output. So keep paging back until the two meet.
        if len(df):
            cached_end = df.index.max()
            end = None
            while guard < 40:
                guard += 1
                chunk = self.klines(symbol, interval, limit=self._max_limit(),
                                    end_time=end)
                if chunk.empty:
                    break
                df = pd.concat([df, chunk])
                if chunk.index[0] <= cached_end + timedelta(seconds=step):
                    break                  # the fetch reaches back into the cache
                new_end = chunk.index[0].to_pydatetime() - timedelta(seconds=step)
                if end is not None and new_end >= end:
                    break                  # not making progress
                end = new_end

        # Phase 2: page backwards until we hold `bars` bars ending at the last closed one.
        end = None
        while guard < 40:
            guard += 1
            have = df[~df.index.duplicated(keep="last")].sort_index()
            if len(have) >= bars and not have.empty:
                break
            chunk = self.klines(symbol, interval, limit=self._max_limit(), end_time=end)
            if chunk.empty:
                break
            df = pd.concat([chunk, df]) if len(df) else chunk
            oldest = chunk.index[0]
            new_end = oldest.to_pydatetime() - timedelta(seconds=step)
            if end is not None and new_end >= end:
                break                      # venue has no deeper history
            end = new_end

        df = df[~df.index.duplicated(keep="last")].sort_index()
        # Say so if a hole survived. Silently returning a gapped series is the failure
        # mode this is here to prevent; a caller that cannot tolerate one can check.
        if len(df) > 1:
            gaps = df.index.to_series().diff().dt.total_seconds().gt(step * 1.5).sum()
            if gaps:
                log.warning("%s %s history has %d gap(s) after refresh -- a rolling "
                            "window will span them", symbol, interval, int(gaps))
        if cache and len(df):
            try:
                _atomic_parquet(df, path)
            except Exception as e:  # noqa: BLE001
                log.warning("could not write history cache: %s", e)
        return df.iloc[-bars:]

    def daily(self, ticker: str, lookback_days: Optional[int] = None,
              cache_hours: float = 6.0) -> pd.DataFrame:
        """Daily OHLCV for a non-crypto series (HYG, LQD, ^GSPC, DX-Y.NYB, ...).

        Refreshes the shared `data/<ticker>_d.parquet` cache used by research when
        it is older than `cache_hours`, and falls back to the stale cache if the
        download fails -- a yfinance outage must not take a live strategy down.

        `lookback_days` is how much history the CALLER needs, never how much is kept:
        the file is shared with research, so it is always filled back to
        `DAILY_CACHE_START`. Asking for 30 days used to create a 30-day file, and the
        next backtest to read that ticker silently got a 30-day series.
        """
        os.makedirs(DATA_DIR, exist_ok=True)
        path = daily_cache_path(ticker)
        fresh = os.path.exists(path) and (time.time() - os.path.getmtime(path)) < cache_hours * 3600
        if not fresh:
            try:
                import yfinance as yf
                start = pd.Timestamp(DAILY_CACHE_START).date()
                if lookback_days is not None:
                    asked = (datetime.now(timezone.utc) - timedelta(days=int(lookback_days))).date()
                    start = min(start, asked)
                new = yf.download(ticker, start=str(start), auto_adjust=True,
                                  progress=False, multi_level_index=False).dropna()
                if len(new):
                    if os.path.exists(path):
                        old = pd.read_parquet(path)
                        old.index = pd.to_datetime(old.index).tz_localize(None)
                        new.index = pd.to_datetime(new.index).tz_localize(None)
                        new = pd.concat([old[~old.index.isin(new.index)], new]).sort_index()
                    _atomic_parquet(new, path)
            except Exception as e:  # noqa: BLE001 - stale data beats no data
                log.warning("daily(%s) refresh failed, using cache: %s", ticker, e)
        if not os.path.exists(path):
            raise FileNotFoundError(f"no data for {ticker} and download failed")
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df


# --------------------------------------------------------------------------- quotes

class QuoteSource:
    """Where a broker's mark price comes from, and which bar that price belongs to.

    This is the seam that stops "paper trading" meaning "the Binance spot testnet".
    A ledger, a fill model and a mark price are all a paper book needs; only the mark
    price ever knew what venue it came from, so that is the one thing made pluggable.

    `bar_key` is the other half, and it is what lets a book trade an instrument that
    is not open 24/7. A continuous market returns None -- every wake-up is a fresh
    price, so act. A daily market returns the date of the last closed bar, and the
    runner acts only when that changes. That is deliberately NOT a market calendar:
    holidays, half-days, DST shifts and a late data vendor all look the same from
    here -- the bar either advanced or it did not -- so there is no calendar to get
    wrong and no dependency to keep up to date.
    """

    name = "quote-source"
    #: bars per year, for annualising live statistics on this kind of market
    bars_per_year_daily = 365.0

    def price(self, symbol: str) -> float:
        raise NotImplementedError

    def bar_key(self, symbol: str) -> Optional[str]:
        return None


class TestnetQuotes(QuoteSource):
    """The paper venue's own last trade -- the right price to SIZE a testnet order."""

    name = "binance-testnet"

    def price(self, symbol: str) -> float:
        return float(_request(f"{BASE_URL}/api/v3/ticker/price?symbol={symbol}")["price"])


class PublicQuotes(QuoteSource):
    """Real Binance spot. Continuous, so every wake-up is a new bar."""

    name = "binance-public"

    def price(self, symbol: str) -> float:
        return float(_request(f"{PUBLIC_URL}/api/v3/ticker/price?symbol={symbol}")["price"])


class YahooQuotes(QuoteSource):
    """Last daily close from the shared `data/` cache, for anything not on Binance.

    Equities, ETFs, FX and futures fill at the close of the bar the signal was
    computed on, which is exactly what `research_lib.backtest` charges turnover at --
    so a simulated fill here matches the backtest's assumption more closely than a
    live crypto market order matches its own.

    The in-process memo is not a micro-optimisation: a cross-sectional book prices a
    dozen symbols twice per rebalance, and every one of those is a parquet read that
    many daemons make at once.
    """

    name = "yahoo-daily"
    bars_per_year_daily = 252.0        # trading days, not calendar days

    def __init__(self, market_data: Optional["MarketData"] = None,
                 cache_hours: float = 1.0, memo_seconds: float = 30.0):
        self.md = market_data or MarketData()
        self.cache_hours = float(cache_hours)
        self.memo_seconds = float(memo_seconds)
        self._memo: dict = {}          # symbol -> (monotonic, bar date, close)

    def _last_bar(self, symbol: str):
        hit = self._memo.get(symbol)
        if hit is not None and (time.monotonic() - hit[0]) < self.memo_seconds:
            return hit[1], hit[2]
        df = self.md.daily(symbol, cache_hours=self.cache_hours)
        if df.empty:
            raise RuntimeError(f"no daily data for {symbol}")
        day = pd.Timestamp(df.index[-1]).date()
        close = float(df["Close"].iloc[-1])
        if not (close > 0):
            raise RuntimeError(f"{symbol} last close is {close}, refusing to mark to it")
        self._memo[symbol] = (time.monotonic(), day, close)
        return day, close

    def price(self, symbol: str) -> float:
        return self._last_bar(symbol)[1]

    def bar_key(self, symbol: str) -> Optional[str]:
        return self._last_bar(symbol)[0].isoformat()


#: name -> factory, so a runner or `meta.json` can name its quote source as a string
QUOTE_SOURCES = {
    "binance-testnet": TestnetQuotes,
    "binance-public": PublicQuotes,
    "yahoo-daily": YahooQuotes,
}


def quote_source(spec) -> QuoteSource:
    """Accept a QuoteSource, or the name of one, and return an instance."""
    if isinstance(spec, QuoteSource):
        return spec
    if isinstance(spec, str):
        try:
            return QUOTE_SOURCES[spec]()
        except KeyError:
            raise ValueError(f"unknown quote source {spec!r}; use one of "
                             f"{sorted(QUOTE_SOURCES)}") from None
    raise TypeError(f"expected a QuoteSource or its name, got {type(spec).__name__}")


# --------------------------------------------------------------------------- allocation

ALLOC_PATH = os.path.join(HARNESS_DIR, "state", "allocations.json")
DEFAULT_CAPITAL = 2_500.0

VENUE_BOOK = "venue"
SIM_BOOK = "sim"
DEFAULT_BOOK = SIM_BOOK

#: Capital lives in one of two books, and which one a strategy is on is the whole
#: difference between "how many can I run" being four and being unbounded.
#:
#: `venue` ledgers are backed by a REAL shared testnet balance, so they must add up to
#: something the account can actually fund -- that pool is a genuine constraint and
#: stays capped. `sim` ledgers share nothing: each is a private book filled against a
#: quote source, so a second one costs no capital that the first was using. Capping
#: those would be inventing a scarcity that does not exist.
DEFAULT_BOOKS = {
    VENUE_BOOK: {
        "pool_usdt": 10_000.0,
        "unlimited": False,
        "description": "Binance spot testnet -- ledgers backed by one shared account",
    },
    SIM_BOOK: {
        "pool_usdt": None,
        "unlimited": True,
        "description": "Self-contained simulation -- no shared account, so no cap",
    },
}


def _normalise_allocations(d: dict) -> dict:
    """Bring any on-disk version up to the current shape, in memory.

    A v1 file has a single top-level `pool_usdt` and strategies with no `book`. Those
    strategies were all funded from the real testnet account, so they migrate to
    `venue` -- reading them as `sim` would silently uncap a pool that a live account
    still has to cover.
    """
    books = {k: dict(v) for k, v in DEFAULT_BOOKS.items()}
    on_disk = d.get("books")
    if isinstance(on_disk, dict):
        for name, cfg in on_disk.items():
            if isinstance(cfg, dict):
                books.setdefault(name, {"pool_usdt": None, "unlimited": False,
                                        "description": ""}).update(cfg)
    elif d.get("pool_usdt") is not None:
        books[VENUE_BOOK]["pool_usdt"] = float(d["pool_usdt"])

    strategies = {}
    for name, s in (d.get("strategies") or {}).items():
        if not isinstance(s, dict):
            continue
        s = dict(s)
        s.setdefault("book", VENUE_BOOK)
        strategies[name] = s
    return {"version": 2, "books": books, "strategies": strategies}


def _read_allocations() -> dict:
    if os.path.exists(ALLOC_PATH):
        try:
            with open(ALLOC_PATH) as fh:
                return _normalise_allocations(json.load(fh))
        except Exception as e:  # noqa: BLE001
            log.warning("allocations file unreadable: %s", e)
    return _normalise_allocations({})


def _write_allocations(d: dict):
    os.makedirs(os.path.dirname(ALLOC_PATH), exist_ok=True)
    tmp = f"{ALLOC_PATH}.{os.getpid()}.tmp"
    with open(tmp, "w") as fh:
        json.dump(d, fh, indent=2)
    os.replace(tmp, ALLOC_PATH)


def book_of(name: str) -> str:
    """Which book a deployed strategy draws its capital from."""
    return _read_allocations()["strategies"].get(name, {}).get("book", DEFAULT_BOOK)


def allocations_summary() -> dict:
    """Per-book pool, commitment and headroom -- what the dashboard renders."""
    d = _read_allocations()
    out = {}
    for book, cfg in d["books"].items():
        mine = {k: v for k, v in d["strategies"].items() if v.get("book") == book}
        committed = sum(float(v.get("capital_usdt") or 0) for v in mine.values())
        pool = cfg.get("pool_usdt")
        out[book] = {
            "pool_usdt": pool,
            "unlimited": bool(cfg.get("unlimited")),
            "description": cfg.get("description", ""),
            "committed_usdt": committed,
            "free_usdt": None if cfg.get("unlimited") or pool is None
                         else float(pool) - committed,
            "strategies": len(mine),
        }
    return out


def allocate(name: str, capital_usdt: float = DEFAULT_CAPITAL,
             book: str = DEFAULT_BOOK) -> dict:
    """Reserve trading capital for a strategy, refusing to oversubscribe its book.

    Capital is ALLOCATED, not divided: deploying or retiring a strategy never
    resizes the others.  Dividing account equity by the live strategy count would
    make every strategy churn its whole position -- and pay the spread -- each time
    an unrelated one came or went.

    Each book is accounted separately. A `sim` deployment cannot exhaust the venue
    pool, and -- the reason the old single pool capped the desk at four strategies --
    a venue deployment is no longer charged for every simulated book alongside it.
    """
    d = _read_allocations()
    if book not in d["books"]:
        raise ValueError(f"unknown book {book!r}; use one of {sorted(d['books'])}")
    capital_usdt = float(capital_usdt)
    if not capital_usdt > 0:
        raise ValueError(f"capital must be positive, got {capital_usdt}")

    cfg = d["books"][book]
    if not cfg.get("unlimited"):
        pool = cfg.get("pool_usdt")
        if pool is None:
            raise ValueError(f"book {book!r} is capped but has no pool_usdt set")
        others = {k: v for k, v in d["strategies"].items()
                  if k != name and v.get("book") == book}
        committed = sum(float(v["capital_usdt"]) for v in others.values())
        free = float(pool) - committed
        if capital_usdt > free + 1e-9:
            raise ValueError(
                f"cannot allocate {capital_usdt:.0f} USDT to {name} in book {book!r}: "
                f"pool is {float(pool):.0f}, {committed:.0f} already committed to "
                f"{len(others)} strategy(ies), {free:.0f} free. Retire a strategy, "
                f"lower the request, deploy to the '{SIM_BOOK}' book instead, or raise "
                f"this book's pool_usdt in {ALLOC_PATH}.")

    d["strategies"][name] = {"capital_usdt": capital_usdt, "book": book,
                             "allocated": datetime.now(timezone.utc).isoformat()}
    _write_allocations(d)
    return d


def release(name: str):
    d = _read_allocations()
    d["strategies"].pop(name, None)
    _write_allocations(d)


# --------------------------------------------------------------------------- broker


class LedgerBroker:
    """A private base/quote ledger, marked to a `QuoteSource`, filled by simulation.

    This is the part of paper trading that never needed a venue.  A book seeded with
    `capital_usdt`, a target weight, a mark price, and fills that move units between
    the two legs net of slippage and fee -- that is the whole mechanism.  `PaperBroker`
    puts the Binance spot testnet on top of it; `SimBroker` puts nothing on top of it,
    which is exactly the point.

    `weight` is the fraction of THIS STRATEGY's own book held in the base asset.  Every
    strategy keeps its own ledger, so one venue account is shared by many strategies
    without them fighting over it -- and a simulated book needs no account at all,
    which is why simulated books do not have to be rationed.

    Subclasses customise three things and inherit everything else:

      * `_clamp_weight` -- which weights this venue can actually express;
      * `_skip_reason`  -- when a trade is too small to be worth sending;
      * `_execute`      -- where the order goes.  The default is a simulated fill.
    """

    #: instrument kind, journalled so a reader knows what the weight meant
    market = "spot"
    #: quote source used when the caller does not name one
    default_quotes = "binance-testnet"

    def __init__(self, symbol: str, capital_usdt: float = DEFAULT_CAPITAL,
                 max_weight: float = 1.0, slippage_bps: float = 1.0,
                 fee_bps: float = 10.0, state_file: Optional[str] = None,
                 quote: str = "USDT", quotes=None, allow_short: bool = False):
        load_env()
        self.symbol = symbol
        self.quote = quote
        self.base = self._derive_base(symbol, quote)
        self.capital_usdt = float(capital_usdt)
        self.max_weight = float(max_weight)
        self.slippage_bps = float(slippage_bps)
        self.fee_bps = float(fee_bps)          # simulated fee; a venue charges its own
        self.allow_short = bool(allow_short)
        self.quotes = quote_source(quotes or self.default_quotes)
        # Nothing leaves this process unless a subclass connects it to something.
        self.shadow = True
        # the strategy's private book -- NOT an exchange account
        self._base_units = 0.0
        self._quote_units = float(capital_usdt)
        self.state_file = state_file           # persists the ledger across restarts
        self.step, self.min_qty, self.min_notional, self.qty_prec = 1e-5, 1e-5, 5.0, 5
        self._load_ledger()

    def _derive_base(self, symbol: str, quote: str) -> str:
        """Base asset of `symbol`.  A Binance pair is BASE and QUOTE concatenated."""
        return symbol[:-len(quote)] if symbol.endswith(quote) else symbol[:-4]

    @property
    def mode(self) -> str:
        """`sim` | `shadow` | `live` -- what actually produced the fills.

        Worth keeping distinct from `shadow`.  A `PaperBroker` in shadow mode has
        DEGRADED: it wanted the venue and could not reach it, and that is a fault to
        surface.  A `SimBroker` is simulated by design and nothing is wrong with it.
        Collapsing the two would either raise false alarms or hide real ones.
        """
        return "sim"

    # ---- ledger persistence (a restarted daemon must not forget its position)

    def _load_ledger(self):
        if not self.state_file or not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file) as fh:
                st = json.load(fh)
            if st.get("symbol") == self.symbol:
                self._base_units = float(st["base"])
                self._quote_units = float(st["quote"])
                log.info("resumed ledger: %s=%.8f %s=%.2f", self.base,
                         self._base_units, self.quote, self._quote_units)
        except Exception as e:  # noqa: BLE001
            log.warning("could not read ledger %s: %s", self.state_file, e)

    def _save_ledger(self):
        if not self.state_file:
            return
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        tmp = self.state_file + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"symbol": self.symbol, "base": self._base_units,
                       "quote": self._quote_units, "capital_usdt": self.capital_usdt,
                       "shadow": self.shadow, "mode": self.mode,
                       "updated": datetime.now(timezone.utc).isoformat()}, fh, indent=2)
        os.replace(tmp, self.state_file)

    # ---- preflight

    def preflight(self) -> dict:
        """Check the book can trade.  A simulated one always can."""
        out = {"venue": self.quotes.name, "market": self.market, "symbol": self.symbol,
               "shadow": self.shadow, "mode": self.mode,
               "capital_usdt": self.capital_usdt,
               "ledger": {"base": self._base_units, "quote": self._quote_units}}
        self._save_ledger()
        return out

    # ---- state (all of it ledger-scoped, never account-wide)

    def mark_price(self) -> float:
        """Price this book marks and fills at."""
        return self.quotes.price(self.symbol)

    def bar_key(self) -> Optional[str]:
        """Identity of the bar the current mark belongs to, or None if continuous."""
        return self.quotes.bar_key(self.symbol)

    def bars_per_year(self, schedule: str) -> Optional[float]:
        """Bars of `schedule` this market prints in a year, or None for the default.

        Only differs from the continuous table when the market has sessions: a daily
        equity bar prints about 252 times a year rather than 365, and annualising its
        Sharpe with 365 overstates it by roughly 20% -- on the live number the desk
        compares against the backtest.
        """
        if schedule == "1d":
            return self.quotes.bars_per_year_daily
        return None

    def position(self) -> float:
        """This strategy's base holding, in base units."""
        return self._base_units

    def equity(self, price: Optional[float] = None) -> float:
        """This strategy's book: its quote units plus its base units at the mark."""
        px = price if price is not None else self.mark_price()
        return self._quote_units + self._base_units * px

    def reconcile(self) -> dict:
        """Ledger vs the outside world.  A simulated book has no outside world."""
        return {"shadow": True, "mode": self.mode, "symbol": self.symbol,
                "ledger_base": self._base_units, "ledger_quote": self._quote_units}

    # ---- trading

    def _round_qty(self, qty: float) -> float:
        """Round toward zero onto the lot step -- rounding up can exceed what we hold.

        Toward zero rather than down, so the guarantee still holds once a book is
        allowed to go short: rounding -1.5 lots down to -2 would overshoot the target
        in exactly the way rounding 1.5 up to 2 does.  `step <= 0` means fractional
        sizing, where there is no lot grid to snap to.
        """
        if self.step <= 0:
            return float(qty)
        n = int(abs(qty) / self.step + 1e-9)
        out = round(n * self.step, self.qty_prec)
        return -out if qty < 0 else out

    def _clamp_weight(self, weight: float) -> float:
        lo = -self.max_weight if self.allow_short else 0.0
        return max(lo, min(self.max_weight, float(weight)))

    def _skip_reason(self, w: float, delta: float, target_qty: float,
                     cur: float, px: float) -> Optional[str]:
        if abs(delta) < self.min_qty:
            return "below min qty"
        # The venue rejects a trade under minNotional unless it liquidates the
        # holding outright -- let a full exit through, hold otherwise.
        closing = abs(target_qty) < self.min_qty <= abs(cur)
        if abs(delta) * px < self.min_notional and not closing:
            return f"delta notional {abs(delta) * px:.2f} < {self.min_notional}"
        return None

    def set_target_weight(self, weight: float) -> dict:
        """Move this strategy's base holding to `weight` of its own book."""
        w = self._clamp_weight(weight)
        px = self.mark_price()
        eq = self.equity(px)
        # A short that more than doubles takes equity negative, and `w * eq / px` then
        # flips sign: asking to go fully LONG would leave the book short. Unreachable
        # on a long-only venue book, which is why it went unnoticed until shorting
        # existed. Stop instead -- the daemon's error counter surfaces it.
        if eq <= 0:
            raise RuntimeError(
                f"equity is {eq:.2f}; the book is wiped out, refusing to trade. "
                "Sizing a target off non-positive equity inverts every weight.")
        cur = self._base_units
        target_qty = self._round_qty(w * eq / px)
        delta = target_qty - cur
        rep = {"weight": w, "price": px, "equity": eq, "target_qty": target_qty,
               "current_qty": cur, "delta_qty": delta, "shadow": self.shadow,
               "mode": self.mode, "market": self.market,
               "capital_usdt": self.capital_usdt, "traded": False}

        skip = self._skip_reason(w, delta, target_qty, cur, px)
        if skip:
            rep["skipped"] = skip
            return rep

        side = "BUY" if delta > 0 else "SELL"
        qty = self._round_qty(abs(delta))
        return self._execute(side, qty, px, rep)

    def _execute(self, side: str, qty: float, px: float, rep: dict) -> dict:
        """Fill against the mark, net of slippage and fee.  Nothing leaves the process."""
        fill = px * (1 + (self.slippage_bps / 1e4) * (1 if side == "BUY" else -1))
        cost = qty * fill
        fee = cost * self.fee_bps / 1e4
        if side == "BUY":
            self._quote_units -= cost + fee
            self._base_units += qty
        else:
            self._quote_units += cost - fee
            self._base_units -= qty
        self._save_ledger()
        rep.update(traded=True, side=side, filled_qty=qty, fill_price=fill,
                   fee=fee, order_id="shadow")
        return rep

    def flatten(self) -> dict:
        return self.set_target_weight(0.0)


class PaperBroker(LedgerBroker):
    """Binance **spot testnet** account, driven by a target weight.

    Spot, long/flat, unlevered: `weight` is the fraction of THIS STRATEGY's capital
    held in the base asset, in [0, 1].  There is no shorting -- the spot testnet has
    no margin -- so a strategy that needs a negative weight cannot be deployed here.
    Use `SimBroker` for one that does.

    Every strategy keeps its own **ledger**: a private book of base and quote units,
    seeded with `capital_usdt` and updated from actual fills.  One testnet account
    is therefore shared by many strategies without them fighting over it, and the
    faucet endowment sitting in the account (1 BTC, 10k USDT, hundreds of alts) never
    inflates anyone's position sizing.  P&L compounds inside each ledger.

    Shadow and live are the same code path; the only difference is whether the order
    actually reaches the venue.  `shadow` is set when the account is unusable -- bad
    credentials, or not enough free balance to back the ledger -- so a strategy still
    produces a verifiable track instead of crash-looping.  Every journal line and
    `launch_live.sh status` say which mode produced it.
    """

    default_quotes = "binance-testnet"

    def __init__(self, symbol: str, capital_usdt: float = DEFAULT_CAPITAL,
                 max_weight: float = 1.0, slippage_bps: float = 1.0,
                 fee_bps: float = 10.0, force_shadow: bool = False,
                 state_file: Optional[str] = None, quote: str = "USDT",
                 resync_every_s: float = 900.0, quotes=None):
        super().__init__(symbol, capital_usdt=capital_usdt, max_weight=max_weight,
                         slippage_bps=slippage_bps, fee_bps=fee_bps,
                         state_file=state_file, quote=quote, quotes=quotes,
                         allow_short=False)
        self.key, self.secret, self.key_source = _spot_credentials()
        self._time_offset = 0
        self._last_sync = 0.0
        self.resync_every_s = float(resync_every_s)
        self.shadow = bool(force_shadow)
        if not force_shadow:
            self._load_filters()
            self._sync_time()

    @property
    def mode(self) -> str:
        return "shadow" if self.shadow else "live"

    # ---- plumbing

    def _sync_time(self, force: bool = True):
        """Re-sync the clock offset.  A daemon left running for weeks WILL drift far
        enough to trip Binance's recvWindow, so this is refreshed periodically and
        not only at startup."""
        if not force and (time.time() - self._last_sync) < self.resync_every_s:
            return
        try:
            srv = _request(f"{BASE_URL}/api/v3/time")["serverTime"]
            new = srv - int(time.time() * 1000)
            if abs(new - self._time_offset) > 1000:
                log.info("clock offset %+d ms -> %+d ms", self._time_offset, new)
            self._time_offset = new
            self._last_sync = time.time()
        except Exception as e:  # noqa: BLE001
            log.warning("time sync failed: %s", e)

    def _load_filters(self):
        try:
            info = _request(f"{BASE_URL}/api/v3/exchangeInfo?symbol={self.symbol}")
            s = info["symbols"][0]
            self.base, self.quote = s["baseAsset"], s["quoteAsset"]
            f = {x["filterType"]: x for x in s["filters"]}
            self.step = float(f["LOT_SIZE"]["stepSize"])
            self.min_qty = float(f["LOT_SIZE"]["minQty"])
            notional = f.get("NOTIONAL") or f.get("MIN_NOTIONAL") or {}
            self.min_notional = float(notional.get("minNotional",
                                                   notional.get("notional", 5.0)))
            self.qty_prec = max(0, int(round(-np.log10(self.step)))) if self.step < 1 else 0
        except Exception as e:  # noqa: BLE001
            log.warning("exchangeInfo failed, using defaults: %s", e)

    def _signed(self, path: str, params: dict, method="GET"):
        self._sync_time(force=False)
        params = dict(params or {})
        params["timestamp"] = int(time.time() * 1000) + self._time_offset
        params.setdefault("recvWindow", 10_000)
        q = urllib.parse.urlencode(params)
        sig = hmac.new(self.secret.encode(), q.encode(), hashlib.sha256).hexdigest()
        return _request(f"{BASE_URL}{path}?{q}&signature={sig}",
                        headers={"X-MBX-APIKEY": self.key}, method=method)

    def account_balances(self) -> dict:
        """Raw exchange balances -- the WHOLE account, shared by every strategy.
        Used for reconciliation and free-balance guards, never for sizing."""
        acct = self._signed("/api/v3/account", {})
        return {b["asset"]: {"free": float(b["free"]), "locked": float(b["locked"])}
                for b in acct["balances"]}

    # ---- preflight

    def preflight(self) -> dict:
        """Check credentials and that the account can actually back this ledger."""
        out = {"venue": BASE_URL, "market": self.market, "symbol": self.symbol,
               "shadow": self.shadow, "mode": self.mode, "key_source": self.key_source,
               "capital_usdt": self.capital_usdt,
               "ledger": {"base": self._base_units, "quote": self._quote_units}}
        if self.shadow:
            out["reason"] = "forced shadow mode"
            return out
        if not self.key or not self.secret:
            self.shadow = True
            out["shadow"] = True
            out["mode"] = self.mode
            out["reason"] = ("no spot-testnet credentials in .env -- set "
                             f"{SPOT_KEY_ENV} / {SPOT_SECRET_ENV}. Running in shadow mode.")
            log.warning(out["reason"])
            return out
        try:
            bals = self.account_balances()
            out["can_trade"] = True
            out["account_quote_free"] = bals.get(self.quote, {}).get("free", 0.0)
            out["account_base_free"] = bals.get(self.base, {}).get("free", 0.0)
            # The account must be able to fund what this ledger still wants to buy.
            if out["account_quote_free"] < min(self._quote_units, self.min_notional * 2):
                self.shadow = True
                out["shadow"] = True
                out["reason"] = (
                    f"account holds {out['account_quote_free']:.2f} free {self.quote}, "
                    f"not enough to back this strategy's {self._quote_units:.2f} "
                    f"{self.quote} ledger. Top up at https://testnet.binance.vision or "
                    "lower capital_usdt. Running in shadow mode.")
                log.warning(out["reason"])
        except BinanceError as e:
            self.shadow = True
            out["shadow"] = True
            if e.code in (-2015, -2008, -2014):
                out["reason"] = (
                    f"the credentials in .env are not valid Binance SPOT TESTNET keys ({e}). "
                    "Create a key at https://testnet.binance.vision (log in with GitHub) and "
                    f"put it in .env as {SPOT_KEY_ENV} / {SPOT_SECRET_ENV}. "
                    "Running in shadow mode until then.")
            else:
                out["reason"] = f"account check failed ({e}); falling back to shadow mode"
            log.warning(out["reason"])
        except Exception as e:  # noqa: BLE001
            self.shadow = True
            out["shadow"] = True
            out["reason"] = f"account check failed ({e}); falling back to shadow mode"
            log.warning(out["reason"])
        out["mode"] = self.mode
        self._save_ledger()
        return out

    def reconcile(self) -> dict:
        """Ledger vs exchange. Persistent drift means fills we did not record."""
        if self.shadow:
            return {"shadow": True}
        bals = self.account_balances()
        return {"shadow": False, "symbol": self.symbol,
                "ledger_base": self._base_units, "ledger_quote": self._quote_units,
                "account_base": bals.get(self.base, {}).get("free", 0.0)
                + bals.get(self.base, {}).get("locked", 0.0),
                "account_quote": bals.get(self.quote, {}).get("free", 0.0)
                + bals.get(self.quote, {}).get("locked", 0.0)}

    # ---- trading

    def _execute(self, side: str, qty: float, px: float, rep: dict) -> dict:
        if self.shadow:
            return super()._execute(side, qty, px, rep)

        # Never exceed this ledger's own book, nor the shared account's free balance.
        try:
            bals = self.account_balances()
        except Exception as e:  # noqa: BLE001
            rep["error"] = f"balance check failed: {e}"
            return rep
        if side == "SELL":
            qty = min(qty, self._round_qty(self._base_units),
                      self._round_qty(bals.get(self.base, {}).get("free", 0.0)))
        else:
            headroom = px * 1.002                      # fee + slippage cushion
            qty = min(qty, self._round_qty(self._quote_units / headroom),
                      self._round_qty(bals.get(self.quote, {}).get("free", 0.0) / headroom))
        if qty < self.min_qty or qty * px < self.min_notional:
            rep["skipped"] = f"insufficient free balance for {side} (qty {qty})"
            return rep

        try:
            o = self._signed("/api/v3/order",
                             {"symbol": self.symbol, "side": side, "type": "MARKET",
                              "quantity": f"{qty:.{self.qty_prec}f}"}, method="POST")
            executed = float(o.get("executedQty") or 0)
            quote_qty = float(o.get("cummulativeQuoteQty") or 0)
            fills = o.get("fills", []) or []
            # Binance charges a BUY's commission in the BASE asset and a SELL's in the
            # quote asset. Counting only the quote side -- which is what this did -- meant
            # every buy credited the ledger with more base than the account actually
            # received, so the book drifted further from the exchange on every trade and
            # equity read high. Both sides are now taken out of the units they were
            # actually charged in.
            fee_quote = sum(float(f.get("commission") or 0) for f in fills
                            if f.get("commissionAsset") == self.quote)
            fee_base = sum(float(f.get("commission") or 0) for f in fills
                           if f.get("commissionAsset") == self.base)
            # A commission paid in a third asset (BNB discount) touches neither leg; the
            # ledger is then optimistic by that amount and reconcile() is what shows it.
            if side == "BUY":
                self._base_units += executed - fee_base
                self._quote_units -= quote_qty + fee_quote
            else:
                self._base_units -= executed + fee_base
                self._quote_units += quote_qty - fee_quote
            self._save_ledger()
            fill_price = (quote_qty / executed) if executed else px
            rep.update(traded=executed > 0, side=side, order_id=o.get("orderId"),
                       status=o.get("status"), filled_qty=executed,
                       # journalled in quote terms so fees_paid stays one currency
                       fee=fee_quote + fee_base * fill_price,
                       fee_base=fee_base, fee_quote=fee_quote,
                       fill_price=fill_price)
        except BinanceError as e:
            rep["error"] = str(e)
            log.error("order rejected: %s", e)
        return rep


class SimBroker(LedgerBroker):
    """A paper book with no venue behind it -- any instrument a quote source can price.

    This is what lets the desk trade what its research actually covers.  Equities,
    ETFs, FX, rates and futures are all priced by `YahooQuotes` from the same `data/`
    cache the backtests read, and filled against that same close, so a simulated fill
    here matches what `research_lib.backtest` assumed more closely than a live crypto
    market order matches its own backtest.

    Three things it does that `PaperBroker` cannot, all of them things the research
    briefs already ask for:

      * **shorting** (`allow_short=True`), so a long/short cross-section or a
        short-vol idea is expressible rather than an automatic rejection;
      * **fractional sizing** -- there is no lot grid and no exchange minimum, so a
        2500-dollar book can hold a 762-dollar share;
      * **no shared account**, and therefore no pool to exhaust.  A second simulated
        book takes nothing from the first, which is why they are not rationed.

    What it is NOT is a claim about execution.  There is no order book here, no
    rejection, no partial fill and no queue position.  A simulated track is weaker
    evidence than a venue-executed one and the dashboard says so; keep the two books
    apart rather than reading a `sim` Sharpe as if it had cleared a real exchange.
    """

    default_quotes = "yahoo-daily"

    def __init__(self, symbol: str, capital_usdt: float = DEFAULT_CAPITAL,
                 max_weight: float = 1.0, slippage_bps: float = 1.0,
                 fee_bps: float = 10.0, state_file: Optional[str] = None,
                 quote: str = "USD", quotes=None, allow_short: bool = False,
                 min_trade_usd: float = 1.0):
        super().__init__(symbol, capital_usdt=capital_usdt, max_weight=max_weight,
                         slippage_bps=slippage_bps, fee_bps=fee_bps,
                         state_file=state_file, quote=quote, quotes=quotes,
                         allow_short=allow_short)
        self.min_trade_usd = float(min_trade_usd)
        # Fractional sizing: no lot grid, no exchange minimum, and no shared account
        # to run out of.  A trade is gated on its notional alone.
        self.step, self.min_qty, self.min_notional, self.qty_prec = 0.0, 0.0, 0.0, 10

    def _derive_base(self, symbol: str, quote: str) -> str:
        """A plain ticker IS the instrument; cash is the other leg.

        Not the Binance rule.  Splitting `SPY` as a BASE+QUOTE pair leaves an empty
        base, and every log line and reconciliation downstream then names nothing.
        """
        return symbol

    def _skip_reason(self, w: float, delta: float, target_qty: float,
                     cur: float, px: float) -> Optional[str]:
        # A full exit always goes through: with no lot minimum there is no such thing
        # as a residue too small to sell, and leaving dust behind would mean weight 0
        # and a non-zero position, which is a lie the journal would carry forever.
        if w == 0.0 and cur != 0.0:
            return None
        notional = abs(delta) * px
        if notional < self.min_trade_usd:
            return f"delta notional {notional:.4f} < {self.min_trade_usd}"
        return None


def broker_from_meta(meta: dict, state_file: Optional[str] = None) -> LedgerBroker:
    """Rebuild a deployed strategy's broker from its `meta.json`.

    One place knows how a `meta.json` maps onto a book, so anything acting on a
    strategy out of band -- the dashboard's flatten button above all -- reconstructs
    the book the daemon is actually running rather than assuming a `PaperBroker`.
    Assuming would be quietly wrong: flattening a basket through a single-instrument
    broker reads a portfolio ledger it cannot parse, finds no position, and reports
    success having sold nothing.

    The shape of the meta decides: `symbols` (a list) means a basket, `book` picks
    between the venue and a simulated book, and the rest are the constructor's own
    defaults so an older meta.json still resolves.
    """
    capital = float(meta.get("capital_usdt") or DEFAULT_CAPITAL)
    quotes = meta.get("quotes")
    symbols = meta.get("symbols")
    if symbols:
        from portfolio import SimPortfolioBroker   # local: portfolio imports this module
        return SimPortfolioBroker(
            symbols, capital_usdt=capital, state_file=state_file,
            quotes=quotes or "yahoo-daily",
            max_gross=float(meta.get("max_gross") or 1.0),
            allow_short=bool(meta.get("allow_short", True)),
            open_universe=bool(meta.get("open_universe", False)))

    symbol = meta.get("symbol")
    if not symbol:
        raise ValueError("meta.json names neither `symbol` nor `symbols`")
    if meta.get("book", VENUE_BOOK) == VENUE_BOOK:
        return PaperBroker(symbol, capital_usdt=capital, state_file=state_file,
                           **({"quotes": quotes} if quotes else {}))
    return SimBroker(symbol, capital_usdt=capital, state_file=state_file,
                     quotes=quotes or "yahoo-daily",
                     max_weight=float(meta.get("max_weight") or 1.0),
                     allow_short=bool(meta.get("allow_short", False)))


# --------------------------------------------------------------------------- scheduling

_INTERVAL_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "12h": 43200, "1d": 86400,
}


def next_boundary(schedule: str, now: Optional[datetime] = None, offset_s: float = 20.0) -> datetime:
    """Next UTC bar boundary for `schedule`, plus `offset_s` so the bar has settled."""
    if schedule not in _INTERVAL_SECONDS:
        raise ValueError(f"unsupported schedule {schedule!r}; use one of "
                         f"{sorted(_INTERVAL_SECONDS)}")
    step = _INTERVAL_SECONDS[schedule]
    now = now or datetime.now(timezone.utc)
    epoch = now.timestamp() - offset_s
    return datetime.fromtimestamp((int(epoch // step) + 1) * step + offset_s, tz=timezone.utc)


# --------------------------------------------------------------------------- runner

class StrategyRunner:
    """Bar-boundary loop: compute a target weight, apply it, journal the result."""

    def __init__(self, name: str, symbol: str, schedule: str,
                 compute_weight: Callable[[datetime], float],
                 broker: Optional[LedgerBroker] = None,
                 state_dir: Optional[str] = None,
                 offset_s: float = 20.0,
                 flatten_on_stop: bool = False,
                 max_consecutive_errors: int = 10,
                 recheck_s: float = 1800.0):
        self.name = name
        self.symbol = symbol
        self.schedule = schedule
        self.compute_weight = compute_weight
        self.broker = broker or PaperBroker(symbol)
        self.offset_s = offset_s
        self.flatten_on_stop = flatten_on_stop
        self.max_consecutive_errors = max_consecutive_errors
        self.recheck_s = float(recheck_s)
        self.dir = state_dir or os.path.join(LIVE_DIR, name)
        os.makedirs(self.dir, exist_ok=True)
        if self.broker.state_file is None:
            self.broker.state_file = os.path.join(self.dir, "ledger.json")
            self.broker._load_ledger()
        self.journal_path = os.path.join(self.dir, "journal.jsonl")
        self.state_path = os.path.join(self.dir, "state.json")
        self._last_bar = self._restore_last_bar()
        # Set by _tick: True when the last wake-up found no new bar. The run loop uses
        # it to re-check sooner than the next boundary; _bar_waited_on keeps the log
        # from repeating the same "already traded" line at every re-check.
        self._waiting_for_bar = False
        self._bar_waited_on: Optional[str] = None
        self._stop = threading.Event()
        self._setup_logging()

    def _restore_last_bar(self) -> Optional[str]:
        """The bar this strategy last acted on, so a restart does not re-trade it."""
        try:
            with open(self.state_path) as fh:
                return json.load(fh).get("last_bar")
        except Exception:  # noqa: BLE001 - no state yet, or unreadable: start fresh
            return None

    # ---- io

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)-7s %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
            force=True,
        )
        logging.Formatter.converter = time.gmtime

    def _journal(self, record: dict):
        record = {"ts": datetime.now(timezone.utc).isoformat(), "strategy": self.name, **record}
        with open(self.journal_path, "a") as fh:
            fh.write(json.dumps(record, default=str) + "\n")

    def _journal_context(self, bar: Optional[str]) -> dict:
        """Fields a rebalance row carries so it can be read without outside context.

        `bars_per_year` travels with the row rather than being looked up from the
        schedule later: only the market knows whether a "1d" bar is one of 365 or one
        of 252, and a journal that has to be told is a journal that can be misread.
        """
        ctx = {}
        if bar:
            ctx["bar"] = bar
        bpy = self.broker.bars_per_year(self.schedule)
        if bpy is not None:
            ctx["bars_per_year"] = bpy
        return ctx

    def _save_state(self, **kw):
        """Merge `kw` into `state.json`.

        Merged, not replaced. A poll that finds no new bar still has to record that the
        daemon is alive, and rewriting the file from scratch would drop the last weight,
        equity and position the dashboard reads -- so a healthy equity strategy would
        show blank from Friday evening until Monday. (Startup had the same hole: it
        wrote `status`/`preflight` alone and erased the previous run's numbers until
        the first rebalance landed.)
        """
        state = {}
        try:
            with open(self.state_path) as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                state = loaded
        except Exception:  # noqa: BLE001 - no state yet, or torn: start from scratch
            state = {}
        state.update({"strategy": self.name, "symbol": self.symbol,
                      "schedule": self.schedule, "pid": os.getpid(),
                      "shadow": self.broker.shadow, "mode": self.broker.mode,
                      "updated": datetime.now(timezone.utc).isoformat(), **kw})
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(state, fh, indent=2, default=str)
        os.replace(tmp, self.state_path)

    # ---- loop

    def _handle_signal(self, signum, _frame):
        log.info("signal %s received, shutting down", signum)
        self._stop.set()

    def step_once(self, now: Optional[datetime] = None,
                  bar: Optional[str] = None) -> dict:
        """Compute a weight and apply it, unconditionally. `--once` and tests use this."""
        now = now or datetime.now(timezone.utc)
        w = float(self.compute_weight(now))
        if w != w:  # NaN
            raise ValueError("compute_weight returned NaN")
        rep = self.broker.set_target_weight(w)
        self._journal({"event": "rebalance", **self._journal_context(bar), **rep})
        if bar:
            self._last_bar = bar
        self._save_state(last_weight=rep["weight"], last_price=rep.get("price"),
                         equity=rep.get("equity"), position=self.broker.position(),
                         capital_usdt=self.broker.capital_usdt,
                         last_run=now.isoformat(), last_bar=self._last_bar,
                         waiting_for_new_bar=False)
        log.info("w=%.4f px=%.2f eq=%.2f pos=%.6f traded=%s%s",
                 rep["weight"], rep.get("price", 0), rep.get("equity", 0),
                 rep.get("target_qty", 0), rep.get("traded"),
                 " SHADOW" if rep.get("shadow") else "")
        return rep

    def _tick(self, now: Optional[datetime] = None) -> Optional[dict]:
        """One wake-up of the daemon loop: rebalance only if there is a new bar.

        A continuous market (`bar_key() is None`) rebalances on every boundary, which
        is what crypto has always done and is unchanged. An instrument that only
        prints on session days returns the identity of its last closed bar, and this
        acts solely when that changes -- so a weekend, a holiday, a half-day and a
        data vendor running an hour late are all the same non-event, with no market
        calendar to encode and get wrong.
        """
        now = now or datetime.now(timezone.utc)
        bar = self.broker.bar_key()
        if bar is not None and bar == self._last_bar:
            # Once per bar, not once per re-check: the loop now comes back every
            # recheck_s while it waits, and a whole weekend of identical lines would
            # bury the one entry that matters when reading back why a day was missed.
            if bar != self._bar_waited_on:
                log.info("bar %s already traded; waiting for the next one", bar)
                self._bar_waited_on = bar
            self._waiting_for_bar = True
            # Still a successful poll: the daemon is alive and up to date, and the
            # staleness watchdog reads `last_run`. Leaving it at the last TRADE would
            # make every equity strategy look hung from Friday evening to Monday.
            self._save_state(status="running", last_run=now.isoformat(), last_bar=bar,
                             waiting_for_new_bar=True)
            return None
        self._waiting_for_bar = False
        return self.step_once(now, bar=bar)

    def check(self) -> dict:
        """Dry run: compute today's weight and report intended sizing, place no order.

        This is the pre-flight a deployment must pass before being daemonised --
        it exercises data loading, the signal, and the venue connection.
        """
        now = datetime.now(timezone.utc)
        pf = self.broker.preflight()
        t0 = time.time()
        w = float(self.compute_weight(now))
        px = self.broker.mark_price()
        eq = self.broker.equity(px)
        out = {"strategy": self.name, "symbol": self.symbol, "schedule": self.schedule,
               "now": now.isoformat(), "weight": w, "mark_price": px,
               "capital_usdt": self.broker.capital_usdt, "equity": eq,
               "position": self.broker.position(),
               "target_qty": self.broker._round_qty(w * eq / px),
               "signal_seconds": round(time.time() - t0, 2),
               "next_run": next_boundary(self.schedule, offset_s=self.offset_s).isoformat(),
               "bar": self.broker.bar_key(), "last_bar_traded": self._last_bar,
               "shadow": pf.get("shadow"), "mode": self.broker.mode,
               "venue": pf.get("venue", BASE_URL)}
        print(json.dumps(out, indent=2, default=str))
        if w != w:
            raise ValueError("compute_weight returned NaN")
        if not -1.0 <= w <= 1.0:
            raise ValueError(f"weight {w} outside [-1, 1]")
        return out

    def cli(self, argv=None):
        """Entry point for a deployed runner.py.

        `--check` computes one weight and exits (no orders).  `--once` performs a
        single rebalance and exits.  No argument runs the daemon loop.
        """
        argv = sys.argv[1:] if argv is None else argv
        if "--check" in argv:
            self.check()
            return
        if "--once" in argv:
            self.broker.preflight()
            # Ignores the gate -- an operator asking for a rebalance gets one -- but
            # still RECORDS the bar it traded, so a daemon started afterwards does not
            # immediately trade that same bar over again.
            self.step_once(bar=self.broker.bar_key())
            return
        self.run()

    def run(self, run_immediately: bool = True):
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        pf = self.broker.preflight()
        log.info("starting %s on %s %s (%s) -- %s", self.name, self.symbol,
                 self.broker.market, self.schedule,
                 {"live": "LIVE PAPER", "shadow": "SHADOW",
                  "sim": "SIMULATED"}.get(self.broker.mode, self.broker.mode.upper()))
        self._journal({"event": "start", **pf})
        self._save_state(status="running", preflight=pf)

        errors = 0
        if run_immediately:
            try:
                self._tick()
                errors = 0
            except Exception as e:  # noqa: BLE001
                errors += 1
                log.exception("initial step failed")
                self._journal({"event": "error", "error": repr(e)})

        while not self._stop.is_set():
            nxt = next_boundary(self.schedule, offset_s=self.offset_s)
            # A tick that found no new bar is either a genuine non-session (weekend,
            # holiday, half-day) or a data vendor running late, and _tick deliberately
            # cannot tell them apart -- that is what keeps a market calendar out of this
            # loop. The cost was paid on the second case: on a 1d schedule the next
            # boundary is 24h away, so a vendor that has not published by 20:00 New York
            # meant the whole session's decision was skipped in silence, and TLT skipped
            # 2026-09-16 and 2026-09-17 exactly that way. Coming back every recheck_s
            # makes the late-vendor case recover on its own, while the non-session case
            # stays a cheap no-op: bar_key is memoised and the daily cache is hourly, so
            # a weekend of re-checks is a handful of reads, not a poll storm.
            if self._waiting_for_bar and self.recheck_s > 0:
                nxt = min(nxt, datetime.now(timezone.utc)
                          + timedelta(seconds=self.recheck_s))
            wait = max(1.0, (nxt - datetime.now(timezone.utc)).total_seconds())
            log.info("sleeping %.0fs until %s", wait, nxt.isoformat())
            if self._stop.wait(wait):
                break
            try:
                self._tick(nxt)
                errors = 0
            except Exception as e:  # noqa: BLE001
                errors += 1
                log.exception("step failed (%d/%d)", errors, self.max_consecutive_errors)
                self._journal({"event": "error", "error": repr(e), "consecutive": errors})
                if errors >= self.max_consecutive_errors:
                    self._journal({"event": "abort", "reason": "too many consecutive errors"})
                    self._save_state(status="aborted")
                    raise

        if self.flatten_on_stop:
            try:
                self._journal({"event": "flatten", **self.broker.flatten()})
            except Exception as e:  # noqa: BLE001
                log.exception("flatten failed")
                self._journal({"event": "error", "error": repr(e)})
        self._journal({"event": "stop"})
        self._save_state(status="stopped")
        log.info("stopped")
