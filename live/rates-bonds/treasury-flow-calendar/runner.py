"""
Live (paper) runner for treasury-flow-calendar -- TLT long/short on three Treasury flow calendars.

Spec:   alphas/rates-bonds/treasury-flow-calendar/spec.md
Signal: code/rates-bonds/treasury-flow-calendar/strategy.py :: target_weight()   (imported, not restated)

TLT is not a crypto pair and the strategy goes short, so it trades in the SIM book:
SimBroker("TLT", allow_short=True), unlevered (|weight| <= 1), marked and filled at the
yfinance daily close from the shared data/ cache -- the same close research_lib.backtest
charged turnover at. There is no order book behind this track; it is weaker evidence than
a venue fill and must be read as such.

Timing. target_weight(close)[t] is the weight held from close_t to close_{t+1}. The runner
wakes at 00:00 UTC, which is always after the NYSE close (20:00 UTC EDT / 21:00 UTC EST)
and before the next open, so the last cached bar is a finished session. It acts only when
that bar changes (YahooQuotes.bar_key), so weekends and holidays are no-ops. A restart
during US trading hours could pull yfinance's still-forming bar for today; compute_weight
refuses that bar rather than trade a mid-session price as if it were the close.

Calendars. FOMC dates come from the committed snapshot (through 2027-12-08). Auction dates
are the committed snapshot UNION the auctions TreasuryDirect has announced
(`securities/upcoming`), which the spec allows via `auction_dates=` and requires ("refresh
monthly") -- without it the short leg goes silently flat once the snapshot runs out
(its last 10y/20y date is 2026-09-17). Announced dates are persisted to the data/ cache so
an endpoint outage does not forget one. Upcoming only lists announced auctions, so this
adds no lookahead.

Cost. The research charges 2 bp per unit of turnover, all-in. SimBroker charges slippage
plus fee on each fill, so the book is built with 1 bp + 1 bp -- NOT the 10 bp crypto
default, at which the report's own cost ladder puts Sharpe at 0.60.
"""
import json
import logging
import os
import sys
from zoneinfo import ZoneInfo

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(REPO, "code", "rates-bonds", "treasury-flow-calendar"))

import calendars  # noqa: E402
from live_lib import MarketData, SimBroker, StrategyRunner, daily_cache_path  # noqa: E402
from strategy import default_auction_dates, default_fomc_dates, target_weight  # noqa: E402

log = logging.getLogger(__name__)

NAME = "rates-bonds/treasury-flow-calendar"
SYMBOL = "TLT"
SCHEDULE = "1d"
# This strategy's own book (sim, uncapped). See live_lib.allocate().
CAPITAL_USDT = 2_500.0
# Research cost: 2 bp/side all-in (backtest_calendar / final.py, COST = 2.0).
SLIPPAGE_BPS = 1.0
FEE_BPS = 1.0
# The signal has no price lookback -- only the trading-day index is used (month-end ranks
# within the month, day-before offsets). 250 bars is a sanity floor, not a requirement.
MIN_BARS = 250
TENORS = ("10y", "20y")          # spec: tenors=("10y","20y"), reopenings included
NY = ZoneInfo("America/New_York")
SEEN_PATH = os.path.join(os.path.dirname(daily_cache_path(SYMBOL)), "treasury_auctions_seen_live.csv")

md = MarketData(source="public")


def live_auction_dates() -> pd.DatetimeIndex:
    """Committed snapshot + every 10y/20y auction TreasuryDirect has announced so far."""
    dates = set(default_auction_dates(TENORS))
    seen = set()
    if os.path.exists(SEEN_PATH):
        seen = set(pd.to_datetime(pd.read_csv(SEEN_PATH)["auction_date"]))
    try:
        up = json.loads(calendars._get(calendars.TD_UPCOMING, timeout=30))
        new = {pd.Timestamp(x["auctionDate"][:10]) for x in up
               if x.get("securityType") in ("Note", "Bond")
               and calendars.tenor_of(x.get("securityTerm")) in TENORS}
        if not new <= seen:
            seen |= new
            tmp = SEEN_PATH + ".tmp"
            pd.DataFrame({"auction_date": sorted(seen)}).to_csv(tmp, index=False)
            os.replace(tmp, SEEN_PATH)
    except Exception as e:  # noqa: BLE001 - keep trading on what is already known
        log.warning("TreasuryDirect upcoming auctions unavailable, using snapshot + cache: %s", e)
    return pd.DatetimeIndex(sorted(dates | seen))


def compute_weight(now):
    """Target TLT weight to hold from the last close to the next, per spec.md."""
    close = md.daily(SYMBOL, cache_hours=1.0)["Close"].dropna()
    close = close[~close.index.duplicated(keep="last")].sort_index()
    if len(close) < MIN_BARS:
        raise RuntimeError(f"only {len(close)} daily {SYMBOL} bars; need >= {MIN_BARS}")

    last = close.index[-1]
    now_ny = pd.Timestamp(now).tz_convert(NY)
    if last.date() == now_ny.date() and (now_ny.hour, now_ny.minute) < (16, 30):
        raise RuntimeError(f"{SYMBOL} bar {last.date()} is still forming "
                           f"({now_ny:%H:%M} New York); waiting for the close")
    if (now_ny.tz_localize(None).normalize() - last).days > 6:
        raise RuntimeError(f"{SYMBOL} last bar {last.date()} is stale -- data feed down?")

    auctions = live_auction_dates()
    fomc = default_fomc_dates()
    if fomc.max() < now_ny.tz_localize(None) + pd.Timedelta(days=60):
        log.warning("FOMC snapshot ends %s -- refresh calendars.py or the FOMC leg goes flat",
                    fomc.max().date())
    if auctions.max() < last:
        log.warning("no 10y/20y auction known after %s -- the short leg is flat until "
                    "TreasuryDirect announces the next one", auctions.max().date())

    w = target_weight(close, fomc_dates=fomc, auction_dates=auctions)
    return float(w.iloc[-1])


if __name__ == "__main__":
    StrategyRunner(
        name=NAME,
        symbol=SYMBOL,
        schedule=SCHEDULE,
        compute_weight=compute_weight,
        broker=SimBroker(SYMBOL, capital_usdt=CAPITAL_USDT, max_weight=1.0,
                         allow_short=True, slippage_bps=SLIPPAGE_BPS, fee_bps=FEE_BPS),
        offset_s=20.0,
    ).cli()
