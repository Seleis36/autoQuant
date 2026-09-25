"""
Live (paper) runner for `sector-etf/sector-sleeve-blend` -- four weak, uncorrelated
sector-ETF sleeves (overnight-sentiment reversal, flow calendar, RSI(2) dips, rate
rotation) risk-weighted once a year, on the 11 SPDR sector ETFs + SPY.

Spec:   alphas/sector-etf/sector-sleeve-blend/spec.md
Signal: code/sector-etf/sector-sleeve-blend/strategy.py :: target_weights()
        (imported with its spec defaults, not restated)

Book. A long/SHORT cross-sectional basket of US ETFs with gross up to 2.0, so it trades
in the SIM book: SimPortfolioBroker over the 11 sectors + SPY, allow_short=True,
max_gross=2.0 -- the `gross_cap` the spec was tested at (binds on ~1 % of days; the
function already applies it, so the broker cap is a backstop, not a second rule). Fills
are at the yfinance daily close out of the shared `data/` cache, the same close the
research charged turnover at. There is no order book, no rejection, no partial fill,
and no margin interest on the levered days behind this track; it is weaker evidence
than a venue fill and must be read as such.

History. The yearly sleeve risk weights use each sleeve's EXPANDING net-return vol from
its first trade (1999-2002) to the prior 31 Dec, so a truncated history would give
different weights from the research. The runner therefore reads the full 1998+ panel
through the research's own loader (`code/sector-etf/shared/data.load_panel`), which
splices the `_d_pre2010.parquet` files onto the live-refreshed post-2010 cache. The
10-year yield is yfinance ^TNX spliced the same way, as the spec asks (FRED DGS10,
the research default, is refreshed by nothing live; ^TNX was tested at 0.89 / 0.84 OOS).

Timing. target_weights(...) row t is the weight held from close_t to close_{t+1}; its
inputs (close_t, open_t, ^TNX_t) are all known at that close, and the calendar sleeve
looks ahead only to day t+1's calendar position. The runner wakes at 00:00 UTC --
always after the NYSE close and before the next open -- and PortfolioRunner acts only
when the bar all 12 legs agree on changes, so weekends and holidays are no-ops. A
re-check during US hours can pull yfinance's still-forming bar for today;
compute_weights refuses it rather than trade a mid-session price as a close.

Cost. The research charges 2 bp per side on sum|dw|, all-in (spec: "2 bp per side on
all traded notional"). The broker is built as 1 bp slippage + 1 bp fee -- NOT the
10 bp default. Report ladder: 0 bp -> 0.98, 2 bp -> 0.88, 5 bp -> 0.73 full-sample.
"""
import logging
import os
import sys
from zoneinfo import ZoneInfo

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(REPO, "code", "sector-etf", "shared"))
sys.path.insert(0, os.path.join(REPO, "code", "sector-etf", "sector-sleeve-blend"))

import data as sxdata  # noqa: E402  (code/sector-etf/shared/data.py)
from live_lib import MarketData, YahooQuotes  # noqa: E402
from portfolio import PortfolioRunner, SimPortfolioBroker  # noqa: E402
from strategy import SECTORS, target_weights  # noqa: E402

log = logging.getLogger(__name__)

NAME = "sector-etf/sector-sleeve-blend"
SCHEDULE = "1d"
OFFSET_S = 20.0                    # 00:00:20 UTC -- after the NYSE close in EDT and EST
# This strategy's own book (sim, uncapped). See live_lib.allocate().
CAPITAL_USDT = 2_500.0
# Research cost: 2 bp per side all-in on traded notional (spec, final_eval.py).
SLIPPAGE_BPS = 1.0
FEE_BPS = 1.0
MAX_GROSS = 2.0                    # spec gross_cap
TRADED = SECTORS + ["SPY"]
Y10 = "^TNX"                       # signal input only; never traded
# The yearly risk weights need 3 years of sleeve returns after a 252-day warm-up; the
# research panel starts 1998-12. Anything much shorter than the full splice means the
# pre-2010 files are missing and the weights would silently differ from the research.
MIN_BARS = 6500
NY = ZoneInfo("America/New_York")
FOMC_CSV = os.path.join(REPO, "code", "sector-etf", "sector-sleeve-blend", "fomc_dates.csv")

md = MarketData(source="public")   # used only for its shared daily cache


def _refresh_cache():
    """Bring the post-2010 `data/<T>_d.parquet` files up to date; `load_panel` reads them."""
    for ticker in TRADED + [Y10]:
        try:
            md.daily(ticker, cache_hours=0.5)
        except Exception as e:  # noqa: BLE001 - a stale leg is caught below, by date
            log.warning("daily(%s) refresh failed: %s", ticker, e)


def compute_weights(now):
    """Target weights to hold from the last NYSE close to the next, per spec.md."""
    _refresh_cache()
    close = sxdata.load_panel(TRADED, field="Close")
    open_ = sxdata.load_panel(TRADED, field="Open")
    y10 = sxdata.load_ohlcv(Y10)["Close"].dropna()
    if len(close) < MIN_BARS:
        raise RuntimeError(f"only {len(close)} daily bars; need >= {MIN_BARS} -- are the "
                           f"data/*_d_pre2010.parquet files missing?")

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
        lv = sxdata.load_ohlcv(t, include_pre2010=False).index[-1]
        if lv != last:
            raise RuntimeError(f"{t} last bar {lv.date()} != SPY {last.date()}; waiting")
    if y10.index[-1] < last:
        log.warning("^TNX last bar %s behind %s -- RATE uses a forward-filled yield today",
                    y10.index[-1].date(), last.date())
    fomc_end = pd.to_datetime(pd.read_csv(FOMC_CSV)["date"]).max()
    if fomc_end < now_ny.tz_localize(None) + pd.Timedelta(days=90):
        log.warning("fomc_dates.csv ends %s -- append next year's Fed calendar or the "
                    "pre-FOMC CAL window goes dark", fomc_end.date())

    W = target_weights(close, open_, y10=y10)          # spec defaults, gross_cap=2.0
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
