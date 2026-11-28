"""
Live (paper) runner for `global-equity-etf/trend-flow-blend` -- four country-ETF sleeves at
IS-fixed equal risk:

    0.490 x intl-relative-trend      (slow US-vs-ex-US trend, market-neutral, month-end)
  + 0.605 x fomc-global-beta         (long EW country basket over FOMC day -1/0)
  + 0.861 x global-rebalance-pressure (-clip(Z)/2 on 0.6 SPY + 0.4 EFA, last 4 sessions)
  + 0.672 x intl-rebalance-flow      (EFA - beta*SPY on the last session of the month)
  then, per session, scale the row to gross 4.0 if sum|w| > 4.0.

Spec:   alphas/global-equity-etf/trend-flow-blend/alpha.md
Signal: code/global-equity-etf/trend-flow-blend/strategy.py :: target_weights()
        (imported with its spec defaults, not restated)

Book. Long/SHORT basket over 9 country ETFs + SPY + EFA, gross averaging 1.11x and reaching
3.97x in the backtest, so it trades in the SIM book: SimPortfolioBroker, allow_short=True,
max_gross=4.0 -- the strategy's own per-session cap (strategy.GROSS_CAP), which never bound in
2003-26. IEF is a signal-only input (stock/bond drift of the rebalance sleeve); it is read
from the cache but never reaches the broker. Fills are at the yfinance daily close from the
shared `data/` cache -- the same close the signal is computed on, which is what the research
charged. No order book, rejection, partial fill or margin interest behind this track.

History. Every input is a trailing window (504d trend, 252d beta/vol), so the weights do not
depend on the panel start. The runner still reads it exactly as `02_evaluate.py` does:
`shared/data.load_panel(COLUMNS + ["IEF"], "Close", start="1998-12-01")`.

Timing. target_weights row t is the weight held close_t -> close_{t+1}, using data up to
close_t. The month-end windows and the FOMC window look ahead through the NYSE calendar in
`shared/trading_calendar.py` (next_session_days_left / month_end_sessions), so the last bar
must be a finished close. The daemon wakes at 00:00:20 UTC (after the NYSE close in EDT and
EST) and PortfolioRunner acts only when the bar changes. A +1 session lag drops the blend
from 1.25 to 0.52 -- the daemon must trade the bar the signal is computed on, never later.

Cost. Research: 5 bp/side on the country ETFs, 2 bp on EFA, 1 bp on SPY. The broker takes
one rate for every leg. Over 2003-26 the backtest's turnover is 37.5 % SPY, 33.3 % EFA and
29 % countries, so its turnover-weighted rate is 2.50 bp/side: built as 1.0 bp slippage +
1.5 bp fee. Aggregate cost matches the research; per leg it under-charges the countries by
2.5 bp and over-charges SPY/EFA. Report: costs x2 -> 1.13 full / 0.99 OOS.
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
sys.path.insert(0, os.path.join(CODE, "trend-flow-blend"))

import data as gedata  # noqa: E402  (code/global-equity-etf/shared/data.py)
from live_lib import MarketData, YahooQuotes  # noqa: E402
from portfolio import PortfolioRunner, SimPortfolioBroker  # noqa: E402
from strategy import COLUMNS, GROSS_CAP, SIGNAL_ONLY, target_weights  # noqa: E402
from trading_calendar import NYSE_HOLIDAYS  # noqa: E402

log = logging.getLogger(__name__)

NAME = "global-equity-etf/trend-flow-blend"
SCHEDULE = "1d"
OFFSET_S = 20.0                    # 00:00:20 UTC -- after the NYSE close in EDT and EST
# This strategy's own book (sim, uncapped). See live_lib.allocate().
CAPITAL_USDT = 2_500.0
# Research cost 5/2/1 bp (countries/EFA/SPY); turnover-weighted 2.50 bp/side (see docstring).
SLIPPAGE_BPS = 1.0
FEE_BPS = 1.5
MAX_GROSS = float(GROSS_CAP)       # 4.0 -- spec's per-session cap (max observed 3.97)
TRADED = list(COLUMNS)             # 9 country ETFs + SPY + EFA
INPUTS = TRADED + list(SIGNAL_ONLY)  # + IEF (signal only)
START = "1998-12-01"               # as 02_evaluate.py
MIN_BARS = 1500                    # 504d trend + 252d beta/vol need ~900 sessions
NY = ZoneInfo("America/New_York")
FOMC_CSV = os.path.join(CODE, "fomc-global-beta", "fomc_snapshot.csv")

md = MarketData(source="public")   # used only for its shared daily cache


def _refresh_cache():
    """Bring the post-2010 `data/<T>_d.parquet` files up to date; `load_panel` reads them."""
    for ticker in INPUTS:
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
        log.warning("trading_calendar.NYSE_HOLIDAYS ends %s -- extend it or month-end and "
                    "FOMC windows next to holidays are mis-timed", NYSE_HOLIDAYS.max().date())


def compute_weights(now):
    """Target weights to hold from the last NYSE close to the next, per alpha.md."""
    _refresh_cache()
    close = gedata.load_panel(INPUTS, field="Close", start=START)
    if len(close) < MIN_BARS:
        raise RuntimeError(f"only {len(close)} daily bars; need >= {MIN_BARS}")

    last = close.index[-1]
    now_ny = pd.Timestamp(now).tz_convert(NY)
    if last.date() == now_ny.date() and (now_ny.hour, now_ny.minute) < (16, 30):
        raise RuntimeError(f"bar {last.date()} is still forming ({now_ny:%H:%M} New York); "
                           f"waiting for the close")
    if (now_ny.tz_localize(None).normalize() - last).days > 6:
        raise RuntimeError(f"last bar {last.date()} is stale -- data feed down?")
    # load_panel forward-fills onto the SPY calendar, which would quietly trade on a stale
    # price. Every input (IEF included) must have printed the book's bar.
    for t in INPUTS:
        lv = gedata.load_ohlcv(t, include_pre2010=False).index[-1]
        if lv != last:
            raise RuntimeError(f"{t} last bar {lv.date()} != SPY {last.date()}; waiting")
    _calendar_warnings(now_ny)

    W = target_weights(close)                          # spec defaults
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
