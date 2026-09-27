"""
Live (paper) runner for `crypto-alts/alt-sleeve-blend` -- a constant-risk-weight blend of
four uncorrelated long/short liquid-alt sleeves (regime-hedged BAB, token dilution,
abnormal-volume attention, perp-funding crowding), netted at the weight level.

Spec:   alphas/crypto-alts/alt-sleeve-blend/spec.md
Signal: code/crypto-alts/alt-sleeve-blend/strategy.py :: blend_weights()
        (imported with its spec defaults -- RISK_WEIGHTS fixed on 2018-22, LEVERAGE 2.0 --
        and every sleeve with its own spec defaults; nothing is restated here)

Book. A long/SHORT basket of up to 64 yfinance crypto tickers at gross up to 2.0, so it
trades in the SIM book: SimPortfolioBroker, allow_short=True, max_gross=2.0 -- the spec's
"Max leverage: gross 2.0", the validated range at LEVERAGE = 2.0 (backtest average 1.08,
max 2.003 on one day; that day would be scaled by 0.9984). Fills are at the yfinance daily
close from the shared `data/` cache, which is what `research_lib.backtest_xs` charged
turnover at. No order book, no rejection, no partial fill: weaker evidence than a venue
fill. Binance spot cannot hold the short legs, so the venue book is not an option.

Universe. Frozen to the 64 columns of the research's `weights_final.parquet`: the 62 alt
candidates `universe.load_panel` actually served (ALTS minus the 14 Yahoo does not price)
plus BTC-USD (hedge legs, funding-sleeve name) and ETH-USD (funding sleeve only). That set
equals `funding_panel.PERP_OF`, so both input panels are loaded over it. `strategy.load_inputs`
calls `load_panel()` with the unfrozen candidate list, which re-tries a yfinance download of
the 14 unpriced tickers on every call and would silently admit one if Yahoo ever started
serving it; `_load_inputs` below is the same function body with the list frozen, and the
deploy check verified it returns identical inputs.

Data freshness -- the three feeds the spec's "Live data dependencies" names:
  1. yfinance daily bars: YahooQuotes refreshes the traded legs before compute_weights runs;
     `_refresh_cache` tops up anything it missed.
  2. CoinMarketCap weekly snapshots (dilution sleeve): `cmc.fetch_weekly` is incremental --
     it only requests Sundays missing from data/CMC_listings_weekly.parquet -- so it is
     called on every run. If it goes stale the sleeve drops names after 10 days of
     forward-fill (the research's own rule); we log a warning rather than override it.
  3. Binance USD-M funding (funding sleeve): nothing else refreshes these files, so every
     run extends each `data/<SYM>_fundingRate.parquet` from 3 days before its last stamp.
     If NO name has a funding value on the decision bar, the refresh failed wholesale and
     the sleeve would silently go flat -- that raises and the day is retried.

Timing. yfinance stamps a crypto day at 00:00 UTC and publishes it while it is forming,
so every input is truncated to rows dated strictly before the current UTC day and the
weight is taken from the last COMPLETE bar -- the research convention (weight at close t,
applied to t+1). Funding keeps its 8h safety lag (`daily_funding(lag_hours=8)`, inside
`strategy.load_inputs`' logic) and CMC snapshots their +1 day known-lag (`cmc.wide`).
The daemon wakes at 00:30 UTC, after the 00:00 roll and the 00:00 funding settlement.

Cost. The research charges 10 bp per side on the netted sum|dw| and nothing else, so the
broker charges fee 10 bp, slippage 0 bp. NOT modelled: short-leg carry (report: 10 %/yr on
the ~0.48 average short notional takes OOS Sharpe 1.31 -> 1.09).
"""
import logging
import os
import sys
from datetime import timezone

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(REPO, "code", "crypto-alts", "shared"))
sys.path.insert(0, os.path.join(REPO, "code", "crypto-perps", "shared"))
sys.path.insert(0, os.path.join(REPO, "code", "crypto-alts", "alt-sleeve-blend"))

import cmc  # noqa: E402
import funding_panel as fp  # noqa: E402
from live_lib import MarketData, YahooQuotes  # noqa: E402
from portfolio import PortfolioRunner, SimPortfolioBroker  # noqa: E402
from strategy import blend_weights  # noqa: E402
from universe import ALTS, clean_close, load_panel  # noqa: E402

log = logging.getLogger(__name__)

NAME = "crypto-alts/alt-sleeve-blend"
SCHEDULE = "1d"
OFFSET_S = 1800.0                  # 00:30 UTC -- the daily bar rolls at 00:00
# This strategy's own book (sim, uncapped). See live_lib.allocate().
CAPITAL_USDT = 2_500.0
# Research cost: 10 bp per side on the netted sum|dw|, nothing else (spec).
FEE_BPS = 10.0
SLIPPAGE_BPS = 0.0
MAX_GROSS = 2.0                    # spec: "Max leverage: gross 2.0"
# Longest lookback: the 365-day volume base shifted by up to 90 days (volume sleeve),
# then a 30-day tranche average. The cache runs from DAILY_CACHE_START anyway; this is a
# floor on what the signal may run on, not a fetch size.
MIN_BARS = 600
FUNDING_REFETCH_DAYS = 3

