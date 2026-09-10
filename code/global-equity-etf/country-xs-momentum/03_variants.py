"""Variants to try after baseline XS momentum failed."""
import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from research_lib import load_series, perf_stats

sys.path.insert(0, HERE)
from importlib import import_module
_bt = import_module("02_backtest")
load_prices = _bt.load_prices
vol_target_scale = _bt.vol_target_scale
backtest = _bt.backtest
split_ret = _bt.split_ret

ANN = 252


def long_only_top_k(px, lookback=63, skip=5, top_k=3, rebal="W-FRI",
                    exclude=("ACWI", "EFA"), trend_gate_ma=200):
    """Long top-K by past momentum, but only those above own trend_gate_ma."""
    tradable = [c for c in px.columns if c not in exclude]
    p = px[tradable]
    r_look = p.pct_change(lookback).shift(skip)
    trend_ok = p > p.rolling(trend_gate_ma).mean()
    r_look = r_look.where(trend_ok)
    ranks = r_look.rank(axis=1, method="first")
    n = ranks.notna().sum(axis=1)
    long_mask = ranks.sub(n - top_k + 1, axis=0) >= 0
    w = pd.DataFrame(0.0, index=p.index, columns=p.columns)
    w = w.add(long_mask.astype(float).div(long_mask.sum(axis=1).replace(0, np.nan), axis=0).fillna(0),
              fill_value=0)
    rebal_days = p.resample(rebal).last().index
    rebal_mask = p.index.isin(rebal_days)
    w = w.where(pd.Series(rebal_mask, index=p.index), np.nan).ffill().fillna(0.0)
    return w


def rel_strength_xs(px, lookback=126, skip=5, top_k=3, bot_k=3,
                    bench="SPY", rebal="W-FRI",
                    exclude=("ACWI", "EFA")):
    """Rank countries by (ETF/SPY) log-return over lookback."""
    tradable = [c for c in px.columns if c not in exclude and c != bench]
    p = px[tradable]
    b = px[bench]
    ratio = p.div(b, axis=0)
    r_look = ratio.pct_change(lookback).shift(skip)
    ranks = r_look.rank(axis=1, method="first")
    n = ranks.notna().sum(axis=1)
    long_mask = ranks.sub(n - top_k + 1, axis=0) >= 0
    short_mask = ranks.le(bot_k, axis=0) & ranks.notna()
    w = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    w[p.columns] = 0.0
    w = w.add(long_mask.astype(float).div(long_mask.sum(axis=1).replace(0, np.nan), axis=0).fillna(0),
              fill_value=0)
    w = w.sub(short_mask.astype(float).div(short_mask.sum(axis=1).replace(0, np.nan), axis=0).fillna(0),
              fill_value=0)
    rebal_days = p.resample(rebal).last().index
    rebal_mask = p.index.isin(rebal_days)
    w = w.where(pd.Series(rebal_mask, index=px.index), np.nan).ffill().fillna(0.0)
    return w


def low_vol_tilt(px, vol_win=63, top_k=3, bot_k=3, rebal="W-FRI",
                 exclude=("ACWI", "EFA")):
    """BAB-style: long low-vol countries, short high-vol."""
    tradable = [c for c in px.columns if c not in exclude]
    p = px[tradable]
    r = p.pct_change()
    vol = r.rolling(vol_win).std(ddof=1) * np.sqrt(ANN)
    ranks = vol.rank(axis=1, method="first", ascending=True)  # 1 = lowest vol
    n = ranks.notna().sum(axis=1)
    long_mask = ranks.le(top_k, axis=0) & ranks.notna()
    short_mask = ranks.sub(n - bot_k + 1, axis=0) >= 0
    w = pd.DataFrame(0.0, index=p.index, columns=p.columns)
    w = w.add(long_mask.astype(float).div(long_mask.sum(axis=1).replace(0, np.nan), axis=0).fillna(0),
              fill_value=0)
    w = w.sub(short_mask.astype(float).div(short_mask.sum(axis=1).replace(0, np.nan), axis=0).fillna(0),
              fill_value=0)
    rebal_days = p.resample(rebal).last().index
    rebal_mask = p.index.isin(rebal_days)
    w = w.where(pd.Series(rebal_mask, index=p.index), np.nan).ffill().fillna(0.0)
    return w


def spy_trend_regime(px, ma=200):
    return (px["SPY"] > px["SPY"].rolling(ma).mean()).astype(float)


if __name__ == "__main__":
    px = load_prices()
    all_dates = px.index
    split = all_dates[int(len(all_dates) * 0.6)]
    splits = {
        "IS": (all_dates[0], split),
        "OOS": (split, all_dates[-1]),
        "Full": (all_dates[0], all_dates[-1]),
    }

    print("\n=== A) Long-only top3, 63d mom, trend-gated (200MA) ===")
    w = long_only_top_k(px, lookback=63, skip=5, top_k=3, trend_gate_ma=200)
    w_v = vol_target_scale(w, px, target_vol=0.15)
    net, st = backtest(w_v, px, cost_bps=5.0, name="lo_top3_63d_trendgate")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== B) Long-only top3, 126d mom, trend-gated ===")
    w = long_only_top_k(px, lookback=126, skip=5, top_k=3, trend_gate_ma=200)
    w_v = vol_target_scale(w, px, target_vol=0.15)
    net, st = backtest(w_v, px, cost_bps=5.0, name="lo_top3_126d_trendgate")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== C) Rel-strength XS 126/5 top3/bot3 (vs SPY) ===")
    w = rel_strength_xs(px, lookback=126, skip=5, top_k=3, bot_k=3)
    w_v = vol_target_scale(w, px, target_vol=0.10)
    net, st = backtest(w_v, px, cost_bps=5.0, name="rs_xs_126_5")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== D) Rel-strength XS 63/5 top3/bot3 ===")
    w = rel_strength_xs(px, lookback=63, skip=5, top_k=3, bot_k=3)
    w_v = vol_target_scale(w, px, target_vol=0.10)
    net, st = backtest(w_v, px, cost_bps=5.0, name="rs_xs_63_5")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== E) Low-vol BAB top3/bot3 ===")
    w = low_vol_tilt(px, vol_win=63, top_k=3, bot_k=3)
    w_v = vol_target_scale(w, px, target_vol=0.10)
    net, st = backtest(w_v, px, cost_bps=5.0, name="lowvol_63d")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== F) Long-only top3, 63d mom, SPY-regime gate (no own-trend filter) ===")
    w = long_only_top_k(px, lookback=63, skip=5, top_k=3, trend_gate_ma=1)  # no gate
    reg = spy_trend_regime(px, ma=200)
    w = w.mul(reg, axis=0)
    w_v = vol_target_scale(w, px, target_vol=0.15)
    net, st = backtest(w_v, px, cost_bps=5.0, name="lo_top3_spygate")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== G) SPY buy-and-hold benchmark ===")
    r = px["SPY"].pct_change().fillna(0.0)
    st = perf_stats(r, ann=ANN, name="SPY_BH")
    print(st.round(3))
    print(pd.DataFrame({k: perf_stats(r.loc[a:b], ann=ANN, name=k) for k, (a, b) in splits.items()}).T.round(2))
