"""
Live (paper) runner for `us-large-cap/large-cap-sleeve-blend` -- four uncorrelated S&P 500
market-neutral sleeves (residual momentum, PIT fundamental quality, 10-K/10-Q text
similarity, short post-inclusion reversal) summed at fixed IS-vol multipliers.

Spec:   alphas/us-large-cap/large-cap-sleeve-blend/spec.md
Signal: code/us-large-cap/large-cap-sleeve-blend/strategy.py :: blend_weights(panel_inputs())
        (imported with its spec defaults, not restated)

Book. A long/SHORT book of ~500 single names at gross ~4.4 (validated max 6.29), so it
trades in the SIM book. The universe is the point-in-time S&P 500, which changes every
month, so the broker is a SimPortfolioBroker with `open_universe=True`: weights may name
a symbol the book has not held before (a new addition), and a ledger written under an
older member list resumes instead of restarting. max_gross=6.3, the validated maximum;
the strategy never asked for more over 2011-2026, so the cap is a backstop, not a rule.
Fills are at the daily close from the shared `data/` cache -- the same close the research
charged turnover at. No order book, no borrow, no short-rebate and no margin interest sit
behind this track: weaker evidence than a venue fill, and it must be read as such.

Bar. `bar_key` is NOT the harness's min-over-legs: with ~600 legs, one halted or acquired
name would freeze the book forever. The book's bar is the latest SPY session that >= 98 %
of current S&P 500 members have printed in the cache. Until the cross-section is that
complete the bar does not advance, so a late vendor is a re-check (every 30 min), not a
rebalance on a partial panel. No data is refreshed between 09:00 and 17:00 New York on a
weekday, and every input is cut at the bar, so a still-forming session is never traded.

Timing. blend_weights row t is the weight held close_t -> close_{t+1}, computed from data
known at close t (fundamentals and filings from the first session after their filing
date; REC shorts an addition at the close of its first session in the index). The daemon
wakes at 00:00:20 UTC -- after the NYSE close in EDT and EST -- refreshes the data, and
trades row `bar` at the `bar` close.

Data. Everything the spec lists is refreshed live, by the research's own fetchers:
  * membership / changes / sectors -- fetch_sp500_changes.py (Wikipedia), every 6 h;
  * prices -- fetch_universe.py --refresh for current members, held names, and any
    panel name still printing (full re-download, as the research's truncation test did);
  * splits/dividends, EDGAR companyfacts, EDGAR filing text -- fetch_actions.py,
    fetch_xbrl.py --refresh, fetch_filing_text.py --update, once per traded bar.
The membership CSVs live in data/us-large-cap-live/ (untracked), NOT in the tracked
code/us-large-cap/shared/ copies the research ships: a daemon rewriting tracked files would
dirty the main tree under every research agent. The runner points `universe`, `fetch_xbrl`
and the REC changes table there. The EDGAR raw caches live in data/SP500_edgar/ rather than
the fetchers' /tmp defaults, which do not survive a cleanup.

Cost. The research charges 5 bp per side on sum|dw|, all-in. The broker is built with
fee_bps=5, slippage_bps=0. Research ladder: 2 bp -> 1.12 / 0.89 OOS, 5 bp -> 1.03 / 0.81,
10 bp -> 0.88 / 0.69.
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
UL = os.path.join(REPO, "code", "us-large-cap")
SHARED = os.path.join(UL, "shared")
LIVE_UNIVERSE = os.path.join(REPO, "data", "us-large-cap-live")
EDGAR = os.path.join(REPO, "data", "SP500_edgar")
os.environ.setdefault("AQ_XBRL_RAW", os.path.join(EDGAR, "companyfacts"))
os.environ.setdefault("AQ_FILING_TMP", os.path.join(EDGAR, "filing_sim"))

sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(REPO, "code", "shared"))
sys.path.insert(0, SHARED)
sys.path.insert(0, os.path.join(UL, "quality-value-composite"))
sys.path.insert(0, os.path.join(UL, "large-cap-sleeve-blend"))

log = logging.getLogger(__name__)

NAME = "us-large-cap/large-cap-sleeve-blend"
SCHEDULE = "1d"
OFFSET_S = 20.0                    # 00:00:20 UTC -- after the NYSE close in EDT and EST
# This strategy's own book (sim, uncapped). See live_lib.allocate().
CAPITAL_USDT = 2_500.0
# Research cost: 5 bp per side, all-in, on sum|dw| (spec "Cost assumed").
FEE_BPS = 5.0
SLIPPAGE_BPS = 0.0
MAX_GROSS = 6.3                    # validated maximum gross 6.29 (calibrate.py)
# A $2,500 book spread over ~500 names holds ~$20 a leg; the harness default of skipping
# trades under $1 would ignore most daily hedge re-sizes. 5 cents is 0.2 bp of capital.
MIN_TRADE_USD = 0.05
CLOCK = "SPY"                      # session clock only; never traded
COVERAGE = 0.98                    # share of current members that must have printed the bar
UNIVERSE_FILES = ("sp500_current_raw.csv", "sp500_changes_raw.csv", "sp500_ticker_start_end.csv")
MEMBERSHIP_EVERY_S = 6 * 3600
PRICES_EVERY_S = 20 * 60
FETCH_TIMEOUT_S = {"actions": 30 * 60, "xbrl": 60 * 60, "filings": 90 * 60, "changes": 5 * 60}
MAX_EDGAR_AGE_DAYS = 7             # refuse to trade on fundamentals/filings older than this
NY = ZoneInfo("America/New_York")


# --------------------------------------------------------------------------- data location

def _seed_live_universe():
    """First run: start the live membership copy from the research's tracked files."""
    os.makedirs(LIVE_UNIVERSE, exist_ok=True)
    for f in UNIVERSE_FILES:
        dst = os.path.join(LIVE_UNIVERSE, f)
        if not os.path.exists(dst):
            shutil.copy2(os.path.join(SHARED, f), dst)
    for env, tmp in (("AQ_XBRL_RAW", "/tmp/sec_companyfacts"), ("AQ_FILING_TMP", "/tmp/filing_sim")):
        dst = os.environ[env]
        if not os.path.isdir(dst):
            if os.path.isdir(tmp):
                shutil.copytree(tmp, dst)
            else:
                os.makedirs(dst, exist_ok=True)


