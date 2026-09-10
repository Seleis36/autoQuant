"""Final creative attempts: VIX-conditioned rotation + volatility-timed variants."""
import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from research_lib import load_series, perf_stats

sys.path.insert(0, HERE)
from importlib import import_module
_bt = import_module("02_backtest")
_v = import_module("03_variants")
load_prices = _bt.load_prices
vol_target_scale = _bt.vol_target_scale
backtest = _bt.backtest
split_ret = _bt.split_ret
long_only_top_k = _v.long_only_top_k
spy_trend_regime = _v.spy_trend_regime

ANN = 252


def vix_series():
    """Fetch VIX daily close."""
    v = load_series("^VIX")["Close"].rename("VIX")
    return v


def moreira_muir_scale(port_r, halflife=20, target_vol=0.15, cap=3.0, ann=ANN):
    """Scale 1/rv^2 (Moreira-Muir vol-managed)."""
    v = port_r.ewm(halflife=halflife, min_periods=halflife).std() * np.sqrt(ann)
    s = (target_vol / (v ** 2 / target_vol)).clip(upper=cap).fillna(0.0)
    return s


if __name__ == "__main__":
    px = load_prices()
    vix = vix_series().reindex(px.index).ffill()
    all_dates = px.index
    split = all_dates[int(len(all_dates) * 0.6)]
    splits = {
        "IS": (all_dates[0], split),
        "OOS": (split, all_dates[-1]),
        "Full": (all_dates[0], all_dates[-1]),
    }

    # Compute VIX regime
    vix_median = vix.rolling(252, min_periods=63).median()
    low_vol = (vix < vix_median).astype(float)

    print("\n=== M) Long-only top3 126d trend-gated × VIX below rolling median ===")
    w = long_only_top_k(px, lookback=126, skip=5, top_k=3, trend_gate_ma=200)
    w = w.mul(low_vol.reindex(px.index).ffill().fillna(0.0), axis=0)
    w_v = vol_target_scale(w, px, target_vol=0.15)
    net, st = backtest(w_v, px, cost_bps=5.0, name="lo_top3_vixgate")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== N) Same but VIX < 20 hard threshold ===")
    w = long_only_top_k(px, lookback=126, skip=5, top_k=3, trend_gate_ma=200)
    calm = (vix < 20).astype(float).reindex(px.index).ffill().fillna(0.0)
    w = w.mul(calm, axis=0)
    w_v = vol_target_scale(w, px, target_vol=0.15)
    net, st = backtest(w_v, px, cost_bps=5.0, name="lo_top3_vix20")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== O) Combined: long-only top3 trend-gated + Moreira-Muir vol scaling ===")
    w = long_only_top_k(px, lookback=126, skip=5, top_k=3, trend_gate_ma=200)
    # Compute the raw portfolio return to time it
    r = px[w.columns].pct_change().fillna(0.0)
    port_r = (w.shift(1).fillna(0.0) * r).sum(axis=1)
    mm_scale = moreira_muir_scale(port_r, halflife=20, target_vol=0.15, cap=3.0)
    w_v = w.mul(mm_scale, axis=0)
    net, st = backtest(w_v, px, cost_bps=5.0, name="lo_top3_mm")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== P) SPY-only trend + inverse-vol, IS/OOS/Full ===")
    # Just to establish a benchmark of what a decent daily strat looks like
    spy = px["SPY"]
    r = spy.pct_change()
    trend = spy > spy.rolling(200).mean()
    ev = r.ewm(halflife=20, min_periods=20).std() * np.sqrt(ANN)
    inv_vol = (0.15 / ev).clip(upper=1.5).fillna(0.0)
    w = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    w["SPY"] = trend.astype(float) * inv_vol
    net, st = backtest(w, px, cost_bps=5.0, name="spy_trend_iv")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== Q) Long-only, all-13 equal weight when SPY > 200MA (buy-hold vs regime) ===")
    tradable = [c for c in px.columns if c not in ("ACWI", "EFA")]
    w = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    reg = spy_trend_regime(px, ma=200)
    for c in tradable:
        w[c] = 1.0 / len(tradable)
    w = w.mul(reg, axis=0)
    w_v = vol_target_scale(w, px, target_vol=0.15)
    net, st = backtest(w_v, px, cost_bps=5.0, name="eq_regime")
    print(st.round(3))
    print(split_ret(net, splits).round(2))
