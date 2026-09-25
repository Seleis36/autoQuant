"""sector-sleeve-blend -- target weights for the deployment agent (self-contained).

Four low-correlated sleeves on the 11 SPDR sector ETFs + SPY, each fixed by the literature or by
the selection-free reference of its own research idea, risk-weighted once a year:

  ON    overnight-sentiment reversal (Aboody et al. 2018): long sectors whose recent overnight
        returns (Open_t / Close_{t-1}) were low, short those where they were high; mean XS rank
        over 21/42/63/126/252-day look-backs, linear weights, 21-day tranches, SPY beta hedge.
  CAL   equity flow calendar: equal-weight sector basket held only on turn-of-month days
        [-3, +3] (Etula et al. 2020), the scheduled FOMC statement day and the day before
        (Lucca-Moench 2015), and the last session before a weekday NYSE holiday (Ariel 1990).
  DIP   Connors RSI(2): per sector, long 1/9 of capital when RSI(2) < 10 and close > SMA200;
        exit when close > SMA5 or after 10 sessions.
  RATE  sector rate beta (126-day 2-factor OLS on SPY and daily 10y-yield change) x sign of the
        10y yield's 21-day change (lagged one day); linear weights, monthly, SPY beta hedge.

Risk weights: in calendar year Y, sleeve i gets k_i = (TARGET_VOL / sqrt(n)) / sigma_i, sigma_i =
std of the sleeve's own net daily returns from its first trade through Dec 31 of Y-1 (sleeves need
3 years of history to enter). Weights are fixed within the year.

Convention: inputs are daily bars through the close of day t; row t of the output is the target
weight held from the close of t (filled at that close), earning day t+1. Every input used for row t
is known at that close; the calendar sleeve looks at day t+1's calendar position, which is known
from the NYSE holiday rules and the published FOMC schedule (`fomc_dates.csv`, refresh yearly).
"""
import os
import numpy as np
import pandas as pd
from pandas.tseries.holiday import (AbstractHolidayCalendar, Holiday, USMartinLutherKingJr,
                                    USPresidentsDay, GoodFriday, USMemorialDay, USLaborDay,
                                    USThanksgivingDay, nearest_workday)

SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]
_HERE = os.path.dirname(os.path.abspath(__file__))
UNSCHEDULED_FOMC = pd.to_datetime(["1998-10-15", "2001-01-03", "2001-04-18", "2001-09-17",
                                   "2008-01-22", "2008-10-08", "2020-03-03", "2020-03-15"])


def _ny_obs(d):
    return d + pd.Timedelta(days=1) if d.weekday() == 6 else d


class NYSEHolidays(AbstractHolidayCalendar):
    rules = [Holiday("NewYear", month=1, day=1, observance=_ny_obs),
             USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
             Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
             Holiday("July4", month=7, day=4, observance=nearest_workday), USLaborDay, USThanksgivingDay,
             Holiday("Christmas", month=12, day=25, observance=nearest_workday)]


def _trading_calendar(index, ahead_days=60):
    """Historical sessions as given, extended forward with NYSE rule-based sessions."""
    index = pd.DatetimeIndex(index)
    fut = pd.bdate_range(index[-1] + pd.Timedelta(days=1), periods=ahead_days)
    hol = NYSEHolidays().holidays(fut[0], fut[-1])
    return index.append(fut[~fut.isin(hol)])


def _beta(r, spy, hl=126):
    cov = r.apply(lambda x: x.ewm(halflife=hl, min_periods=hl).cov(spy))
    return cov.div(spy.ewm(halflife=hl, min_periods=hl).var(), axis=0)


def _lin(sig, mask):
    s = sig.where(mask)
    s = s.sub(s.mean(axis=1), axis=0)
    return s.div(s.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)


# ------------------------------------------------------------------ sleeves

def sleeve_on(c, o, cols, listed, beta, lookbacks=(21, 42, 63, 126, 252), tranche=21):
    on = np.log(o / c.shift(1))[cols]
    ens = 0
    for k in lookbacks:
        s = (-on.rolling(k).sum()).where(listed)
        rk = s.rank(axis=1, pct=True)
        ens = ens + rk.sub(rk.mean(axis=1), axis=0)
    w = _lin(ens / len(lookbacks), listed).rolling(tranche, min_periods=1).mean()
    w["SPY"] = -(w * beta).sum(axis=1)
    return w


def sleeve_cal(c, cols, fomc_path=None):
    idx = c.index
    full = _trading_calendar(idx)
    s = pd.Series(full, index=full)
    per = full.to_period("M")
    from_end = s.groupby(per).cumcount(ascending=False) + 1
    from_start = s.groupby(per).cumcount() + 1
    tdom = pd.Series(np.where(from_start <= 10, from_start, -from_end), index=full)
    f = pd.to_datetime(pd.read_csv(fomc_path or os.path.join(_HERE, "fomc_dates.csv"))["date"])
    f = pd.DatetimeIndex(sorted(set(f[~f.isin(UNSCHEDULED_FOMC)])))
    pos = np.searchsorted(full.values, f.values)
    fday = np.zeros(len(full), bool); fprev = np.zeros(len(full), bool)
    for p in pos:
        if p < len(full):
            fday[p] = True
            if p >= 1:
                fprev[p - 1] = True
    nb = full + pd.offsets.BDay(1)
    nxt = pd.Series(list(full[1:]) + [nb[-1]], index=full)
    pre_hol = pd.Series(nxt.values > nb.values, index=full)
    on = ((tdom.between(-3, 3) & (tdom != 0)) | pd.Series(fday | fprev, index=full) | pre_hol)
    on_next = on.shift(-1).reindex(idx).fillna(False).astype(float)   # row t: is day t+1 in-window?
    m = c[cols].notna().astype(float)
    w = m.div(m.sum(axis=1), axis=0).fillna(0.0).mul(on_next, axis=0)
    w["SPY"] = 0.0
    return w