def _point_at_live_universe():
    """Make the research modules read (never write) the live membership copy."""
    import universe
    universe.HERE = LIVE_UNIVERSE
    try:
        import fetch_xbrl
        fetch_xbrl.HERE = LIVE_UNIVERSE
    except ImportError:
        pass


_seed_live_universe()
_point_at_live_universe()

from live_lib import MarketData, daily_cache_path  # noqa: E402
from portfolio import PortfolioRunner, SimPortfolioBroker  # noqa: E402
import universe  # noqa: E402
import strategy as blend  # noqa: E402  (code/us-large-cap/large-cap-sleeve-blend/strategy.py)

# REC reads the changes table through a default argument bound at import time.
blend._rec.load_changes.__defaults__ = (os.path.join(LIVE_UNIVERSE, "sp500_changes_raw.csv"),)

md = MarketData(source="public")   # used only for the SPY clock in the shared daily cache


# --------------------------------------------------------------------------- fetchers

def _run_fetcher(which: str):
    """`runner.py --fetch <which>`: one research fetcher, pointed at the live universe."""
    if which == "changes":
        import fetch_sp500_changes as m
        sys.argv = ["fetch_sp500_changes.py", "--out-dir", LIVE_UNIVERSE]
    elif which == "prices":
        import fetch_universe as m
        sys.argv = ["fetch_universe.py", os.path.join(LIVE_UNIVERSE, "refresh_tickers.txt"), "--refresh"]
    elif which == "actions":
        import fetch_actions as m
        sys.argv = ["fetch_actions.py"]
    elif which == "xbrl":
        import fetch_xbrl as m
        sys.argv = ["fetch_xbrl.py", "--refresh"]
    elif which == "filings":
        import fetch_filing_text as m
        sys.argv = ["fetch_filing_text.py", "--update", "--workers", "10"]
    else:
        raise SystemExit(f"unknown fetcher {which!r}")
    _point_at_live_universe()
    m.main()


def _fetch(which: str) -> bool:
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--fetch", which],
                           capture_output=True, text=True,
                           timeout=FETCH_TIMEOUT_S.get(which, 30 * 60))
    except subprocess.TimeoutExpired:
        log.warning("fetch %s timed out after %.0fs", which, time.time() - t0)
        return False
    tail = " | ".join((r.stdout or "").strip().splitlines()[-2:])
    if r.returncode != 0:
        log.warning("fetch %s failed (rc %d, %.0fs): %s", which, r.returncode, time.time() - t0,
                    (r.stderr or "").strip().splitlines()[-1:] or tail)
        return False
    log.info("fetch %s ok (%.0fs): %s", which, time.time() - t0, tail)
    return True