# The 64 columns of code/crypto-alts/alt-sleeve-blend/weights_final.parquet, i.e. the
# exact priced set the research backtested (== funding_panel.PERP_OF). Frozen: the ledger
# keys off this list.
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
    "BTC-USD", "ETH-USD",
]
PANEL = ["BTC-USD", "ETH-USD"] + [t for t in ALTS if t in TRADED]   # MAJORS + ALTS order

md = MarketData(source="public")   # used only for its shared daily cache


def _refresh_cache():
    """Bring every external input up to date. Failures are logged; staleness is caught
    by date in compute_weights."""
    for ticker in TRADED:
        try:
            md.daily(ticker, cache_hours=0.5)
        except Exception as e:  # noqa: BLE001
            log.warning("daily(%s) refresh failed: %s", ticker, e)
    for sym in fp.PERP_OF.values():
        try:
            old = fp.load_funding(sym)
            start = ((old.index[-1] - pd.Timedelta(days=FUNDING_REFETCH_DAYS)).strftime("%Y-%m-%d")
                     if old is not None and len(old) else "2019-09-01")
            fp.fetch_funding_rest(sym, start=start)
        except Exception as e:  # noqa: BLE001
            log.warning("funding refresh %s failed: %s", sym, e)
    try:
        cmc.fetch_weekly(verbose=False)
    except Exception as e:  # noqa: BLE001
        log.warning("CMC weekly snapshot refresh failed: %s", e)


def _load_inputs():
    """`strategy.load_inputs(refresh_cmc=False)` with the ticker list frozen to TRADED.

    Same body: token-dilution/strategy.py::load_inputs for close/volume/btc/circ_supply,
    alt-sleeve-blend/strategy.py::load_inputs for the funding panels.
    """
    p = load_panel(PANEL)
    close = clean_close(p["Close"])
    alts = [t for t in ALTS if t in close]
    snaps = cmc.load_weekly()
    idmap = cmc.yahoo_map(close[alts], snaps)
    circ = cmc.wide("circulatingSupply", idmap, snaps, close.index)
    inp = dict(close=close[alts], volume=p["Volume"].reindex(columns=close.columns)[alts],
               btc_close=close["BTC-USD"], circ_supply=circ)

    pan = load_panel(list(fp.PERP_OF))
    fc = clean_close(pan["Close"])
    fv = pan["Volume"].reindex_like(fc)
    fund = fp.daily_funding(list(fc.columns))[0].reindex(index=fc.index, columns=fc.columns)
    inp.update(fund_close=fc.loc["2020-01-01":], fund_volume=fv.loc["2020-01-01":],
               funding=fund.loc["2020-01-01":])
    return inp, snaps


def compute_weights(now):
    """Target weights for the coming day, per spec.md, from the last COMPLETE daily bar."""
    _refresh_cache()
    inp, snaps = _load_inputs()

    missing = [t for t in TRADED if t not in inp["fund_close"].columns]   # PERP_OF == TRADED
    if missing:
        raise RuntimeError(f"no cached series for {missing}; the panel is incomplete")

    # yfinance publishes the current UTC day as a forming bar. Trading on it would be a
    # same-bar signal -- the one lookahead this runner could introduce.
    today = pd.Timestamp(now.astimezone(timezone.utc).date())
    inp = {k: v.loc[v.index < today] for k, v in inp.items()}
    close = inp["close"]
    if len(close) < MIN_BARS:
        raise RuntimeError(f"only {len(close)} closed daily bars; need >= {MIN_BARS}")
    last = close.index[-1]
    if (today - last).days > 2:
        raise RuntimeError(f"last closed bar is {last.date()}, {(today - last).days} days "
                           f"behind {today.date()} -- yfinance cache is stale")

    if not inp["funding"].loc[last].notna().any():
        raise RuntimeError(f"no Binance funding on {last.date()} for any name -- the funding "
                           f"refresh failed; the funding sleeve would silently go flat")
    snap_age = (last - snaps["date"].max()).days
    if snap_age > 10:
        log.warning("latest CMC snapshot is %s (%d days before %s): the dilution sleeve is "
                    "dropping names under its 10-day forward-fill limit",
                    snaps["date"].max().date(), snap_age, last.date())

    w = blend_weights(inp)                     # RISK_WEIGHTS, LEVERAGE = 2.0 (spec)
    row = w.loc[last]
    if not float(row.abs().sum()) > 0:
        raise RuntimeError(f"all weights are zero on {last.date()} -- the inputs are broken")
    unknown = sorted(s for s, v in row.items() if v != 0 and s not in TRADED)
    if unknown:
        raise RuntimeError(f"blend holds names outside the frozen universe: {unknown}")
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
