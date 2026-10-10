"""
Live (paper) runner for rates-bonds/cef-discount-reversion -- dollar-neutral long/short of
bond closed-end funds on the short-term dislocation of their discount to NAV.

Spec:   alphas/rates-bonds/cef-discount-reversion/spec.md
Signal: code/rates-bonds/cef-discount-reversion/strategy.py :: target_weights()
        (imported with its spec DEFAULTS, not restated)

Book. A long/SHORT basket of ~16-34 of ~170 closed-end funds, net 0, gross <= 1.0, so it
trades in the SIM book: SimPortfolioBroker, allow_short=True, max_gross=1.0 -- the gross the
research validated and the strategy's own cap (nothing above 1.0 was tested). The fund list
is a snapshot that decays as funds merge or liquidate, so the broker is `open_universe=True`:
a ledger written under an older list resumes instead of restarting. No order book, no
rejection, no partial fill and -- the one that matters here -- NO BORROW: the sim book
shorts any closed-end fund freely and for nothing. Weaker evidence than a venue fill, and it
must be read as such.

Data. Per the spec's deployment notes the panel `data/CEF_BOND_panel_d.parquet` is rebuilt
with the research fetcher `fetch_cef.build_panel()` (two yfinance batches: fund prices and
the `X<T>X` NAV tickers, ~2 min) and read back with `strategy.load_inputs()`, full history,
exactly as 07_selected.py backtested it. Nothing is rebuilt between 09:00 and 17:00 New York
on a weekday, and every input is cut at the bar, so a forming session is never traded.

Timing. target_weights row t is the weight held close_t -> close_{t+1} and already carries
the one-session NAV-publication skip: it uses prices and NAVs up to close t-1 only. The
daemon wakes at 00:00:20 UTC -- after the NYSE close in EDT and EST -- and trades row `bar`
at the `bar` close. No extra lag is added here: the report loses half its Sharpe to two more
sessions of delay.

Bar. `bar_key` is NOT the harness's min-over-legs: with ~170 thin legs one halted fund would
freeze the book. The book's bar is the latest panel session on which
  * at least MIN_FUNDS funds printed a close (a failed yfinance chunk drops 40 at once), and
  * the SIGNAL session before it (t-1) has a NAV for >= NAV_COVERAGE of the funds that
    printed -- a NAV Yahoo has not posted yet reads as "no discount", which resets that
    fund's state to flat and would close real positions on a data gap.
Until both hold the bar does not advance and the daemon re-checks every 30 min. These two
thresholds are runner data-quality guards, not strategy parameters.

Marks. Every leg is marked at the panel's dividend-adjusted close on the bar (its last one
before it for a halted fund) -- the series the backtest took returns from; on the latest
bar it equals the traded close.

Cost. The research charges 10 bp per side on every trade, all-in, so the broker is built
with fee_bps=10, slippage_bps=0. Report ladder (IS / OOS): 5 bp 2.96 / 2.88, 10 bp
2.71 / 2.49, 20 bp 2.20 / 1.71, 30 bp 1.69 / 0.91.
"""
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(REPO, "code", "rates-bonds", "cef-discount-reversion"))

from portfolio import PortfolioRunner, SimPortfolioBroker  # noqa: E402
import strategy as S  # noqa: E402  (code/rates-bonds/cef-discount-reversion/strategy.py)

log = logging.getLogger(__name__)

NAME = "rates-bonds/cef-discount-reversion"
SCHEDULE = "1d"
OFFSET_S = 20.0                    # 00:00:20 UTC -- after the NYSE close in EDT and EST
# This strategy's own book (sim, uncapped). See live_lib.allocate().
CAPITAL_USDT = 2_500.0
# Research cost: 10 bp per side, all-in, on every trade (spec "Cost assumed").
FEE_BPS = 10.0
SLIPPAGE_BPS = 0.0
MAX_GROSS = 1.0                    # spec: gross <= 1.0 (0.5 long + 0.5 short), validated max
MIN_FUNDS = 150                    # funds that must have printed the bar (170 at deploy)
NAV_COVERAGE = 0.95                # share of them with a NAV on the signal session (t-1)
MIN_BARS = 500                     # spec: feed at least 500 sessions
REBUILD_EVERY_S = 6 * 3600         # panel rebuild while the bar is complete
RETRY_EVERY_S = 20 * 60            # ... and while the vendor is late
NY = ZoneInfo("America/New_York")


# --------------------------------------------------------------------------- the panel

_state = {"bar": None, "bar_t": 0.0, "try_t": 0.0, "trade_bar": None}
_inputs_memo = {}                  # panel mtime -> load_inputs()


def _in_session(now_ny):
    return now_ny.weekday() < 5 and 9 <= now_ny.hour < 17


def _rebuild():
    """The research fetcher, as the spec prescribes. A failure keeps the old panel."""
    _state["try_t"] = time.time()
    t0 = time.time()
    try:
        import fetch_cef
        p = fetch_cef.build_panel()
        log.info("panel rebuilt (%.0fs): %d funds to %s", time.time() - t0,
                 p["ticker"].nunique(), pd.Timestamp(p["date"].max()).date())
    except Exception as e:  # noqa: BLE001 - stale data beats no data; staleness is checked
        log.warning("panel rebuild failed after %.0fs: %r", time.time() - t0, e)


def _inputs():
    """(close, nav, volume, group, adj_close) from the research loader, memoised by mtime."""
    mt = os.path.getmtime(S.PANEL)
    if mt not in _inputs_memo:
        _inputs_memo.clear()
        _inputs_memo[mt] = S.load_inputs()
    return _inputs_memo[mt]


