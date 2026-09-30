"""
Live (paper) runner for `crypto-perps/retail-crowding-xs` -- a cross-sectional contrarian
book on Binance's retail long/short ACCOUNT ratio, traded long/short on spot.

Spec:   alphas/crypto-perps/retail-crowding-xs/spec.md
Signal: code/crypto-perps/retail-crowding-xs/strategy.py :: target_weights()
        (imported with its spec defaults: n_top 20, q 0.3, hold 7, beta halflife 60,
        min_metric_days 60 -- nothing is restated here)
Report: past_research/crypto-perps/retail-crowding-xs/2026-09-30_retail_crowding_xs.md

Book. Long the 30 % of the PIT top-20 whose retail accounts are least net long, short the
30 % most net long, 0.5 gross per side, legs rescaled beta-neutral to BTC, mean of the last
7 daily books. It has a short leg, so it trades in the SIM book: SimPortfolioBroker,
allow_short=True, max_gross=1.0 (spec: "max 1.0 -- no leverage beyond 1x gross"; backtest
average 0.975). Fills at the yfinance daily close from the shared `data/` cache, which is
what `research_lib.backtest_xs` charged turnover at. No order book, no rejection, no partial
fill: weaker evidence than a venue fill.

Universe. The 64 yfinance tickers of `funding_panel.PERP_OF` (BTC-USD included), the same
set and quote source as live/crypto-alts/alt-sleeve-blend. Frozen: the ledger keys off it.

Data feeds, refreshed on every run:
  1. yfinance daily bars for the 64 legs (MarketData.daily, shared cache).
  2. The Binance USD-M `metrics` archive `data/<SYM>_metrics_5m.parquet`, topped up with the
     research's own `metrics_panel.fetch` (incremental, 1-day publication lag). Perps whose
     archive ended more than ARCHIVE_DEAD_DAYS ago are delisted (WAVES, XEM, OMG, MKR, EOS
     ...) and are not re-polled -- they have no ratio, so the eligibility rule drops them,
     exactly as in the backtest.
  3. The REST feed `globalLongShortAccountRatio` via `metrics_panel.fetch_rest`, which
     already re-stamps REST rows 5 minutes earlier onto the archive clock. It covers the
     days the archive has not published yet; archive values win where both exist, and a
     hole between the two raises.
  The daily value for D is then `metrics_panel.daily_from_frame` over the stitched frame:
  the last stamp before D 23:00 UTC -- the backtest's own builder, not a restatement.

Timing. yfinance stamps a crypto day at 00:00 UTC and publishes it while it is forming, so
every input is truncated to rows dated strictly before the current UTC day and the weight
is taken from the last COMPLETE bar -- weight at close D, applied to D+1's return
(backtest_xs convention). The daemon wakes at 00:30 UTC.

Cost. The research charges 10 bp per side on sum|dw| and nothing else: fee 10 bp,
slippage 0 bp. NOT modelled: short-leg borrow/funding carry on ~0.49 short notional.
"""
import logging
import os
import sys
from datetime import timezone

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(REPO, "code", "shared"))
sys.path.insert(0, os.path.join(REPO, "code", "crypto-alts", "shared"))
sys.path.insert(0, os.path.join(REPO, "code", "crypto-perps", "shared"))
sys.path.insert(0, os.path.join(REPO, "code", "crypto-perps", "retail-crowding-xs"))

import funding_panel as fp  # noqa: E402
import metrics_panel as mp  # noqa: E402
from live_lib import MarketData, YahooQuotes  # noqa: E402
from portfolio import PortfolioRunner, SimPortfolioBroker  # noqa: E402
from strategy import target_weights  # noqa: E402
from universe import clean_close, load_panel  # noqa: E402

log = logging.getLogger(__name__)

NAME = "crypto-perps/retail-crowding-xs"
SCHEDULE = "1d"
OFFSET_S = 1800.0                  # 00:30 UTC -- the daily bar rolls at 00:00
# This strategy's own book (sim, uncapped). See live_lib.allocate().
CAPITAL_USDT = 2_500.0
# Research cost: 10 bp per side on sum|dw|, nothing else (spec).
FEE_BPS = 10.0
SLIPPAGE_BPS = 0.0
MAX_GROSS = 1.0                    # spec: "max 1.0 -- no leverage beyond 1x gross"
# exp06_final.py (the headline run) loads prices from 2020-01-01 "for no warm-up edge
# effects"; the same start is used here so the EWM-60 beta sees the same history.
PRICE_START = "2020-01-01"
MIN_BARS = 400                     # 120-close history + 90d volume median + EWM beta warm-up
ARCHIVE_DEAD_DAYS = 30             # archive silent this long == delisted perp; REST keeps 30d
MIN_RATIO_NAMES = 10               # fewer ratios than this on D == the metrics feed broke

