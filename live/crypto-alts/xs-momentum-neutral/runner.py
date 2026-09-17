"""
Live (paper) runner for `crypto-alts/xs-momentum-neutral` -- regime-hedged
betting-against-beta on a point-in-time universe of liquid altcoins.

Spec:   alphas/crypto-alts/xs-momentum-neutral/spec.md
Signal: code/crypto-alts/xs-momentum-neutral/strategy.py :: alt_bab_weights()
        (imported with its spec defaults, not restated)

Book. This is a long/SHORT cross-sectional basket of ~13 altcoins priced by yfinance,
so it trades in the SIM book: SimPortfolioBroker over the research's own candidate list,
allow_short=True, max_gross=1.0 -- the gross the research validated and never exceeds
(`alt_bab_weights` builds legs summing to exactly 1.0 before the 14-day tranche average,
and averaging can only shrink it). Fills are at the yfinance daily close out of the same
shared `data/` cache the backtest read, which is what `research_lib.backtest_xs` charged
turnover at. There is no order book, no rejection and no partial fill behind this track;
it is weaker evidence than a venue fill and must be read as such. Binance spot cannot
hold the short leg at all, which is why the venue book is not an option here.

Universe. The traded set is FROZEN to the 62 candidates that `universe.load_panel`
actually served on 2026-09-17 -- i.e. `ALTS` minus the 14 tickers Yahoo does not price
(UNI, APT, SUI, MATIC/POL, FTM, GRT, COMP, STX, PEPE, IMX, TAO, TON, TRUMP), which is
exactly the panel the backtest ran on. Freezing matters twice over: the ledger keys off
the symbol list, so a set that drifted between restarts would be read as a different book
and wiped; and if Yahoo ever starts serving one of those 14, the backtest still never saw
it, so the live book should not hold it either. Membership WITHIN the 62 is point-in-time
and rotates daily -- the other 49 names simply carry weight 0.

Timing. yfinance stamps a crypto day at 00:00 UTC and publishes that row while the day is
still running, so the last row of the cache is ALWAYS a forming bar. The research is a
decision at the close of day t applied to the return of t+1, so `compute_weights` drops
every row dated on or after the current UTC day and computes from the last COMPLETE bar.
The runner wakes once a day at 00:30 UTC -- half an hour after the bar rolls, to let all
62 legs print -- and `PortfolioRunner` acts only when the bar every leg agrees on changes.

Cost. The research charges 10 bp per side on sum|dw| and nothing else (spec §"Costs and
turnover"; its ladder: 0 bp -> 1.26, 10 -> 1.22, 20 -> 1.18, 30 -> 1.14). The broker is
built to charge exactly that: fee 10 bp, slippage 0 bp. NOT modelled here, and the
binding real-world risk per the report: short-leg funding/borrow, which the backtest
charges nothing for (10%/yr on short notional would take Sharpe 1.22 -> 1.04).
"""
import logging
import os
import sys
from datetime import timezone

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(REPO, "code", "crypto-alts", "shared"))
sys.path.insert(0, os.path.join(REPO, "code", "crypto-alts", "xs-momentum-neutral"))

from live_lib import MarketData, YahooQuotes  # noqa: E402
from portfolio import PortfolioRunner, SimPortfolioBroker  # noqa: E402
from strategy import alt_bab_weights  # noqa: E402
from universe import clean_close, load_panel  # noqa: E402

log = logging.getLogger(__name__)

NAME = "crypto-alts/xs-momentum-neutral"
SCHEDULE = "1d"
OFFSET_S = 1800.0                  # 00:30 UTC -- the daily bar rolls at 00:00
# This strategy's own book (sim, uncapped). See live_lib.allocate().
CAPITAL_USDT = 2_500.0
# Research cost: 10 bp per side on sum|dw|, nothing else (spec).
FEE_BPS = 10.0
SLIPPAGE_BPS = 0.0
MAX_GROSS = 1.0
BETA_REF = "BTC-USD"               # beta and regime reference; never traded
# Longest lookback is the 120-close history screen; the EWM-60 beta and the 90-day
# volume median sit inside it, and the 14-day tranche average on top. 600 days is
# comfortably past all of them -- but the cache is filled to DAILY_CACHE_START anyway,
# so this is a floor on what the signal is allowed to run on, not a fetch size.
MIN_BARS = 600

