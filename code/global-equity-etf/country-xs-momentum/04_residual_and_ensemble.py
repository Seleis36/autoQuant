"""Beta-hedged residual momentum + signal ensembles."""
import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from research_lib import perf_stats

sys.path.insert(0, HERE)
from importlib import import_module
_bt = import_module("02_backtest")
_v = import_module("03_variants")

load_prices = _bt.load_prices
vol_target_scale = _bt.vol_target_scale
backtest = _bt.backtest
split_ret = _bt.split_ret

ANN = 252


def rolling_beta(y, x, win=63):
    x_ = x - x.rolling(win).mean()
    y_ = y - y.rolling(win).mean()
    cov = (x_ * y_).rolling(win).mean()
    var = (x_ * x_).rolling(win).mean()
    return cov / var


def residual_returns(px, bench="SPY", win=63):
    r = px.pct_change()
    rb = r[bench]
    resid = pd.DataFrame(index=r.index, columns=r.columns, dtype=float)
    for c in r.columns:
        if c == bench:
            resid[c] = 0.0
            continue
        beta = rolling_beta(r[c], rb, win=win)
        resid[c] = r[c] - beta.shift(1) * rb  # use lagged beta (no lookahead)
    return resid


def residual_xs_mom(px, lookback=126, skip=5, top_k=3, bot_k=3,
                    beta_win=63, bench="SPY",
                    exclude=("ACWI", "EFA")):
    tradable = [c for c in px.columns if c not in exclude and c != bench]
    resid = residual_returns(px, bench=bench, win=beta_win)
    cum = (1 + resid[tradable]).rolling(lookback).apply(np.prod, raw=True) - 1
    cum = cum.shift(skip)
    ranks = cum.rank(axis=1, method="first")
    n = ranks.notna().sum(axis=1)
    long_mask = ranks.sub(n - top_k + 1, axis=0) >= 0
    short_mask = ranks.le(bot_k, axis=0) & ranks.notna()
    w = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    w = w.add(long_mask.astype(float).div(long_mask.sum(axis=1).replace(0, np.nan), axis=0).fillna(0),
              fill_value=0)
    w = w.sub(short_mask.astype(float).div(short_mask.sum(axis=1).replace(0, np.nan), axis=0).fillna(0),
              fill_value=0)
    rebal_days = px.resample("W-FRI").last().index
    rebal_mask = px.index.isin(rebal_days)
    w = w.where(pd.Series(rebal_mask, index=px.index), np.nan).ffill().fillna(0.0)
    return w


def residual_ts_mom(px, fast=32, slow=128, beta_win=63, bench="SPY",
                    exclude=("ACWI",)):
    """Baz MACD on residual (beta-hedged) cumulative returns."""
    tradable = [c for c in px.columns if c not in exclude and c != bench]
    resid = residual_returns(px, bench=bench, win=beta_win)[tradable].fillna(0.0)
    eq = (1 + resid).cumprod()
    m = eq.ewm(halflife=fast).mean() - eq.ewm(halflife=slow).mean()
    z = m / eq.rolling(63).std(ddof=1)
    z = z / z.rolling(252).std(ddof=1)
    sig = np.sign(z)
    # long/short but hedge each with SPY: net_w[bench] = -sum(w_i * beta_i)
    w = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    w[tradable] = sig.div(len(tradable))
    # hedge with rolling beta
    r = px.pct_change()
    for c in tradable:
        beta = rolling_beta(r[c], r[bench], win=beta_win).shift(1).fillna(1.0)
        w[bench] = w[bench] - w[c] * beta
    return w.fillna(0.0)


if __name__ == "__main__":
    px = load_prices()
    all_dates = px.index
    split = all_dates[int(len(all_dates) * 0.6)]
    splits = {
        "IS": (all_dates[0], split),
        "OOS": (split, all_dates[-1]),
        "Full": (all_dates[0], all_dates[-1]),
    }

    print("\n=== H) Residual XS momentum 126/5, top3/bot3, weekly, vt=10% ===")
    w = residual_xs_mom(px, lookback=126, skip=5, top_k=3, bot_k=3)
    w_v = vol_target_scale(w, px, target_vol=0.10)
    net, st = backtest(w_v, px, cost_bps=5.0, name="resid_xs_126_5")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== I) Residual XS momentum 63/5, top3/bot3, weekly, vt=10% ===")
    w = residual_xs_mom(px, lookback=63, skip=5, top_k=3, bot_k=3)
    w_v = vol_target_scale(w, px, target_vol=0.10)
    net, st = backtest(w_v, px, cost_bps=5.0, name="resid_xs_63_5")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== J) Residual XS momentum 252/21, top3/bot3, weekly, vt=10% ===")
    w = residual_xs_mom(px, lookback=252, skip=21, top_k=3, bot_k=3)
    w_v = vol_target_scale(w, px, target_vol=0.10)
    net, st = backtest(w_v, px, cost_bps=5.0, name="resid_xs_252_21")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== K) Residual TS-mom basket 32/128, SPY-hedged, vt=10% ===")
    w = residual_ts_mom(px, fast=32, slow=128)
    w_v = vol_target_scale(w, px, target_vol=0.10)
    net, st = backtest(w_v, px, cost_bps=5.0, name="resid_ts_32_128")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== L) 50/50 blend: long-only top3 trend-gated + residual XS 126 ===")
    w1 = _v.long_only_top_k(px, lookback=126, skip=5, top_k=3, trend_gate_ma=200)
    w1_v = vol_target_scale(w1, px, target_vol=0.15)
    w2 = residual_xs_mom(px, lookback=126, skip=5, top_k=3, bot_k=3)
    w2_v = vol_target_scale(w2, px, target_vol=0.10)
    w_blend = 0.5 * w1_v + 0.5 * w2_v
    net, st = backtest(w_blend, px, cost_bps=5.0, name="blend_50_50")
    print(st.round(3))
    print(split_ret(net, splits).round(2))