TRADED = list(fp.PERP_OF)          # 64 yfinance tickers, BTC-USD and ETH-USD included
RATIO = "count_long_short_ratio"

md = MarketData(source="public")   # used only for its shared daily cache


def _ratio_frame(sym, now):
    """Archive 5-minute frame for one perp, topped up and stitched with REST. None if the
    perp is dead (no archive in ARCHIVE_DEAD_DAYS and nothing on REST)."""
    arc = mp.load_metrics(sym)
    alive = arc is not None and arc.index.max() > now - pd.Timedelta(days=ARCHIVE_DEAD_DAYS)
    if not alive:
        return None if arc is None else arc[[RATIO]]
    try:
        mp.fetch(sym)
        arc = mp.load_metrics(sym)
    except Exception as e:  # noqa: BLE001 -- REST covers the gap; the hole check below catches the rest
        log.warning("metrics archive top-up %s failed: %s", sym, e)
    arc = arc[[RATIO]].dropna()
    need = int((now - arc.index.max()) / pd.Timedelta(minutes=5)) + 60
    try:
        rest = mp.fetch_rest(sym, RATIO, limit=min(need, 8000))
    except Exception as e:  # noqa: BLE001
        log.warning("REST %s failed: %s", sym, e)
        return arc
    if rest.empty:
        return arc
    if rest.index.min() > arc.index.max() + pd.Timedelta(minutes=5):
        log.warning("%s: hole between archive end %s and REST start %s -- dropping REST",
                    sym, arc.index.max(), rest.index.min())
        return arc
    rest = rest[rest.index > arc.index.max()].to_frame()
    return pd.concat([arc, rest]).sort_index()


def _ls_panel(index, now):
    """Daily ratio panel [date x ticker], built with the backtest's daily_from_frame."""
    cols = {}
    for ticker, sym in fp.PERP_OF.items():
        f = _ratio_frame(sym, now)
        if f is not None and len(f):
            cols[ticker] = mp.daily_from_frame(f, cutoff_hour=23, how="last")[RATIO]
    return pd.DataFrame(cols).reindex(index=index, columns=TRADED)


def compute_weights(now):
    """Target weights for the coming day, per spec.md, from the last COMPLETE daily bar."""
    for ticker in TRADED:
        try:
            md.daily(ticker, cache_hours=0.5)
        except Exception as e:  # noqa: BLE001
            log.warning("daily(%s) refresh failed: %s", ticker, e)

    panel = load_panel(TRADED)
    close = clean_close(panel["Close"])
    missing = [t for t in TRADED if t not in close.columns]
    if missing:
        raise RuntimeError(f"no cached series for {missing}; the panel is incomplete")
    close = close[TRADED]
    volume = panel["Volume"].reindex_like(close)

    # yfinance publishes the current UTC day as a forming bar. Trading on it would be a
    # same-bar signal -- the one lookahead this runner could introduce.
    today = pd.Timestamp(now.astimezone(timezone.utc).date())
    close = close.loc[PRICE_START:].loc[lambda d: d.index < today]
    volume = volume.reindex_like(close)
    if len(close) < MIN_BARS:
        raise RuntimeError(f"only {len(close)} closed daily bars; need >= {MIN_BARS}")
    last = close.index[-1]
    if (today - last).days > 2:
        raise RuntimeError(f"last closed bar is {last.date()}, {(today - last).days} days "
                           f"behind {today.date()} -- yfinance cache is stale")

    ls = _ls_panel(close.index, pd.Timestamp(now.astimezone(timezone.utc)).tz_localize(None))
    n_ratio = int(ls.loc[last].notna().sum())
    if n_ratio < MIN_RATIO_NAMES:
        raise RuntimeError(f"only {n_ratio} perps have a L/S ratio on {last.date()} -- the "
                           f"metrics feed is broken; the book would silently shrink")

    w = target_weights(close, volume, ls)
    row = w.loc[last]
    if not float(row.abs().sum()) > 0:
        raise RuntimeError(f"all weights are zero on {last.date()} -- the inputs are broken")
    log.info("bar %s: %d ratios, gross %.3f, net %+.3f, %d long / %d short", last.date(),
             n_ratio, row.abs().sum(), row.sum(), int((row > 0).sum()), int((row < 0).sum()))
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
            quotes=YahooQuotes(cache_hours=0.25),
        ),
        offset_s=OFFSET_S,
    ).cli()
