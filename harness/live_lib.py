"""
Live (paper) execution runtime for autoQuant strategies.

Venue: **Binance SPOT TESTNET** (https://testnet.binance.vision).  Long/flat,
unlevered, no shorting -- the weight a strategy returns is the fraction of account
equity held in the base asset, in [0, 1].

Signals are computed from REAL Binance market data (api.binance.com); only orders
and account state touch the testnet.  The two are deliberately separate: a testnet
price series is not the market the research was backtested on.

A deployed strategy only has to supply a `compute_weight()` callable.  Everything
else -- bar-boundary scheduling, closed-bar-only data, order sizing, exchange
filters, journalling, crash recovery, graceful shutdown -- lives here.

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

Conventions
-----------
* `compute_weight(now)` returns the TARGET weight for the bar that is about to
  start, as a fraction of account equity, in [-1, 1].  It is called just after a
  bar boundary and must only use bars that have already closed.
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
                df.to_parquet(path)
            except Exception as e:  # noqa: BLE001
                log.warning("could not write history cache: %s", e)
        return df.iloc[-bars:]

    def daily(self, ticker: str, lookback_days: int = 1200,
              cache_hours: float = 6.0) -> pd.DataFrame:
        """Daily OHLCV for a non-crypto series (HYG, LQD, ^GSPC, DX-Y.NYB, ...).

        Refreshes the shared `data/<ticker>_d.parquet` cache used by research when
        it is older than `cache_hours`, and falls back to the stale cache if the
        download fails -- a yfinance outage must not take a live strategy down.
        """
        os.makedirs(DATA_DIR, exist_ok=True)
        path = os.path.join(DATA_DIR, f"{ticker.replace('-', '_')}_d.parquet")
        fresh = os.path.exists(path) and (time.time() - os.path.getmtime(path)) < cache_hours * 3600
        if not fresh:
            try:
                import yfinance as yf
                start = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).date()
                new = yf.download(ticker, start=str(start), auto_adjust=True,
                                  progress=False, multi_level_index=False).dropna()
                if len(new):
                    if os.path.exists(path):
                        old = pd.read_parquet(path)
                        old.index = pd.to_datetime(old.index).tz_localize(None)
                        new.index = pd.to_datetime(new.index).tz_localize(None)
                        new = pd.concat([old[~old.index.isin(new.index)], new]).sort_index()
                    new.to_parquet(path)
            except Exception as e:  # noqa: BLE001 - stale data beats no data
                log.warning("daily(%s) refresh failed, using cache: %s", ticker, e)
        if not os.path.exists(path):
            raise FileNotFoundError(f"no data for {ticker} and download failed")
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df


# --------------------------------------------------------------------------- allocation

ALLOC_PATH = os.path.join(HARNESS_DIR, "state", "allocations.json")
DEFAULT_CAPITAL = 2_500.0


def _read_allocations() -> dict:
    if os.path.exists(ALLOC_PATH):
        try:
            with open(ALLOC_PATH) as fh:
                return json.load(fh)
        except Exception as e:  # noqa: BLE001
            log.warning("allocations file unreadable: %s", e)
    return {"pool_usdt": 10_000.0, "strategies": {}}


def _write_allocations(d: dict):
    os.makedirs(os.path.dirname(ALLOC_PATH), exist_ok=True)
    tmp = ALLOC_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(d, fh, indent=2)
    os.replace(tmp, ALLOC_PATH)


def allocate(name: str, capital_usdt: float = DEFAULT_CAPITAL) -> dict:
    """Reserve trading capital for a strategy, refusing to oversubscribe the pool.

    Capital is ALLOCATED, not divided: deploying or retiring a strategy never
    resizes the others.  Dividing account equity by the live strategy count would
    make every strategy churn its whole position -- and pay the spread -- each time
    an unrelated one came or went.
    """
    d = _read_allocations()
    others = {k: v for k, v in d["strategies"].items() if k != name}
    committed = sum(float(v["capital_usdt"]) for v in others.values())
    free = float(d["pool_usdt"]) - committed
    if capital_usdt > free + 1e-9:
        raise ValueError(
            f"cannot allocate {capital_usdt:.0f} USDT to {name}: pool is "
            f"{d['pool_usdt']:.0f}, {committed:.0f} already committed to "
            f"{len(others)} strategy(ies), {free:.0f} free. Retire a strategy, "
            f"lower the request, or raise pool_usdt in {ALLOC_PATH}.")
    d["strategies"][name] = {"capital_usdt": float(capital_usdt),
                             "allocated": datetime.now(timezone.utc).isoformat()}
    _write_allocations(d)
    return d


def release(name: str):
    d = _read_allocations()
    d["strategies"].pop(name, None)
    _write_allocations(d)


# --------------------------------------------------------------------------- broker


class PaperBroker:
    """Binance **spot testnet** account, driven by a target weight.

    Spot, long/flat, unlevered: `weight` is the fraction of THIS STRATEGY's capital
    held in the base asset, in [0, 1].  There is no shorting -- the spot testnet has
    no margin -- so a strategy that needs a negative weight cannot be deployed here.

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

    def __init__(self, symbol: str, capital_usdt: float = DEFAULT_CAPITAL,
                 max_weight: float = 1.0, slippage_bps: float = 1.0,
                 fee_bps: float = 10.0, force_shadow: bool = False,
                 state_file: Optional[str] = None, quote: str = "USDT",
                 resync_every_s: float = 900.0):
        load_env()
        self.symbol = symbol
        self.quote = quote
        self.base = symbol[:-len(quote)] if symbol.endswith(quote) else symbol[:-4]
        self.capital_usdt = float(capital_usdt)
        self.max_weight = float(max_weight)
        self.slippage_bps = float(slippage_bps)
        self.fee_bps = float(fee_bps)          # shadow-mode fee; the venue charges its own
        self.key, self.secret, self.key_source = _spot_credentials()
        self._time_offset = 0
        self._last_sync = 0.0
        self.resync_every_s = float(resync_every_s)
        self.shadow = bool(force_shadow)
        # the strategy's private book -- NOT the exchange account
        self._base_units = 0.0
        self._quote_units = float(capital_usdt)
        self.state_file = state_file           # persists the ledger across restarts
        self.step, self.min_qty, self.min_notional, self.qty_prec = 1e-5, 1e-5, 5.0, 5
        self._load_ledger()
        if not force_shadow:
            self._load_filters()
            self._sync_time()

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
                       "shadow": self.shadow,
                       "updated": datetime.now(timezone.utc).isoformat()}, fh, indent=2)
        os.replace(tmp, self.state_file)

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
        out = {"venue": BASE_URL, "market": "spot", "symbol": self.symbol,
               "shadow": self.shadow, "key_source": self.key_source,
               "capital_usdt": self.capital_usdt,
               "ledger": {"base": self._base_units, "quote": self._quote_units}}
        if self.shadow:
            out["reason"] = "forced shadow mode"
            return out
        if not self.key or not self.secret:
            self.shadow = True
            out["shadow"] = True
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
        self._save_ledger()
        return out

    # ---- state (all of it ledger-scoped, never account-wide)

    def mark_price(self) -> float:
        """Last traded price on the venue we actually fill against."""
        return float(_request(f"{BASE_URL}/api/v3/ticker/price?symbol={self.symbol}")["price"])

    def position(self) -> float:
        """This strategy's base holding, in base units."""
        return self._base_units

    def equity(self, price: Optional[float] = None) -> float:
        """This strategy's book: its quote units plus its base units at the mark."""
        px = price if price is not None else self.mark_price()
        return self._quote_units + self._base_units * px

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

    def _round_qty(self, qty: float) -> float:
        """Round DOWN to the lot step -- rounding up can exceed what we hold."""
        n = int(qty / self.step + 1e-9)
        return round(n * self.step, self.qty_prec)

    def set_target_weight(self, weight: float) -> dict:
        """Move this strategy's base holding to `weight` of its own book."""
        w = max(0.0, min(self.max_weight, float(weight)))
        px = self.mark_price()
        eq = self.equity(px)
        cur = self._base_units
        target_qty = self._round_qty(w * eq / px)
        delta = target_qty - cur
        rep = {"weight": w, "price": px, "equity": eq, "target_qty": target_qty,
               "current_qty": cur, "delta_qty": delta, "shadow": self.shadow,
               "market": "spot", "capital_usdt": self.capital_usdt, "traded": False}

        if abs(delta) < self.min_qty:
            rep["skipped"] = "below min qty"
            return rep
        # The venue rejects a trade under minNotional unless it liquidates the
        # holding outright -- let a full exit through, hold otherwise.
        closing = target_qty < self.min_qty and cur >= self.min_qty
        if abs(delta) * px < self.min_notional and not closing:
            rep["skipped"] = f"delta notional {abs(delta) * px:.2f} < {self.min_notional}"
            return rep

        side = "BUY" if delta > 0 else "SELL"
        qty = self._round_qty(abs(delta))

        if self.shadow:
            fill = px * (1 + (self.slippage_bps / 1e4) * (1 if delta > 0 else -1))
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

    def flatten(self) -> dict:
        return self.set_target_weight(0.0)

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
                 broker: Optional[PaperBroker] = None,
                 state_dir: Optional[str] = None,
                 offset_s: float = 20.0,
                 flatten_on_stop: bool = False,
                 max_consecutive_errors: int = 10):
        self.name = name
        self.symbol = symbol
        self.schedule = schedule
        self.compute_weight = compute_weight
        self.broker = broker or PaperBroker(symbol)
        self.offset_s = offset_s
        self.flatten_on_stop = flatten_on_stop
        self.max_consecutive_errors = max_consecutive_errors
        self.dir = state_dir or os.path.join(LIVE_DIR, name)
        os.makedirs(self.dir, exist_ok=True)
        if self.broker.state_file is None:
            self.broker.state_file = os.path.join(self.dir, "ledger.json")
            self.broker._load_ledger()
        self.journal_path = os.path.join(self.dir, "journal.jsonl")
        self.state_path = os.path.join(self.dir, "state.json")
        self._stop = threading.Event()
        self._setup_logging()

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

    def _save_state(self, **kw):
        state = {"strategy": self.name, "symbol": self.symbol, "schedule": self.schedule,
                 "pid": os.getpid(), "shadow": self.broker.shadow,
                 "updated": datetime.now(timezone.utc).isoformat(), **kw}
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(state, fh, indent=2, default=str)
        os.replace(tmp, self.state_path)

    # ---- loop

    def _handle_signal(self, signum, _frame):
        log.info("signal %s received, shutting down", signum)
        self._stop.set()

    def step_once(self, now: Optional[datetime] = None) -> dict:
        now = now or datetime.now(timezone.utc)
        w = float(self.compute_weight(now))
        if w != w:  # NaN
            raise ValueError("compute_weight returned NaN")
        rep = self.broker.set_target_weight(w)
        self._journal({"event": "rebalance", **rep})
        self._save_state(last_weight=rep["weight"], last_price=rep.get("price"),
                         equity=rep.get("equity"), position=self.broker.position(),
                         capital_usdt=self.broker.capital_usdt,
                         last_run=now.isoformat())
        log.info("w=%.4f px=%.2f eq=%.2f pos=%.6f traded=%s%s",
                 rep["weight"], rep.get("price", 0), rep.get("equity", 0),
                 rep.get("target_qty", 0), rep.get("traded"),
                 " SHADOW" if rep.get("shadow") else "")
        return rep

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
               "shadow": pf.get("shadow"), "venue": BASE_URL}
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
            self.step_once()
            return
        self.run()

    def run(self, run_immediately: bool = True):
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        pf = self.broker.preflight()
        log.info("starting %s on %s spot (%s) -- %s", self.name, self.symbol,
                 self.schedule, "SHADOW" if pf.get("shadow") else "LIVE PAPER")
        self._journal({"event": "start", **pf})
        self._save_state(status="running", preflight=pf)

        errors = 0
        if run_immediately:
            try:
                self.step_once()
                errors = 0
            except Exception as e:  # noqa: BLE001
                errors += 1
                log.exception("initial step failed")
                self._journal({"event": "error", "error": repr(e)})

        while not self._stop.is_set():
            nxt = next_boundary(self.schedule, offset_s=self.offset_s)
            wait = max(1.0, (nxt - datetime.now(timezone.utc)).total_seconds())
            log.info("sleeping %.0fs until %s", wait, nxt.isoformat())
            if self._stop.wait(wait):
                break
            try:
                self.step_once(nxt)
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
