"""token-dilution -> short the alts whose circulating supply grew most over 12 weeks, long the
least-diluted, BTC-beta-hedged, 30-day overlapping tranches.

    inputs = load_inputs()                    # from the flat data/ cache (+ CMC snapshots)
    weights = dilution_weights(**inputs)

close, volume : DataFrame [date x yfinance ticker], daily USD close / USD volume of the alt
                candidate list (yfinance crypto `Volume` is already USD).
btc_close     : Series, BTC-USD daily close (beta reference and hedge instrument).
circ_supply   : DataFrame [date x ticker], circulating supply as KNOWN on each date: weekly
                CoinMarketCap snapshots re-stamped to snapshot date + 1 day and forward-filled
                (`code/crypto-alts/shared/cmc.py::wide`). Missing = coin not tradable by this book.

Returns TARGET weights known at the close of day t (columns: alts + "BTC-USD"), applied to the
return of day t+1 exactly as `research_lib.backtest_xs` does. Alt legs are dollar-neutral with
sum|w| = 1 before the BTC hedge; the BTC leg zeroes the EWM-60 beta. Every default is the value in
alphas/crypto-alts/token-dilution/spec.md.
"""
import os
import sys

import numpy as np
import pandas as pd


def pit_universe(close, volume, n_top=20, lookback=90, min_history=120, min_dv=5e6):
    """Top-`n_top` by trailing `lookback`-day median USD volume among names with >= `min_history`
    closes and median volume >= `min_dv`. Past data only (same rule as xs-momentum-neutral)."""
    med = volume.rolling(lookback, min_periods=lookback // 2).median()
    hist = close.notna().cumsum()
    elig = (hist >= min_history) & (med >= min_dv) & close.notna()
    ranked = med.where(elig).rank(axis=1, ascending=False)
    return (ranked <= n_top) & elig


def ewm_beta(ret, mkt_ret, halflife=60):
    cov = ret.ewm(halflife=halflife, min_periods=halflife).cov(mkt_ret)
    var = mkt_ret.ewm(halflife=halflife, min_periods=halflife).var()
    return cov.div(var, axis=0)


def dilution_signal(circ_supply, weeks=12, clip=(-1.0, 2.0)):
    """Negative log growth of circulating supply over `weeks` weeks (higher = less dilution)."""
    c = circ_supply.where(circ_supply > 0)
    return -np.log(c / c.shift(7 * weeks)).clip(*clip)


def dilution_weights(close, volume, btc_close, circ_supply, n_top=20, dv_lookback=90,
                     min_history=120, min_dv=5e6, weeks=12, beta_halflife=60, hold=30,
                     gross=1.0, hedge=True):
    circ_supply = circ_supply.reindex(index=close.index, columns=close.columns)
    mask = pit_universe(close, volume, n_top, dv_lookback, min_history, min_dv) & circ_supply.notna()
    sig = dilution_signal(circ_supply, weeks).where(mask)
    # cross-sectional percentile rank, demeaned -> linear weights with sum|w| = gross
    r = sig.rank(axis=1, pct=True)
    r = r.sub(r.mean(axis=1), axis=0)
    w = r.div(r.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0) * gross
    if hedge:
        beta = ewm_beta(close.pct_change(), btc_close.reindex(close.index).pct_change(), beta_halflife)
        w["BTC-USD"] = -(w * beta.reindex_like(w)).sum(axis=1)
    if hold > 1:
        w = w.rolling(hold, min_periods=1).mean()
    return w


def load_inputs(refresh_cmc=False):
    """Build the inputs from the shared cache. `refresh_cmc=True` appends any missing weekly CMC
    snapshots first (incremental; the live runner should do this once a week)."""
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(here, "..", "shared"))
    import cmc
    from universe import load_panel, clean_close, ALTS
    p = load_panel()
    close = clean_close(p["Close"])
    alts = [t for t in ALTS if t in close]
    snaps = cmc.fetch_weekly(verbose=False) if refresh_cmc else cmc.load_weekly()
    idmap = cmc.yahoo_map(close[alts], snaps)
    circ = cmc.wide("circulatingSupply", idmap, snaps, close.index)
    return dict(close=close[alts], volume=p["Volume"].reindex(columns=close.columns)[alts],
                btc_close=close["BTC-USD"], circ_supply=circ)
