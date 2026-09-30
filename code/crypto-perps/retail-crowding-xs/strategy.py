"""retail-crowding-xs — contrarian cross-section on Binance's retail long/short account ratio,
traded on spot.

    w = target_weights(close, volume, ls_ratio)      # DataFrame [date x yfinance ticker]

Inputs (daily, calendar days, index = date D, columns = yfinance tickers such as "DOGE-USD"):
  close, volume  yfinance XXX-USD daily panels (Volume is USD notional). Row D closes at
                 D+1 00:00 UTC.
  ls_ratio       Binance USD-M `count_long_short_ratio` (global accounts net long / net short;
                 REST: /futures/data/globalLongShortAccountRatio) of the coin's USDT perp, one
                 value per day = the last 5-minute value whose ARCHIVE stamp is before D 23:00
                 UTC (REST stamps are 5 min later: use REST rows stamped <= D 23:00).
                 Build it with code/crypto-perps/shared/metrics_panel.py:
                   daily_metrics(syms)["count_long_short_ratio"]   (archive files on disk)
                   daily_from_frame(fetch_rest(sym).to_frame())    (live, last 30 days)
                 Ticker <-> perp symbol map: funding_panel.PERP_OF (1000SHIB, 1000BONK ...).

Rule (every parameter defaulted to the spec in alphas/crypto-perps/retail-crowding-xs/spec.md):
  1. universe  PIT top-`n_top` by trailing-90d median USD volume among coins with >= 120
               closes, median volume >= $1M, a ratio today and >= `min_metric_days` days of
               ratio history
  2. signal    -log(ls_ratio): the coins whose retail accounts are most net-long are shorted
  3. book      long the top 30 % / short the bottom 30 % of the universe, equal weight,
               0.5 gross per side, then legs rescaled so the book is beta-neutral to BTC
               (EWM-60 beta of daily returns)
  4. holding   7 staggered tranches == the mean of the last 7 daily target books
Weights are known at the close of D and apply from D+1 (research_lib.backtest_xs convention).
Gross ~0.93, net ~0, max gross 1.0. Includes BTC-USD as an ordinary member.
"""
import numpy as np
import pandas as pd

DEFAULTS = dict(n_top=20, q=0.3, hold=7, beta_halflife=60, min_metric_days=60, min_history=120,
                min_median_volume=1e6)


def pit_mask(close, volume, ls_ratio, n_top=20, min_metric_days=60, min_history=120,
             min_median_volume=1e6):
    med = volume.rolling(90, min_periods=45).median()
    hist = close.notna().cumsum()
    has_m = ls_ratio.notna().cumsum() >= min_metric_days
    elig = (hist >= min_history) & (med >= min_median_volume) & close.notna() & has_m & ls_ratio.notna()
    return (med.where(elig).rank(axis=1, ascending=False) <= n_top) & elig


def btc_beta(close, halflife=60):
    ret = close.pct_change(fill_method=None)
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


def target_weights(close, volume, ls_ratio, n_top=20, q=0.3, hold=7, beta_halflife=60,
                   min_metric_days=60, min_history=120, min_median_volume=1e6):
    ls_ratio = ls_ratio.reindex(index=close.index, columns=close.columns)
    ls_ratio = ls_ratio.where(ls_ratio > 0)
    volume = volume.reindex_like(close)
    mask = pit_mask(close, volume, ls_ratio, n_top, min_metric_days, min_history, min_median_volume)
    sig = -np.log(ls_ratio)
    w = beta_neutral(quantile_ls(sig, mask, q), btc_beta(close, beta_halflife))
    return tranche(w, hold)