# The 62 alt candidates `universe.load_panel` served on 2026-09-17 -- the exact panel
# `08_final.py` backtested. Frozen: see the Universe note above.
TRADED = [
    "SOL-USD", "XRP-USD", "ADA-USD", "AVAX-USD", "LINK-USD", "DOT-USD", "LTC-USD",
    "BCH-USD", "XLM-USD", "EOS-USD", "TRX-USD", "ETC-USD", "XMR-USD", "NEO-USD",
    "IOTA-USD", "DASH-USD", "ZEC-USD", "ATOM-USD", "DOGE-USD", "BNB-USD", "VET-USD",
    "ALGO-USD", "FIL-USD", "AAVE-USD", "XTZ-USD", "NEAR-USD", "BSV-USD", "XEM-USD",
    "QTUM-USD", "OMG-USD", "ICP-USD", "OP-USD", "SHIB-USD", "HBAR-USD", "THETA-USD",
    "EGLD-USD", "SAND-USD", "MANA-USD", "AXS-USD", "MKR-USD", "SNX-USD",
    "CRV-USD", "LDO-USD", "INJ-USD", "RUNE-USD",
    "KSM-USD", "WAVES-USD", "ZIL-USD", "ONT-USD", "BAT-USD", "ENJ-USD", "CHZ-USD",
    "FLOW-USD", "KAVA-USD", "ONE-USD", "CAKE-USD", "TIA-USD", "SEI-USD", "WIF-USD",
    "RENDER-USD", "FET-USD", "BONK-USD",
]

md = MarketData(source="public")   # used only for its shared daily cache


def _refresh_cache():
    """Bring the shared `data/<TICKER>_d.parquet` files `load_panel` reads up to date.

    `universe.load_panel(cache=True)` reads the parquet and never downloads, so
    something has to refresh it. `YahooQuotes` has already refreshed the 62 traded legs
    by the time this runs (the runner prices the book before it computes weights), and
    `md.daily` skips anything whose file is younger than `cache_hours` -- so in practice
    this call fetches BTC-USD and nothing else.
    """
    for ticker in TRADED + [BETA_REF]:
        try:
            md.daily(ticker, cache_hours=0.5)
        except Exception as e:  # noqa: BLE001 - a stale leg is caught below, by date
            log.warning("daily(%s) refresh failed: %s", ticker, e)


def compute_weights(now):
    """Target weights for the coming day, per spec.md.

    Returns {symbol: weight} over the closed bars only: `alt_bab_weights` returns the
    weight known at the close of day t, which `research_lib.backtest_xs` applies to the
    return of t+1, so the last COMPLETE row is today's target.
    """
    _refresh_cache()
    panel = load_panel(tickers=TRADED + [BETA_REF], cache=True)
    close = clean_close(panel["Close"])
    volume = panel["Volume"].reindex(columns=close.columns)

    missing = [t for t in TRADED + [BETA_REF] if t not in close.columns]
    if missing:
        raise RuntimeError(f"no cached series for {missing}; the panel is incomplete")

    # yfinance publishes the current UTC day as a forming bar. Trading on it would be
    # a same-bar signal -- the one lookahead this runner could introduce.
    today = pd.Timestamp(now.astimezone(timezone.utc).date())
    close = close.loc[close.index < today]
    volume = volume.reindex(close.index)
    if len(close) < MIN_BARS:
        raise RuntimeError(f"only {len(close)} closed daily bars; need >= {MIN_BARS}")

    last = close.index[-1]
    if (today - last).days > 2:
        raise RuntimeError(f"last closed bar is {last.date()}, {(today - last).days} days "
                           f"behind {today.date()} -- yfinance cache is stale")

    alts = [t for t in TRADED if t in close.columns]
    w = alt_bab_weights(close[alts], volume[alts], close[BETA_REF])   # spec defaults
    row = w.loc[last]

    if not float(row.abs().sum()) > 0:
        raise RuntimeError(f"all weights are zero on {last.date()} -- the point-in-time "
                           f"universe is empty, which means the volume panel is broken")
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
