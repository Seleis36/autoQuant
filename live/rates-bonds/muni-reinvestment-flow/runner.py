"""
Live (paper) runner for rates-bonds/muni-reinvestment-flow -- long MUB/TFI/ITM/SHM, short
beta x IEF/SHY over the first five NYSE sessions of every month (muni coupon/redemption
reinvestment flow).

Spec:   alphas/rates-bonds/muni-reinvestment-flow/spec.md
Signal: code/rates-bonds/muni-reinvestment-flow/strategy.py :: target_weights()
        (imported with its spec defaults, not restated)

Book. A long/SHORT six-ETF basket with gross 1.37 on held days (max 1.74 in the backtest),
so it trades in the SIM book: SimPortfolioBroker, allow_short=True, max_gross=1.8 -- a
backstop just above the observed maximum at the validated scale = 1, never a rule the
research did not test. Fills are at the yfinance daily close out of the shared data/ cache,
the same close the research charged turnover at. No order book, rejection, partial fill,
borrow cost or margin interest sits behind this track; it is weaker evidence than a venue
fill and must be read as such.

History. The only lookback is the 252-session (min 126) OLS beta, so ~600 bars are plenty.
The runner reads prices with the research loader `rb_data.etf_close`, the same function
07_final.py backtested on, after refreshing the per-ticker caches it reads.

Timing. target_weights(close) row t is the weight held from close_t to close_{t+1}, from
data up to and including close_t. The month-start test looks one NYSE session ahead via
strategy.hold_flags, so the last bar must be a finished close: the daemon wakes at 00:00 UTC
(after the NYSE close in EDT and EST, before the next open) and PortfolioRunner acts only
when the bar all six legs agree on changes. A re-check during US hours that pulls yfinance's
forming bar raises instead of trading it.

Cost. The research charges 2 bp per side on every leg (07_final.py, bt(w, px, 2.0)), so the
broker is built as 1 bp slippage + 1 bp fee -- NOT the 10 bp crypto default, at which this
book is dead (report ladder: 3 bp -> 0.29, 5 bp -> -0.17 full-sample).
"""
import logging
import os
import sys
from zoneinfo import ZoneInfo

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
CODE = os.path.join(REPO, "code", "rates-bonds")
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(CODE, "shared"))
sys.path.insert(0, os.path.join(CODE, "muni-reinvestment-flow"))

from live_lib import MarketData, YahooQuotes  # noqa: E402
from portfolio import PortfolioRunner, SimPortfolioBroker  # noqa: E402
from rb_data import etf_close  # noqa: E402
from strategy import TICKERS, target_weights  # noqa: E402

log = logging.getLogger(__name__)

NAME = "rates-bonds/muni-reinvestment-flow"
SCHEDULE = "1d"
OFFSET_S = 20.0                    # 00:00:20 UTC -- after the NYSE close in EDT and EST
# This strategy's own book (sim, uncapped). See live_lib.allocate().
CAPITAL_USDT = 2_500.0
# Research cost: 2 bp/side all-in on every leg.
SLIPPAGE_BPS = 1.0
FEE_BPS = 1.0
MAX_GROSS = 1.8                    # scale = 1: gross 1.37 avg, 1.74 max observed 2008-26
TRADED = list(TICKERS)             # MUB TFI ITM SHM IEF SHY
MIN_BARS = 600                     # 252d beta (min 126) + margin
NY = ZoneInfo("America/New_York")

md = MarketData(source="public")   # used only for its shared daily cache


def _refresh_cache():
    """Bring data/<T>_d.parquet up to date; etf_close reads those files."""
    for ticker in TRADED:
        try:
            md.daily(ticker, cache_hours=0.5)
        except Exception as e:  # noqa: BLE001 - a stale leg is caught below, by date
            log.warning("daily(%s) refresh failed: %s", ticker, e)


def compute_weights(now):
    """Target weights to hold from the last NYSE close to the next, per spec.md."""
    _refresh_cache()
    close = etf_close(TRADED, include_pre2010=False)
    close = close.loc["2018-01-01":]
    if len(close) < MIN_BARS:
        raise RuntimeError(f"only {len(close)} daily bars; need >= {MIN_BARS}")

    last = close.index[-1]
    now_ny = pd.Timestamp(now).tz_convert(NY)
    if last.date() == now_ny.date() and (now_ny.hour, now_ny.minute) < (16, 30):
        raise RuntimeError(f"bar {last.date()} is still forming ({now_ny:%H:%M} New York); "
                           f"waiting for the close")
    if (now_ny.tz_localize(None).normalize() - last).days > 6:
        raise RuntimeError(f"last bar {last.date()} is stale -- data feed down?")
    # Every leg must have printed the book's bar, or a leg's beta/position would be
    # computed on a missing price.
    missing = close.columns[close.loc[last].isna()].tolist()
    if missing:
        raise RuntimeError(f"{missing} have no bar for {last.date()}; waiting")

    W = target_weights(close[TRADED])                  # spec defaults: n_days=5, 252d beta, scale 1
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
