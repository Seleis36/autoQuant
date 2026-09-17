"""Shared research harness for autoQuant BTC strategy research.

Conventions (lookahead-safe):
  * All signals are computed from data available up to and including the CLOSE of day t.
  * The resulting weight is applied to the return of day t+1 (we shift weights by 1).
  * Costs are charged on |w_t - w_{t-1}| at a per-side rate.
"""
import os
import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_ROOT, "data")
ANN = 365.0  # crypto trades every day

#: Earliest bar the shared `data/` cache is filled back to. Must stay equal to
#: `live_lib.DAILY_CACHE_START`: research and the live runners read and write the same
#: files, so while the two disagreed, whichever reached a ticker first decided how far
#: back the other could see it.
DAILY_CACHE_START = "2010-01-01"

# ---------------------------------------------------------------- data

def daily_cache_path(ticker):
    """The one true filename for a daily series, shared with `harness/live_lib.py`.

    Kept byte-identical to `live_lib.daily_cache_path` on purpose: the two modules
    read and write the same `data/` directory, and when their naming rules disagreed
    `^GSPC` ended up cached twice, as two independently-refreshed partial copies.
    """
    stem = ticker.replace("-", "_").replace("^", "IDX_")
    return os.path.join(DATA_DIR, f"{stem}_d.parquet")


