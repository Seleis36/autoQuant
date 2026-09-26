"""
Live (paper) runner for `vol-complex/vix-cot-positioning` -- short VIXY in contango only when
the CFTC asset-manager net share of VIX-futures open interest (the vol-ETP crowd) is high
against its own history: weight = -mean of 25 votes 1[VIX3M/VIX(t-1) > 1 AND score_t > theta]
over 5 positioning z-scores x 5 thresholds, so the book is short VIXY 0..100 % or flat.

Spec:   alphas/vol-complex/vix-cot-positioning/spec.md
Signal: code/vol-complex/vix-cot-positioning/strategy.py :: target_weight(vixy, vix, vix3m, tff)
        (imported with its spec defaults -- size=1.0, slope_lag=1 -- not restated)

Book. VIXY is an ETF and the strategy is short-only, so it trades in the SIM book:
SimBroker("VIXY", allow_short=True, max_weight=1.0) -- the spec's validated maximum gross,
reached on 9 % of backtest days. Marked and filled at the yfinance daily close from the shared
data/ cache, which is the close research_lib.backtest charged turnover at. There is no order
book, no rejection, no partial fill, and NO short-borrow fee behind this track (the report
puts VIXY borrow at ~-0.04 Sharpe); it is weaker evidence than a venue fill.

Timing. target_weight(...)[t] is the weight held from close_t to close_{t+1}. The runner wakes
at 00:00 UTC, after the NYSE close, and acts only when VIXY prints a new bar
(YahooQuotes.bar_key), so weekends and holidays are no-ops. The VIX-family slope is lagged one
session inside target_weight (the index closes 16:15 ET, after the 16:00 ETP fill), so the
runner insists ^VIX and ^VIX3M hold the PREVIOUS VIXY session -- a lagging index feed would
otherwise be forward-filled into a stale slope without a trace.

COT. Bar D uses the latest report with avail_utc < D 00:00 UTC (Monday's close for a normal
Friday release; fetch_cot_fx._avail for holiday / shutdown weeks). When the report the bar is
entitled to is not cached the runner calls fetch_cot_vix.refresh_current_year(). If CFTC still
has not published it, it trades on the last report for up to MAX_COT_EXTRA_LAG_DAYS -- the
report's lag placebo puts 1-2 extra weeks at 1.02 / 0.98 vs 1.00 -- and refuses beyond that.

Cost. Research charges 5 bp per side on traded notional (vc_data.bt, cost_bps=5). SimBroker
charges slippage + fee on each fill, so the book is built with 2.5 bp + 2.5 bp -- NOT the 10 bp
default (the report's cost ladder: 10 bp -> 0.99).
"""
import logging
import os
import sys
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
CODE = os.path.join(REPO, "code", "vol-complex")
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(CODE, "shared"))
sys.path.insert(0, os.path.join(CODE, "vix-cot-positioning"))

import fetch_cot_vix  # noqa: E402  (code/vol-complex/shared/fetch_cot_vix.py)
from live_lib import MarketData, SimBroker, StrategyRunner  # noqa: E402
from strategy import scores_on_sessions, target_weight  # noqa: E402

log = logging.getLogger(__name__)

NAME = "vol-complex/vix-cot-positioning"
SYMBOL = "VIXY"
SCHEDULE = "1d"
# This strategy's own book (sim, uncapped). See live_lib.allocate().
CAPITAL_USDT = 2_500.0
# Research cost: 5 bp/side on traded notional (final.py: vc.bt(w, VIXY, 5)).
SLIPPAGE_BPS = 2.5
FEE_BPS = 2.5
MAX_WEIGHT = 1.0                  # spec: max gross 1.0 (short 100 % of capital)
# The z-scores run on the weekly COT grid (up to 156 reports, read from the CFTC cache), not
# on the price series; prices only need the index and a one-session-lagged slope. 250 bars
# is a sanity floor.
MIN_BARS = 250
MAX_STALE_DAYS = 6
MAX_COT_EXTRA_LAG_DAYS = 14       # report: +1 / +2 weeks of COT lag -> Sharpe 1.02 / 0.98
NY = ZoneInfo("America/New_York")

md = MarketData(source="public")      # used only for its daily cache