def _complete_bar(close, nav, sessions):
    """Latest of `sessions` that enough funds printed and whose signal session has its NAVs."""
    idx = close.index
    for day in sessions[::-1][:5]:
        i = idx.get_loc(day)
        if i == 0:
            break
        printed = int(close.iloc[i].notna().sum())
        sig = close.iloc[i - 1].notna()
        navs = int((nav.iloc[i - 1].notna() & sig).sum())
        if printed >= MIN_FUNDS and navs >= NAV_COVERAGE * max(int(sig.sum()), 1):
            return day
        log.info("bar %s incomplete: %d funds printed (need %d), %d/%d NAVs on %s",
                 day.date(), printed, MIN_FUNDS, navs, int(sig.sum()), idx[i - 1].date())
    return None


def current_bar(now=None, max_age_s=600.0) -> str:
    """The session the book is on: see "Bar" in the module docstring."""
    if _state["bar"] and time.time() - _state["bar_t"] < max_age_s:
        return _state["bar"]
    now_ny = pd.Timestamp(now or datetime.now(timezone.utc)).tz_convert(NY)
    today = now_ny.tz_localize(None).normalize()
    in_session = _in_session(now_ny)

    def _find():
        close, nav = _inputs()[:2]
        sessions = close.index[close.index < today] if in_session else close.index
        return _complete_bar(close, nav, sessions), sessions[-1]

    if not os.path.exists(S.PANEL):
        _rebuild()
    bar, last = _find()
    if not in_session:
        age = time.time() - os.path.getmtime(S.PANEL)
        late = bar is None or bar < last
        since_try = time.time() - _state["try_t"]
        if (age > REBUILD_EVERY_S and since_try > RETRY_EVERY_S) or (late and since_try > RETRY_EVERY_S):
            _rebuild()
            bar, last = _find()
    if bar is None:
        raise RuntimeError(f"no complete session in the last 5 (panel ends {last.date()}) -- "
                           f"yfinance down or NAV tickers not posting?")
    if bar < last:
        log.info("holding at %s: %s is not complete yet", bar.date(), last.date())
    _state.update(bar=bar.date().isoformat(), bar_t=time.time())
    return _state["bar"]


class CefBook(SimPortfolioBroker):
    """SimPortfolioBroker over the bond-CEF universe, clocked and marked from the panel.

    `bar_key` and `prices` are the only overrides: the bar is `current_bar()`, and every
    leg is marked at its dividend-adjusted panel close ON that bar (or its last one before
    it, for a halted or merged fund).
    """

    def bar_key(self):
        return current_bar()

    def prices(self):
        bar = pd.Timestamp(_state["trade_bar"] or current_bar())
        adj = _inputs()[4].loc[:bar]
        last = adj.ffill().iloc[-1]
        out = {}
        for s in self.symbols:
            px = float(last.get(s, float("nan")))
            if not px > 0:
                raise RuntimeError(f"{s}: no positive adjusted close on or before {bar.date()}")
            out[s] = px
        return out


# --------------------------------------------------------------------------- the signal

def compute_weights(now):
    """Target weights to hold from the `bar` close to the next, per spec.md."""
    bar = pd.Timestamp(current_bar(now))
    _state["trade_bar"] = bar.date().isoformat()
    now_ny = pd.Timestamp(now).tz_convert(NY).tz_localize(None)
    if (now_ny.normalize() - bar).days > 6:
        raise RuntimeError(f"bar {bar.date()} is stale -- data feed down?")

    close, nav, volume, group, _ = _inputs()
    close, nav, volume = close.loc[:bar], nav.loc[:bar], volume.loc[:bar]
    if close.index[-1] != bar:
        raise RuntimeError(f"panel ends {close.index[-1].date()}, expected {bar.date()}")
    if len(close) < MIN_BARS:
        raise RuntimeError(f"only {len(close)} sessions; the spec needs >= {MIN_BARS}")

    W = S.target_weights(close, nav, volume, group)        # spec DEFAULTS, signal_lag=1
    row = W.loc[bar]
    if row.isna().any():
        raise RuntimeError(f"NaN weights on {bar.date()}: {row[row.isna()].index.tolist()[:10]}")
    out = {t: float(v) for t, v in row.items() if v != 0.0}
    for t in BOOK.symbols:                       # close anything the book holds but the row drops
        out.setdefault(t, 0.0)
    log.info("bar %s: %d long / %d short, gross %.3f, net %+.4f", bar.date(),
             sum(1 for v in out.values() if v > 0), sum(1 for v in out.values() if v < 0),
             sum(abs(v) for v in out.values()), sum(out.values()))
    return out


def _held():
    try:
        with open(os.path.join(HERE, "ledger.json")) as fh:
            return [s for s, q in json.load(fh).get("positions", {}).items() if q]
    except Exception:  # noqa: BLE001 - no ledger yet
        return []


def _initial_symbols():
    if not os.path.exists(S.PANEL):
        _rebuild()
    # A fund listed for fewer than the strategy's own `min_hist` sessions cannot be eligible
    # (FSSL at deploy); open_universe adds it if it ever earns a weight.
    adj = _inputs()[4]
    priced = adj.columns[adj.notna().sum() >= S.DEFAULTS["min_hist"]]
    return sorted((set(priced) - set(S.EXCLUDE)) | set(_held()))


SYMBOLS = _initial_symbols()
BOOK = CefBook(SYMBOLS, capital_usdt=CAPITAL_USDT, max_gross=MAX_GROSS, allow_short=True,
               fee_bps=FEE_BPS, slippage_bps=SLIPPAGE_BPS, open_universe=True)

if __name__ == "__main__":
    PortfolioRunner(
        name=NAME,
        symbols=SYMBOLS,
        schedule=SCHEDULE,
        compute_weights=compute_weights,
        broker=BOOK,
        offset_s=OFFSET_S,
    ).cli()
