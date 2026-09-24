"""funding-xs-crowding — contrarian cross-sectional perp-funding sleeve, traded on spot.

STATUS: Failed as a standalone alpha (full-sample Sharpe 0.80, OOS 0.99, deflated Sharpe 0.22
over 199 trials). Kept as a reusable function because the sleeve is uncorrelated (0.04) with
betting-against-beta and may be worth adding to the live crypto-alts BAB book; see the report.

target_weights(close, volume, funding) -> DataFrame[date x ticker]
  close, volume : daily yfinance panels (USD volume), columns = yfinance tickers ("SOL-USD")
  funding       : daily sum of Binance USDT-M funding usable at the close of each date
                  (see code/crypto-perps/shared/funding_panel.daily_funding, lag_hours=8)
Weights are known at the close of day t and are to be applied from t+1 (research_lib.backtest_xs
convention). Dollar-neutral-ish, beta-neutral to BTC, gross ~1.
"""
import numpy as np
import pandas as pd

DEFAULTS = dict(n_top=20, lookbacks=(14, 30, 60, 90), q=0.3, hold=7, beta_halflife=60,
                min_funding_days=30)


def pit_mask(close, volume, funding, n_top=20, min_funding_days=30):
    med = volume.rolling(90, min_periods=45).median()
    hist = close.notna().cumsum()
    has_f = funding.notna().cumsum() >= min_funding_days
    elig = (hist >= 120) & (med >= 1e6) & close.notna() & has_f & funding.notna()
    return (med.where(elig).rank(axis=1, ascending=False) <= n_top) & elig


def btc_beta(close, halflife=60):
    ret = close.pct_change()
    btc = ret["BTC-USD"]
    cov = ret.ewm(halflife=halflife, min_periods=60).cov(btc)
    return cov.div(btc.ewm(halflife=halflife, min_periods=60).var(), axis=0).clip(-0.5, 3.0)


def beta_neutral(w, beta):
    b = beta.reindex_like(w).fillna(1.0)
    lw, sw = w.clip(lower=0), w.clip(upper=0)
    bl, bs = (lw * b).sum(axis=1), -(sw * b).sum(axis=1)
    return (lw.mul(2 * bs / (bl + bs), axis=0) + sw.mul(2 * bl / (bl + bs), axis=0)).fillna(0.0)


def quantile_ls(sig, mask, q=0.3):
    s = sig.where(mask)
    k = (s.notna().sum(axis=1) * q).round().clip(lower=1)
    long = s.rank(axis=1, ascending=False).le(k, axis=0) & s.notna()
    short = s.rank(axis=1, ascending=True).le(k, axis=0) & s.notna()
    w = long.astype(float).div(long.sum(axis=1).replace(0, np.nan), axis=0) * 0.5 \
        - short.astype(float).div(short.sum(axis=1).replace(0, np.nan), axis=0) * 0.5
    return w.fillna(0.0)


def tranche(w, h):
    if h <= 1:
        return w
    parts = []
    for off in range(h):
        keep = pd.Series((np.arange(len(w)) - off) % h == 0, index=w.index)
        parts.append(w.where(keep, np.nan).ffill().fillna(0.0))
    return sum(parts) / h


def target_weights(close, volume, funding, n_top=20, lookbacks=(14, 30, 60, 90), q=0.3,
                   hold=7, beta_halflife=60, min_funding_days=30):
    funding = funding.reindex(index=close.index, columns=close.columns)
    volume = volume.reindex_like(close)
    mask = pit_mask(close, volume, funding, n_top, min_funding_days)
    ranks = [(-funding.rolling(L, min_periods=int(L * 0.7)).mean()).where(mask).rank(axis=1, pct=True)
             for L in lookbacks]
    sig = sum(ranks) / len(ranks)
    w = beta_neutral(quantile_ls(sig, mask, q), btc_beta(close, beta_halflife))
    return tranche(w, hold)