# --------------------------------------------------------------------------- the bar

_state = {"membership_t": 0.0, "prices_t": 0.0, "bar": None, "bar_t": 0.0, "edgar_bar": None,
          "trade_bar": None}
_last_bar_memo = {}                # ticker -> (file mtime, last bar)


def _last_bar(ticker):
    p = daily_cache_path(ticker)
    if not os.path.exists(p):
        return None
    mt = os.path.getmtime(p)
    hit = _last_bar_memo.get(ticker)
    if hit and hit[0] == mt:
        return hit[1]
    idx = pd.read_parquet(p, columns=["Close"]).dropna().index
    lb = pd.Timestamp(idx[-1]).tz_localize(None).normalize() if len(idx) else None
    _last_bar_memo[ticker] = (mt, lb)
    return lb


def _members_at(day):
    d = universe.load_spans()
    live = (d.start_date <= day) & (d.end_date.isna() | (d.end_date > day))
    return sorted(set(d.ticker[live]))


def _in_session(now_ny):
    return now_ny.weekday() < 5 and 9 <= now_ny.hour < 17


def _held():
    try:
        with open(os.path.join(HERE, "ledger.json")) as fh:
            return [s for s, q in json.load(fh).get("positions", {}).items() if q]
    except Exception:  # noqa: BLE001 - no ledger yet
        return []


def _refresh(now_ny, clock):
    """Membership every 6 h; prices for every name that has not printed the clock bar."""
    t = time.time()
    if t - _state["membership_t"] > MEMBERSHIP_EVERY_S:
        _fetch("changes")          # a failure keeps yesterday's table; logged
        _state["membership_t"] = t
    if t - _state["prices_t"] < PRICES_EVERY_S:
        return
    _state["prices_t"] = t
    alive = []
    for tk in universe.all_tickers_since("2010-01-01"):
        lb = _last_bar(tk)
        if lb is not None and (clock - lb).days <= 10:
            alive.append(tk)
    want = sorted(set(_members_at(clock)) | set(_held()) | set(alive))
    stale = [tk for tk in want if (_last_bar(tk) or pd.Timestamp(0)) < clock]
    if stale:
        with open(os.path.join(LIVE_UNIVERSE, "refresh_tickers.txt"), "w") as fh:
            fh.write("\n".join(stale))
        log.info("refreshing %d of %d price files to %s", len(stale), len(want), clock.date())
        _fetch("prices")


def current_bar(now=None, max_age_s=600.0) -> str:
    """Latest SPY session that >= COVERAGE of that day's members have printed."""
    if _state["bar"] and time.time() - _state["bar_t"] < max_age_s:
        return _state["bar"]
    now_ny = pd.Timestamp(now or datetime.now(timezone.utc)).tz_convert(NY)
    today = now_ny.tz_localize(None).normalize()
    spy = md.daily(CLOCK, cache_hours=0.25) if not _in_session(now_ny) else md.daily(CLOCK, cache_hours=1e9)
    sessions = spy.index.normalize()
    if _in_session(now_ny):
        sessions = sessions[sessions < today]              # today's bar is still forming
    clock = sessions[-1]
    if not _in_session(now_ny):
        _refresh(now_ny, clock)
    for day in sessions[::-1][:5]:
        mem = _members_at(day)
        have = sum(1 for tk in mem if (_last_bar(tk) or pd.Timestamp(0)) >= day)
        cov = have / max(len(mem), 1)
        if cov >= COVERAGE:
            if day < clock:
                log.info("bar %s: only %.1f%% of members printed %s yet; holding at %s",
                         clock.date(), 100 * cov, clock.date(), day.date())
            _state.update(bar=day.date().isoformat(), bar_t=time.time())
            return _state["bar"]
        log.info("coverage %s: %d/%d members (%.1f%%)", day.date(), have, len(mem), 100 * cov)
    raise RuntimeError(f"no session in the last 5 has {COVERAGE:.0%} member coverage -- "
                       f"price refresh broken?")