def sleeve_dip(c, cols, rsi_n=2, rsi_entry=10, sma_trend=200, sma_exit=5, max_hold=10, size=1 / 9):
    px = c[cols]
    d = px.diff()
    up = d.clip(lower=0).ewm(alpha=1 / rsi_n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / rsi_n, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn)
    ent = ((rsi < rsi_entry) & (px > px.rolling(sma_trend).mean())).fillna(False).values
    ext = (px > px.rolling(sma_exit).mean()).fillna(False).values
    pos = np.zeros(ent.shape)
    for j in range(ent.shape[1]):
        held = 0
        for i in range(ent.shape[0]):
            if held:
                if ext[i, j] or held >= max_hold:
                    held = 0
                else:
                    held += 1; pos[i, j] = 1; continue
            if ent[i, j]:
                held = 1; pos[i, j] = 1
    w = pd.DataFrame(pos * size, index=c.index, columns=cols)
    w["SPY"] = 0.0
    return w


def sleeve_rate(c, cols, listed, beta, y10, L=126, k=21):
    r = c.pct_change(); spy = r["SPY"]
    y = y10.reindex(c.index.union(y10.index)).ffill().reindex(c.index)
    dy = y.diff().fillna(0.0)
    out = {}
    vm = spy.rolling(L).var(); vy = dy.rolling(L).var(); cmy = spy.rolling(L).cov(dy)
    for s in cols:
        cm = spy.rolling(L).cov(r[s]); cy = dy.rolling(L).cov(r[s])
        out[s] = (vm * cy - cmy * cm) / (vm * vy - cmy ** 2)
    sig = pd.DataFrame(out).mul(np.sign(y.diff(k).shift(1)), axis=0)
    w = _lin(sig, listed)
    me = c.index.to_series().groupby(c.index.to_period("M")).transform("max") == c.index.to_series()
    w = w.where(me).ffill().fillna(0.0)
    w["SPY"] = -(w * beta).sum(axis=1)
    return w


# ------------------------------------------------------------------ blend

def _net_returns(w, c, cost_bps):
    ret = c[w.columns].pct_change().fillna(0.0)
    we = w.shift(1).fillna(0.0)
    turn = (we - we.shift(1).fillna(0.0)).abs().sum(axis=1)
    return (we * ret).sum(axis=1) - turn * cost_bps / 1e4


def target_weights(close, open_, y10=None, target_vol=0.10, min_history_days=756,
                   cost_bps=2.0, sleeves=("ON", "CAL", "DIP", "RATE"), gross_cap=2.0,
                   return_sleeves=False):
    """close, open_: DataFrames (date x ticker) holding the 11 sector ETFs and SPY (auto-adjusted).
    y10: daily 10-year Treasury yield (FRED DGS10 or yfinance ^TNX -- only its sign of change and
    betas to it are used, so the scale is irrelevant). Loaded from data/FRED_DGS10_d.parquet if None.
    gross_cap: total gross exposure limit (proportional scale-down on the ~1 % of days it binds;
    uncapped max is 2.4 -- see cap_sensitivity.py, Sharpe unchanged). None disables.
    Returns DataFrame of target weights, columns SECTORS + ['SPY'].
    """
    cols = [s for s in SECTORS if s in close.columns]
    c = close[cols + ["SPY"]].copy()
    o = open_[cols + ["SPY"]].copy()
    r = c.pct_change()
    listed = c[cols].notna() & c[cols].shift(252).notna()
    beta = _beta(r[cols], r["SPY"]).fillna(1.0)
    if y10 is None and "RATE" in sleeves:
        p = os.path.join(_HERE, "..", "..", "..", "data", "FRED_DGS10_d.parquet")
        y10 = pd.read_parquet(p)["DGS10"]
        y10.index = pd.to_datetime(y10.index)
    W = {}
    if "ON" in sleeves:
        W["ON"] = sleeve_on(c, o, cols, listed, beta)
    if "CAL" in sleeves:
        W["CAL"] = sleeve_cal(c, cols)
    if "DIP" in sleeves:
        W["DIP"] = sleeve_dip(c, cols)
    if "RATE" in sleeves:
        W["RATE"] = sleeve_rate(c, cols, listed, beta, y10)
    W = {k: v.reindex(columns=cols + ["SPY"]).fillna(0.0) for k, v in W.items()}
    R = {k: _net_returns(v, c, cost_bps) for k, v in W.items()}
    K = pd.DataFrame(0.0, index=c.index, columns=list(W))
    years = sorted(set(c.index.year))
    for Y in years:
        past_end = pd.Timestamp(f"{Y - 1}-12-31")
        act = {}
        for k_, x in R.items():
            traded = W[k_].abs().sum(axis=1) > 0
            if not traded.loc[:past_end].any():
                continue
            first = traded.loc[:past_end].idxmax()
            xs = x.loc[first:past_end]
            if len(xs) > min_history_days:
                act[k_] = xs.std() * np.sqrt(252)
        for k_, v in act.items():
            K.loc[str(Y), k_] = (target_vol / np.sqrt(len(act))) / v
    total = sum(W[k_].mul(K[k_], axis=0) for k_ in W)
    for s in SECTORS:
        if s not in total.columns:
            total[s] = 0.0
    total = total[SECTORS + ["SPY"]]
    if gross_cap is not None:
        g = total.abs().sum(axis=1)
        total = total.mul((gross_cap / g).clip(upper=1.0).fillna(1.0), axis=0)
    if return_sleeves:
        return total, W, K
    return total
