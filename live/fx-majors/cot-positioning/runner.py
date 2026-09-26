"""
Live (paper) runner for `fx-majors/cot-positioning` -- fade CFTC positioning in the CME
currency futures across the seven G10 majors vs USD: the mean of -z(net share of OI) and
-z(4-report change) for legacy non-commercials, TFF leveraged funds and TFF asset managers,
demeaned across currencies (exactly USD-neutral), sum|w| = 1, scaled to 5 % vol, rebalanced
on the first `=X` row of each ISO week.

Spec:   alphas/fx-majors/cot-positioning/spec.md
Signal: code/fx-majors/cot-positioning/strategy.py :: target_weights(px, cot_legacy, cot_tff)
        (imported with its spec defaults, not restated)

Book. A long/SHORT basket with gross averaging 1.49x and reaching 2.42x in 2010-26, so it
trades in the SIM book: SimPortfolioBroker over the seven `=X` pairs, allow_short=True,
max_gross=3.0 -- the cap the spec asks for (the strategy's own k cap). Weights are in TICKER
space: USDJPY/USDCAD/USDCHF carry minus the currency weight, which the function applies.
Fills are at the last yfinance daily close in the shared `data/` cache. There is no order
book, no rejection, no partial fill, and no carry/swap accrual behind this track (the report
puts the book's carry at +3 bp/yr, so the omission is immaterial); it is weaker evidence
than a venue fill and must be read as such.

Bars. Yahoo stamps `=X` row D at the start of day D: once settled, its close is the 00:00 UTC
(London-midnight) quote on D, which is the price the research fills at. The row is created
at day start and carries the live price until it settles, so acting right after 00:00 UTC
on D fills at ~that print. Two live artefacts the research history does not contain are
removed before anything sees them:
  * a transient Saturday row (Friday's 21:00 UTC close) that Yahoo shows over the weekend
    and later drops -- stripped from the frame AND from the shared cache, where
    `MarketData.daily`'s merge would otherwise keep it forever;
  * a row dated after today's UTC date (in BST, day D's row appears at 23:00 UTC on D-1) --
    hidden until 00:00 UTC D, so the Monday rebalance cannot fire an hour early.

COT. The Monday row uses the report released the previous Friday (usable after Saturday
21:00 UTC; holiday weeks and shutdown backlogs per `fetch_cot_fx._avail`). The runner
refreshes this year's CFTC files whenever the report the current row is entitled to is not
cached yet, and refuses to trade without it rather than trade a week-stale signal (the
report puts one-week-late at 0.40 vs 0.80).

Cost. Research charges each pair's measured 00:00 UTC half-spread (2020-26: EUR 0.17 ...
NZD 0.94 bp/side); the spec suggests slippage 1 bp, fee 0 as the conservative single rate
for the broker (flat 1 bp: 0.77 / 0.60 vs 0.80 / 0.64 at measured cost).
"""
import logging
import os
import sys

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
CODE = os.path.join(REPO, "code", "fx-majors")
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(REPO, "code", "shared"))
sys.path.insert(0, os.path.join(CODE, "shared"))
sys.path.insert(0, os.path.join(CODE, "cot-positioning"))

import fetch_cot_fx  # noqa: E402  (code/fx-majors/shared/fetch_cot_fx.py)
from live_lib import MarketData, YahooQuotes, _atomic_parquet, daily_cache_path  # noqa: E402
from portfolio import PortfolioRunner, SimPortfolioBroker  # noqa: E402
from research_lib import load_series  # noqa: E402
from strategy import TICKERS, target_weights  # noqa: E402

log = logging.getLogger(__name__)

NAME = "fx-majors/cot-positioning"
SCHEDULE = "1d"
OFFSET_S = 120.0                   # 00:02 UTC -- just after the 00:00 UTC print the research fills at
# This strategy's own book (sim, uncapped). See live_lib.allocate().
CAPITAL_USDT = 2_500.0
# Spec: "slippage 1 bp, fee 0" -- conservative against the measured 0.17-0.94 bp half-spreads.
SLIPPAGE_BPS = 1.0
FEE_BPS = 0.0
MAX_GROSS = 3.0                    # spec: "cap 3.0 -- set max_gross = 3.0" (max observed 2.42)
TRADED = list(TICKERS)             # EURUSD GBPUSD USDJPY AUDUSD USDCAD USDCHF NZDUSD =X
# 126d-halflife vol estimate and a 156-report z window: the research reads =X from 2010,
# the cache start; ask for at least 4 years of daily rows before trusting a weight.
MIN_BARS = 1000
MAX_STALE_DAYS = 5