class LargeCapBook(SimPortfolioBroker):
    """SimPortfolioBroker over an open S&P 500 universe, clocked by member coverage.

    `bar_key` and `prices` are the only overrides: the bar is `current_bar()`, and every
    leg is marked at its cached close ON that bar (or its last close before it, for a
    halted or acquired name) -- the same close the weights were computed from.
    """

    def bar_key(self):
        return current_bar()

    def prices(self):
        # The bar the weights were computed on, not whatever the clock says a few
        # minutes later after the EDGAR refresh.
        bar = pd.Timestamp(_state["trade_bar"] or current_bar())
        memo = getattr(self, "_px_memo", None)
        if memo is None or memo[0] != bar:
            memo = self._px_memo = (bar, {})
        out = {}
        for s in self.symbols:
            if s not in memo[1]:
                p = daily_cache_path(s)
                if not os.path.exists(p):
                    raise RuntimeError(f"no cached prices for {s}")
                c = pd.read_parquet(p, columns=["Close"])["Close"].dropna()
                c.index = pd.to_datetime(c.index).tz_localize(None)
                c = c.loc[:bar]
                if c.empty or not c.iloc[-1] > 0:
                    raise RuntimeError(f"{s}: no positive close on or before {bar.date()}")
                memo[1][s] = float(c.iloc[-1])
            out[s] = memo[1][s]
        return out


# --------------------------------------------------------------------------- the signal

def _refresh_edgar(bar):
    """Splits/dividends and both EDGAR stores, once per traded bar (spec: before each close)."""
    if _state["edgar_bar"] == bar:
        return
    for which in ("actions", "xbrl", "filings"):
        _fetch(which)                                  # a failure is logged; age checked below
    _state["edgar_bar"] = bar
    for f in ("SP500_xbrl_facts.parquet", "SP500_filing_similarity.parquet", "SP500_actions.parquet"):
        p = os.path.join(REPO, "data", f)
        age = (time.time() - os.path.getmtime(p)) / 86400
        if age > MAX_EDGAR_AGE_DAYS:
            raise RuntimeError(f"{f} is {age:.1f} days old -- its fetcher has been failing")


def compute_weights(now):
    """Target weights to hold from the `bar` close to the next, per spec.md."""
    bar = pd.Timestamp(current_bar(now))
    _state["trade_bar"] = bar.date().isoformat()
    now_ny = pd.Timestamp(now).tz_convert(NY).tz_localize(None)
    if (now_ny.normalize() - bar).days > 6:
        raise RuntimeError(f"bar {bar.date()} is stale -- data feed down?")
    if not _in_session(pd.Timestamp(now).tz_convert(NY)):
        _refresh_edgar(bar.date().isoformat())

    X = blend.panel_inputs()
    X = {k: (v.loc[:bar] if k != "sector" else v) for k, v in X.items()}
    if X["close"].index[-1] != bar:
        raise RuntimeError(f"panel ends {X['close'].index[-1].date()}, expected {bar.date()}")
    W = blend.blend_weights(X)
    row = W.loc[bar]
    if row.isna().any():
        raise RuntimeError(f"NaN weights on {bar.date()}: {row[row.isna()].index.tolist()[:10]}")
    out = {t: float(v) for t, v in row.items() if v != 0.0}
    for t in BOOK.symbols:                       # close anything the book holds but the row drops
        out.setdefault(t, 0.0)
    log.info("bar %s: %d names, gross %.2f, net %+.3f", bar.date(), sum(1 for v in out.values() if v),
             sum(abs(v) for v in out.values()), sum(out.values()))
    return out


def _initial_symbols():
    # A member without a price file is not in the research panel either (e.g. FI: the
    # FISV->FI alias points at a ticker yfinance no longer carries), so it can never get
    # a weight; leaving it out keeps `prices()` from failing on it.
    day = pd.Timestamp.now().normalize()
    mem = [t for t in _members_at(day) if os.path.exists(daily_cache_path(t))]
    return sorted(set(mem) | set(_held()))


if __name__ == "__main__" and len(sys.argv) > 2 and sys.argv[1] == "--fetch":
    _run_fetcher(sys.argv[2])
    sys.exit(0)

SYMBOLS = _initial_symbols()
BOOK = LargeCapBook(SYMBOLS, capital_usdt=CAPITAL_USDT, max_gross=MAX_GROSS, allow_short=True,
                    fee_bps=FEE_BPS, slippage_bps=SLIPPAGE_BPS, min_trade_usd=MIN_TRADE_USD,
                    open_universe=True)

if __name__ == "__main__":
    PortfolioRunner(
        name=NAME,
        symbols=SYMBOLS,
        schedule=SCHEDULE,
        compute_weights=compute_weights,
        broker=BOOK,
        offset_s=OFFSET_S,
    ).cli()