def _atomic_parquet(df, path):
    """Write a cache file a concurrent reader can never catch half-written.

    Research agents run concurrently and `data/` is shared with the live runners, so
    two processes refreshing one ticker do overlap. The pid in the temp name keeps
    those writers from clobbering each other's partial file.
    """
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        df.to_parquet(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_btc(start="2014-01-01", end=None, cache=True, ticker="BTC-USD"):
    """Daily OHLCV for BTC-USD from yfinance, with a local parquet cache."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = daily_cache_path(ticker)
    if cache and os.path.exists(path):
        df = pd.read_parquet(path)
    else:
        import yfinance as yf
        df = yf.download(ticker, start=start, end=end, auto_adjust=True,
                         progress=False, multi_level_index=False)
        df = df.dropna()
        _atomic_parquet(df, path)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def load_series(ticker, start=DAILY_CACHE_START, end=None, cache=True):
    """Daily close for any yfinance ticker (for macro overlays)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = daily_cache_path(ticker)
    if cache and os.path.exists(path):
        df = pd.read_parquet(path)
    else:
        import yfinance as yf
        df = yf.download(ticker, start=start, end=end, auto_adjust=True,
                         progress=False, multi_level_index=False)
        df = df.dropna()
        _atomic_parquet(df, path)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[~df.index.duplicated(keep="last")].sort_index()


# ---------------------------------------------------------------- metrics

def perf_stats(ret, ann=ANN, name="strategy"):
    """ret: pd.Series of periodic strategy returns (already net of costs)."""
    ret = pd.Series(ret).dropna()
    n = len(ret)
    if n < 2:
        return pd.Series(dtype=float, name=name)
    eq = (1 + ret).cumprod()
    yrs = n / ann
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1.0
    vol = ret.std(ddof=1) * np.sqrt(ann)
    sharpe = ret.mean() / ret.std(ddof=1) * np.sqrt(ann) if ret.std(ddof=1) > 0 else np.nan
    dn = ret[ret < 0].std(ddof=1)
    sortino = ret.mean() / dn * np.sqrt(ann) if dn and dn > 0 else np.nan
    dd = eq / eq.cummax() - 1
    mdd = dd.min()
    calmar = cagr / abs(mdd) if mdd < 0 else np.nan
    # Newey-West t-stat on the mean (lag ~ 1 month) for statistical significance
    t_nw = newey_west_t(ret.values, lags=21)
    return pd.Series({
        "CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "Sortino": sortino,
        "MaxDD": mdd, "Calmar": calmar,
        "Skew": ret.skew(), "Kurt": ret.kurtosis(),
        "HitRate": (ret > 0).mean(), "t_NW": t_nw, "N": n,
    }, name=name)


def newey_west_t(x, lags=21):
    """t-stat of the mean of x with Newey-West HAC standard errors."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 30:
        return np.nan
    mu = x.mean()
    e = x - mu
    g0 = (e @ e) / n
    s = g0
    for L in range(1, min(lags, n - 1) + 1):
        g = (e[L:] @ e[:-L]) / n
        s += 2 * (1 - L / (lags + 1)) * g
    if s <= 0:
        return np.nan
    return mu / np.sqrt(s / n)


def deflated_sharpe(sr, n_obs, n_trials, skew=0.0, kurt=3.0, ann=ANN):
    """Bailey & Lopez de Prado Deflated Sharpe Ratio.
    sr: annualised Sharpe. Returns probability the true SR > 0 after
    correcting for multiple testing over `n_trials` independent trials."""
    from scipy.stats import norm
    sr_p = sr / np.sqrt(ann)                     # per-period SR
    if n_trials < 2:
        sr0 = 0.0
    else:
        e = 0.5772156649
        z1 = norm.ppf(1 - 1.0 / n_trials)
        z2 = norm.ppf(1 - 1.0 / (n_trials * np.e))
        sr0 = (1 - e) * z1 + e * z2              # expected max SR under null (std-normal units)
        sr0 *= 1.0                                # variance of trial SRs assumed 1 (std units)
    # SR estimator standard error accounting for non-normality
    se = np.sqrt((1 - skew * sr_p + (kurt - 1) / 4.0 * sr_p ** 2) / (n_obs - 1))
    # sr0 above is in units of the SR sampling std-dev
    return float(norm.cdf((sr_p - sr0 * se) / se))


# ---------------------------------------------------------------- backtest engine

def backtest(weights, close, cost_bps=10.0, ann=ANN, name="strategy"):
    """Fast vectorised long/flat (or leveraged) backtest.

    weights : pd.Series of TARGET weights known at the CLOSE of each day t.
    close   : pd.Series of closes.
    Returns (net_returns, stats).  Weight is shifted by 1 day => no lookahead.
    """
    w = pd.Series(weights).reindex(close.index).fillna(0.0)
    r = close.pct_change().fillna(0.0)
    w_eff = w.shift(1).fillna(0.0)                     # applied to next day's return
    turn = (w_eff - w_eff.shift(1).fillna(0.0)).abs()  # trade happens at that close
    gross = w_eff * r
    net = gross - turn * (cost_bps / 1e4)
    net.name = name
    stats = perf_stats(net, ann=ann, name=name)
    stats["Turnover_ann"] = turn.sum() / (len(turn) / ann)
    stats["AvgExposure"] = w_eff.mean()
    stats["TimeInMkt"] = (w_eff > 0).mean()
    return net, stats


def split_stats(net, splits, ann=ANN):
    """net: series of returns. splits: dict name -> (start, end)."""
    rows = {}
    for k, (a, b) in splits.items():
        seg = net.loc[a:b]
        rows[k] = perf_stats(seg, ann=ann, name=k)
    return pd.DataFrame(rows).T


# ---------------------------------------------------------------- signal helpers

def realized_vol(ret, window=30, ann=ANN):
    return ret.rolling(window).std(ddof=1) * np.sqrt(ann)


def ewm_vol(ret, halflife=20, ann=ANN):
    return ret.ewm(halflife=halflife, min_periods=halflife).std() * np.sqrt(ann)


def vol_target_scalar(ret, target=0.40, halflife=20, cap=1.0, floor=0.0, ann=ANN):
    """Inverse-vol position scalar, capped. Uses only past returns."""
    v = ewm_vol(ret, halflife=halflife, ann=ann)
    s = (target / v).clip(lower=floor, upper=cap)
    return s.fillna(0.0)


def macd_trend(close, fast, slow, scale_win=63, vol_win=252):
    """Baz et al. (2015) normalised MACD trend strength, in std units."""
    m = close.ewm(halflife=fast).mean() - close.ewm(halflife=slow).mean()
    q = m / close.rolling(scale_win).std(ddof=1)
    z = q / q.rolling(vol_win).std(ddof=1)
    return z


def fmt(df, cols=None):
    df = df.copy()
    pct = ["CAGR", "Vol", "MaxDD", "HitRate", "AvgExposure", "TimeInMkt"]
    for c in df.columns:
        if c in pct:
            df[c] = (df[c] * 100).round(1)
        elif c in ("N",):
            df[c] = df[c].astype(int)
        else:
            df[c] = df[c].round(2)
    return df[cols] if cols else df


# ---------------------------------------------------------------- cross-sectional (multi-asset) helpers
# Added 2026-09-17 by crypto-alts research. Asset-agnostic: pass `ann` for the calendar.

def rank_xs(sig, mask=None):
    """Cross-sectional percentile rank in [-0.5, 0.5] per row over the masked universe."""
    s = sig.where(mask) if mask is not None else sig
    r = s.rank(axis=1, pct=True)
    return r.sub(r.mean(axis=1), axis=0)


def quantile_weights(sig, mask, q=0.3, gross=1.0, long_only=False):
    """Long top-q / short bottom-q, equal weight per side, each side gross/2 (dollar-neutral).
    With long_only=True: long top-q only, total gross."""
    s = sig.where(mask)
    n = s.notna().sum(axis=1)
    k = (n * q).round().clip(lower=1)
    r_hi = s.rank(axis=1, ascending=False)
    long = r_hi.le(k, axis=0) & s.notna()
    if long_only:
        return long.astype(float).div(long.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0) * gross
    r_lo = s.rank(axis=1, ascending=True)
    short = r_lo.le(k, axis=0) & s.notna()
    w = long.astype(float).div(long.sum(axis=1).replace(0, np.nan), axis=0) * (gross / 2) \
        - short.astype(float).div(short.sum(axis=1).replace(0, np.nan), axis=0) * (gross / 2)
    return w.fillna(0.0)


def linear_weights(sig, mask, gross=1.0):
    """Weights proportional to the demeaned signal, scaled to total |w| = gross. Dollar-neutral."""
    s = sig.where(mask)
    s = s.sub(s.mean(axis=1), axis=0)
    denom = s.abs().sum(axis=1).replace(0, np.nan)
    return s.div(denom, axis=0).fillna(0.0) * gross


def backtest_xs(weights, close, cost_bps=10.0, ann=ANN, name="xs"):
    """Multi-asset version of `backtest`.

    weights : DataFrame of TARGET weights known at the close of day t (date x ticker).
    close   : DataFrame of closes on the same tickers.
    Weight is shifted by one bar; cost charged on sum |w_t - w_{t-1}| per side.
    Returns (net daily returns, stats). Missing returns (delisted/NaN) earn 0.
    """
    ret = close.pct_change()
    w = weights.reindex(index=ret.index, columns=ret.columns).fillna(0.0)
    w_eff = w.shift(1).fillna(0.0)
    gross = (w_eff * ret.fillna(0.0)).sum(axis=1)
    turn = (w_eff - w_eff.shift(1).fillna(0.0)).abs().sum(axis=1)
    net = gross - turn * (cost_bps / 1e4)
    net.name = name
    stats = perf_stats(net, ann=ann, name=name)
    stats["Turnover_ann"] = turn.sum() / (len(turn) / ann)
    stats["AvgGross"] = w_eff.abs().sum(axis=1).mean()
    stats["AvgNet"] = w_eff.sum(axis=1).mean()
    return net, stats
