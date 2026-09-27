"""volume-attention (Failed standalone; kept as a sleeve for alt-sleeve-blend).

    w = volume_attention_weights(close, volume, btc_close)

Short the alts whose recent USD volume surged against their own history, long the quiet ones:
signal = mean cross-sectional rank of -log(mean vol[k] / mean vol[base, ending k days ago]) over
k in {7,14,30,60,90} x base in {180,365}; PIT top-20 universe; linear-rank dollar-neutral alt legs
(sum|w| = 1) plus a BTC leg that zeroes the EWM-60 beta; 30-day overlapping tranches.
Target weights at the close of t, applied to t+1 (research_lib.backtest_xs convention).
"""
import numpy as np
import pandas as pd


def pit_universe(close, volume, n_top=20, lookback=90, min_history=120, min_dv=5e6):
    med = volume.rolling(lookback, min_periods=lookback // 2).median()
    hist = close.notna().cumsum()
    elig = (hist >= min_history) & (med >= min_dv) & close.notna()
    return (med.where(elig).rank(axis=1, ascending=False) <= n_top) & elig


def ewm_beta(ret, mkt_ret, halflife=60):
    cov = ret.ewm(halflife=halflife, min_periods=halflife).cov(mkt_ret)
    var = mkt_ret.ewm(halflife=halflife, min_periods=halflife).var()
    return cov.div(var, axis=0)


def abn_volume(vol, k, base):
    num = vol.rolling(k, min_periods=max(2, int(k * 0.8))).mean()
    den = vol.rolling(base, min_periods=base // 3).mean().shift(k)
    return np.log(num / den)


def _rank_xs(sig, mask):
    r = sig.where(mask).rank(axis=1, pct=True)
    return r.sub(r.mean(axis=1), axis=0)


def volume_attention_weights(close, volume, btc_close, n_top=20, ks=(7, 14, 30, 60, 90),
                             bases=(180, 365), beta_halflife=60, hold=30, gross=1.0, hedge=True):
    mask = pit_universe(close, volume, n_top)
    s = sum(_rank_xs(-abn_volume(volume, k, b), mask).fillna(0) for k in ks for b in bases)
    s = (s / (len(ks) * len(bases))).where(mask)
    r = s.rank(axis=1, pct=True)
    r = r.sub(r.mean(axis=1), axis=0)
    w = r.div(r.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0) * gross
    if hedge:
        beta = ewm_beta(close.pct_change(), btc_close.reindex(close.index).pct_change(), beta_halflife)
        w["BTC-USD"] = -(w * beta.reindex_like(w)).sum(axis=1)
    return w.rolling(hold, min_periods=1).mean() if hold > 1 else w