class WeekdayDaily(MarketData):
    """`MarketData.daily` restricted to the rows the research panel is made of."""

    def daily(self, ticker, lookback_days=None, cache_hours=6.0):
        df = super().daily(ticker, lookback_days=lookback_days, cache_hours=cache_hours)
        wkend = df.index.dayofweek >= 5
        if wkend.any():
            log.info("%s: dropping %d weekend row(s) %s from the shared cache", ticker,
                     int(wkend.sum()), [d.date().isoformat() for d in df.index[wkend]])
            df = df[~wkend]
            _atomic_parquet(df, daily_cache_path(ticker))
        today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
        return df[df.index <= today]


md = WeekdayDaily(source="public")      # used only for its daily cache


def _load_px():
    for t in TRADED:
        try:
            md.daily(t, cache_hours=0.5)
        except Exception as e:  # noqa: BLE001 - a stale leg is caught below, by date
            log.warning("daily(%s) refresh failed: %s", t, e)
    # Same reader as strategy.load_inputs(refresh=False), i.e. the research panel.
    px = pd.DataFrame({t: load_series(t)["Close"] for t in TRADED})
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    return px[(px.index.dayofweek < 5) & (px.index <= today)]


def _required_report(row):
    """As-of date of the latest COT report released strictly before row's 00:00 UTC stamp."""
    tue = pd.Series(pd.date_range(row - pd.Timedelta(days=42), row, freq="W-TUE"))
    avail = fetch_cot_fx._avail(tue)
    return tue[(avail < row).values].max()


def _load_cot(row):
    need = _required_report(row)
    lg, tf = fetch_cot_fx.fetch_legacy(), fetch_cot_fx.fetch_tff()
    # A Tuesday-holiday week can stamp the report Monday: allow one day.
    have = lambda: min(lg["date"].max(), tf["date"].max()) >= need - pd.Timedelta(days=1)
    if not have():
        log.info("COT report as of %s not cached (have %s); refreshing CFTC %d files",
                 need.date(), min(lg["date"].max(), tf["date"].max()).date(), row.year)
        fetch_cot_fx.refresh_current_year()
        lg, tf = fetch_cot_fx.fetch_legacy(), fetch_cot_fx.fetch_tff()
    if not have():
        raise RuntimeError(f"COT report as of {need.date()} is due for row {row.date()} but "
                           f"CFTC has not published it (latest {lg['date'].max().date()}); "
                           f"not trading a stale signal")
    return lg, tf


def compute_weights(now):
    """Ticker-space weights to hold from the last =X row to the next, per spec.md."""
    px = _load_px()
    if len(px) < MIN_BARS:
        raise RuntimeError(f"only {len(px)} daily rows; need >= {MIN_BARS}")
    last = px.index[-1]
    today = pd.Timestamp(now).tz_convert("UTC").tz_localize(None).normalize()
    if (today - last).days > MAX_STALE_DAYS:
        raise RuntimeError(f"last =X row {last.date()} is stale -- data feed down?")
    # target_weights forward-fills, which would quietly trade a lagging leg on an old price.
    lagging = {t: px[t].last_valid_index().date() for t in TRADED
               if px[t].last_valid_index() != last}
    if lagging:
        raise RuntimeError(f"legs lag the {last.date()} row: {lagging}; waiting")

    lg, tf = _load_cot(last)
    W = target_weights(px, lg, tf)
    row = W.loc[last]
    if row.isna().any():
        raise RuntimeError(f"NaN weights on {last.date()}: {row[row.isna()].index.tolist()}")
    if row.abs().sum() == 0:
        raise RuntimeError(f"all-zero weights on {last.date()} -- signal inputs empty?")
    return {s: float(row[s]) for s in TRADED}


if __name__ == "__main__":
    PortfolioRunner(
        name=NAME,
        symbols=TRADED,
        schedule=SCHEDULE,
        compute_weights=compute_weights,
        broker=SimPortfolioBroker(
            TRADED, capital_usdt=CAPITAL_USDT, max_gross=MAX_GROSS, allow_short=True,
            fee_bps=FEE_BPS, slippage_bps=SLIPPAGE_BPS,
            quotes=YahooQuotes(market_data=md, cache_hours=0.5),
        ),
        offset_s=OFFSET_S,
    ).cli()