def _close(ticker):
    df = md.daily(ticker, cache_hours=1.0)
    s = df["Close"].dropna()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s[~s.index.duplicated(keep="last")].sort_index()


def _required_report(row):
    """As-of date of the latest COT report released strictly before row's 00:00 UTC."""
    tue = pd.Series(pd.date_range(row - pd.Timedelta(days=42), row, freq="W-TUE"))
    avail = fetch_cot_vix.fx._avail(tue)
    return tue[(avail < row).values].max()


def _load_tff(row):
    need = _required_report(row)
    tff = fetch_cot_vix.fetch_tff()
    # A Tuesday-holiday week can stamp the report Monday: allow one day.
    if tff["date"].max() < need - pd.Timedelta(days=1):
        log.info("COT report as of %s not cached (have %s); refreshing CFTC %d files",
                 need.date(), tff["date"].max().date(), pd.Timestamp.today().year)
        try:
            fetch_cot_vix.refresh_current_year()
        except Exception as e:  # noqa: BLE001 - judged by the staleness test below
            log.warning("CFTC refresh failed: %s", e)
        tff = fetch_cot_vix.fetch_tff()
    have = tff["date"].max()
    if have < need - pd.Timedelta(days=MAX_COT_EXTRA_LAG_DAYS + 1):
        raise RuntimeError(f"COT report as of {need.date()} is due for row {row.date()}; latest "
                           f"cached is {have.date()} (> {MAX_COT_EXTRA_LAG_DAYS} d late); "
                           f"not trading a stale signal")
    if have < need - pd.Timedelta(days=1):
        log.warning("COT report as of %s not yet published; using %s (within the %d-day "
                    "extra-lag tolerance)", need.date(), have.date(), MAX_COT_EXTRA_LAG_DAYS)
    return tff


def compute_weight(now):
    """Target VIXY weight (<= 0) to hold from the last close to the next, per spec.md."""
    vixy = _close(SYMBOL)
    vix, vix3m = _close("^VIX"), _close("^VIX3M")
    if len(vixy) < MIN_BARS:
        raise RuntimeError(f"only {len(vixy)} daily {SYMBOL} bars; need >= {MIN_BARS}")

    last, prev = vixy.index[-1], vixy.index[-2]
    now_ny = pd.Timestamp(now).tz_convert(NY)
    if last.date() == now_ny.date() and (now_ny.hour, now_ny.minute) < (16, 30):
        raise RuntimeError(f"{SYMBOL} bar {last.date()} is still forming "
                           f"({now_ny:%H:%M} New York); waiting for the close")
    if (now_ny.tz_localize(None).normalize() - last).days > MAX_STALE_DAYS:
        raise RuntimeError(f"{SYMBOL} last bar {last.date()} is stale -- data feed down?")
    # target_weight forward-fills the indices onto VIXY's sessions and lags the slope one
    # session, so the slope used for `last` is the one at `prev`; it must be a real print.
    for nm, s in (("^VIX", vix), ("^VIX3M", vix3m)):
        if prev not in s.index:
            raise RuntimeError(f"{nm} has no close for {prev.date()} (latest "
                               f"{s.index[-1].date()}); the lagged slope would be stale")

    tff = _load_tff(last)
    w = target_weight(vixy, vix, vix3m, tff)

    slope = float(vix3m.loc[prev] / vix.loc[prev])
    S = scores_on_sessions(tff, pd.DatetimeIndex([last])).iloc[-1]
    if not np.isfinite(slope) or S.isna().any():
        raise RuntimeError(f"NaN signal input on {last.date()}: slope {slope}, "
                           f"scores {S.to_dict()}")
    log.info("row %s: VIX3M/VIX(%s) = %.3f, scores %s -> weight %.2f", last.date(),
             prev.date(), slope, {k: round(float(v), 2) for k, v in S.items()},
             float(w.iloc[-1]))
    return float(w.iloc[-1])


if __name__ == "__main__":
    StrategyRunner(
        name=NAME,
        symbol=SYMBOL,
        schedule=SCHEDULE,
        compute_weight=compute_weight,
        broker=SimBroker(SYMBOL, capital_usdt=CAPITAL_USDT, max_weight=MAX_WEIGHT,
                         allow_short=True, slippage_bps=SLIPPAGE_BPS, fee_bps=FEE_BPS),
        offset_s=20.0,
    ).cli()
