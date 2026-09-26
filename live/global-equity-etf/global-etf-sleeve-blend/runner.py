"""
Live (paper) runner for `global-equity-etf/global-etf-sleeve-blend` -- 0.67 x the slow
US-vs-rest-of-world relative trend book (market-neutral country spreads vs SPY, month-end)
+ 0.87 x the FOMC sleeve (long the EW country basket over FOMC day -1 and day 0), on the
9 country iShares ETFs + SPY.

Spec:   alphas/global-equity-etf/global-etf-sleeve-blend/alpha.md
Signal: code/global-equity-etf/global-etf-sleeve-blend/strategy.py :: target_weights()
        (imported with its spec defaults, not restated)

Book. A long/SHORT basket with gross averaging 1.41x and reaching 3.00x in the backtest, so
it trades in the SIM book: SimPortfolioBroker over the 10 ETFs, allow_short=True,
max_gross=3.1 -- the cap the spec asks for. It sits above the observed maximum, so it is a
backstop, never a rule the research did not test. Fills are at the yfinance daily close
out of the shared `data/` cache, the same close the research charged turnover at. There is
no order book, no rejection, no partial fill and no margin interest behind this track; it
is weaker evidence than a venue fill and must be read as such.

History. Every input is a trailing window (252d beta, 504d trend, 126d vol/cov), so the
weights do not depend on where the panel starts. The runner still reads it exactly as
`02_evaluate.py` does -- the research loader `code/global-equity-etf/shared/data.load_panel`
from 1998-12-01, which splices `_d_pre2010.parquet` onto the live-refreshed cache.

Timing. target_weights(close) row t is the weight held from close_t to close_{t+1}, from
data up to and including close_t. The month-end test and the FOMC window both look one or
two NYSE sessions ahead through `shared/trading_calendar.py`, so the last bar must be a
finished close: the daemon wakes at 00:00 UTC (after the NYSE close in EDT and EST, before
the next open) and PortfolioRunner acts only when the bar all 10 legs agree on changes. A
re-check during US hours that pulls yfinance's forming bar raises instead of trading it.

Cost. The research charges 5 bp per side on the country ETFs and 1 bp on SPY. The broker
takes one rate for every leg, so it is built as 1 bp slippage + 4 bp fee = 5 bp on all ten
-- conservative on the SPY hedge leg by 4 bp. Report ladder: 2 bp -> 0.87, 5 bp -> 0.81,
10 bp -> 0.72 full-sample.
"""
import logging
import os
import sys
from zoneinfo import ZoneInfo

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
CODE = os.path.join(REPO, "code", "global-equity-etf")
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(CODE, "shared"))
sys.path.insert(0, os.path.join(CODE, "global-etf-sleeve-blend"))

import data as gedata  # noqa: E402  (code/global-equity-etf/shared/data.py)
from live_lib import MarketData, YahooQuotes  # noqa: E402
from portfolio import PortfolioRunner, SimPortfolioBroker  # noqa: E402
from strategy import COLUMNS, target_weights  # noqa: E402
from trading_calendar import NYSE_HOLIDAYS  # noqa: E402

log = logging.getLogger(__name__)

NAME = "global-equity-etf/global-etf-sleeve-blend"
SCHEDULE = "1d"
OFFSET_S = 20.0                    # 00:00:20 UTC -- after the NYSE close in EDT and EST
# This strategy's own book (sim, uncapped). See live_lib.allocate().
CAPITAL_USDT = 2_500.0
# Research cost: 5 bp/side on country ETFs, 1 bp on SPY (02_evaluate.py). One rate per
# broker, so 5 bp on every leg.
SLIPPAGE_BPS = 1.0
FEE_BPS = 4.0
MAX_GROSS = 3.1                    # spec: "Cap gross at 3.1x" (max observed 3.00)
TRADED = list(COLUMNS)             # 9 country ETFs + SPY
START = "1998-12-01"               # as 02_evaluate.py
# 504d trend + 252d beta + 126d vol need ~900 sessions before the first valid weight.
MIN_BARS = 1500
NY = ZoneInfo("America/New_York")
FOMC_CSV = os.path.join(CODE, "fomc-global-beta", "fomc_snapshot.csv")

md = MarketData(source="public")   # used only for its shared daily cache


def _refresh_cache():
    """Bring the post-2010 `data/<T>_d.parquet` files up to date; `load_panel` reads them."""
    for ticker in TRADED:
        try:
            md.daily(ticker, cache_hours=0.5)
        except Exception as e:  # noqa: BLE001 - a stale leg is caught below, by date
            log.warning("daily(%s) refresh failed: %s", ticker, e)


def _calendar_warnings(now_ny):
    horizon = now_ny.tz_localize(None) + pd.Timedelta(days=90)
    fomc_end = pd.to_datetime(pd.read_csv(FOMC_CSV)["date"]).max()
    if fomc_end < horizon:
        log.warning("fomc_snapshot.csv ends %s -- append next year's Fed calendar or the "
                    "FOMC sleeve goes dark", fomc_end.date())
    if NYSE_HOLIDAYS.max() < horizon:
        log.warning("trading_calendar.NYSE_HOLIDAYS ends %s -- extend it or month-ends and "
                    "FOMC windows next to holidays are mis-timed", NYSE_HOLIDAYS.max().date())


def compute_weights(now):
    """Target weights to hold from the last NYSE close to the next, per alpha.md."""
    _refresh_cache()
    close = gedata.load_panel(TRADED, field="Close", start=START)
    if len(close) < MIN_BARS:
        raise RuntimeError(f"only {len(close)} daily bars; need >= {MIN_BARS}")

    last = close.index[-1]
    now_ny = pd.Timestamp(now).tz_convert(NY)
    if last.date() == now_ny.date() and (now_ny.hour, now_ny.minute) < (16, 30):
        raise RuntimeError(f"bar {last.date()} is still forming ({now_ny:%H:%M} New York); "
                           f"waiting for the close")
    if (now_ny.tz_localize(None).normalize() - last).days > 6:
        raise RuntimeError(f"last bar {last.date()} is stale -- data feed down?")
    # load_panel forward-fills up to 3 days onto the SPY calendar, which would quietly
    # trade a leg on yesterday's price. Every leg must have printed the book's bar.
    for t in TRADED:
        lv = gedata.load_ohlcv(t, include_pre2010=False).index[-1]
        if lv != last:
            raise RuntimeError(f"{t} last bar {lv.date()} != SPY {last.date()}; waiting")
    _calendar_warnings(now_ny)

    W = target_weights(close)                          # spec defaults: 0.67 / 0.87
    row = W.loc[last]
    if row.isna().any():
        raise RuntimeError(f"NaN weights on {last.date()}: {row[row.isna()].index.tolist()}")
    return {s: float(row.get(s, 0.0)) for s in TRADED}


if __name__ == "__main__":
    PortfolioRunner(
        name=NAME,
        symbols=TRADED,
        schedule=SCHEDULE,
        compute_weights=compute_weights,
        broker=SimPortfolioBroker(
            TRADED, capital_usdt=CAPITAL_USDT, max_gross=MAX_GROSS, allow_short=True,
            fee_bps=FEE_BPS, slippage_bps=SLIPPAGE_BPS,
            quotes=YahooQuotes(cache_hours=0.5),
        ),
        offset_s=OFFSET_S,
    ).cli()
