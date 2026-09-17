"""xs-momentum-neutral -> final mechanism: regime-hedged betting-against-beta on liquid alts.

    weights = alt_bab_weights(close, volume, btc_close)

close, volume : DataFrame [date x ticker] of daily USD close and USD volume for the alt
                candidate list (yfinance `Volume` for crypto is already in USD).
btc_close     : Series of BTC-USD daily close (regime + beta reference).

Returns a DataFrame of TARGET weights known at the close of day t, to be applied to the
return of day t+1 (exactly what `research_lib.backtest_xs` does). Gross exposure <= 1.
Every default is the value in alphas/crypto-alts/xs-momentum-neutral/spec.md.
"""
import numpy as np
import pandas as pd


def pit_universe(close, volume, n_top=20, lookback=90, min_history=120, min_dv=5e6):
    """Top-`n_top` names by trailing `lookback`-day median USD volume among names with at
    least `min_history` closes and median volume >= `min_dv`. Past data only."""
    med = volume.rolling(lookback, min_periods=lookback // 2).median()
    hist = close.notna().cumsum()
    elig = (hist >= min_history) & (med >= min_dv) & close.notna()
    ranked = med.where(elig).rank(axis=1, ascending=False)
    return (ranked <= n_top) & elig


def ewm_beta(ret, mkt_ret, halflife=60):
    cov = ret.ewm(halflife=halflife, min_periods=halflife).cov(mkt_ret)
    var = mkt_ret.ewm(halflife=halflife, min_periods=halflife).var()
    return cov.div(var, axis=0)


def _tercile_legs(beta, mask, q):
    b = beta.where(mask)
    n = b.notna().sum(axis=1)
    k = (n * q).round().clip(lower=1)
    lo = b.rank(axis=1, ascending=True).le(k, axis=0) & b.notna()     # lowest beta -> long
    hi = b.rank(axis=1, ascending=False).le(k, axis=0) & b.notna()    # highest beta -> short
    L = lo.astype(float).div(lo.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    S = hi.astype(float).div(hi.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return L, S, b


def alt_bab_weights(close, volume, btc_close, n_top=20, dv_lookback=90, min_history=120,
                    min_dv=5e6, beta_halflife=60, q=0.3, regime_sma=50, hold=14,
                    bear_target_beta=None, gross=1.0):
    """Regime-hedged betting-against-beta.

    Long the lowest-beta tercile, short the highest-beta tercile of the point-in-time
    universe (equal weight within legs, tercile on EWM beta to BTC). Leg sizes a, b with
    a + b = gross are solved so that the portfolio beta hits a target:
      * BTC above its `regime_sma` SMA (bull): target beta 0 (beta-neutral, net long $);
        `regime_sma=None` means always beta-neutral;
      * BTC below (bear): dollar-neutral legs (a = b), whose beta is naturally negative,
        or `bear_target_beta` if given.
    Daily target weights are averaged over the last `hold` days (overlapping tranches).
    """
    ret = close.pct_change()
    btc_ret = btc_close.pct_change()
    mask = pit_universe(close, volume, n_top, dv_lookback, min_history, min_dv)
    beta = ewm_beta(ret, btc_ret, beta_halflife)
    L, S, b = _tercile_legs(beta, mask, q)
    bL = (L * b).sum(axis=1)
    bS = (S * b).sum(axis=1)
    if regime_sma is None:                                # always beta-neutral
        bull = pd.Series(True, index=close.index)
    else:
        bull = (btc_close > btc_close.rolling(regime_sma).mean()).reindex(close.index).fillna(False)
    # solve a*bL - (gross-a)*bS = target  ->  a = (target + gross*bS) / (bL + bS)
    if bear_target_beta is None:
        target_bear = (bL - bS) * gross / 2.0             # = dollar-neutral beta
    else:
        target_bear = pd.Series(bear_target_beta, index=close.index)
    target = pd.Series(0.0, index=close.index).where(bull, target_bear)
    denom = (bL + bS).replace(0, np.nan)
    a = ((target + gross * bS) / denom).clip(0.0, gross)
    a = a.where(bull, gross / 2.0) if bear_target_beta is None else a
    w = L.mul(a, axis=0) - S.mul(gross - a, axis=0)
    w = w.fillna(0.0)
    if hold > 1:
        w = w.rolling(hold, min_periods=1).mean()
    return w
