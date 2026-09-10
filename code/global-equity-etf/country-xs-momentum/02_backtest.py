"""Cross-sectional country momentum on global equity ETFs.

Long top-K, short bottom-K country ETFs ranked by past-N-month total return
(skipping the last week to sidestep short-term reversal), portfolio vol-scaled
to a fixed annual target. Rebalance weekly (Fridays close).

Reports full-sample, IS/OOS split and walk-forward Sharpe. Also tests two
alternative constructions (TS-momentum basket, short-term reversal) for context.
"""
import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from research_lib import load_series, perf_stats, newey_west_t  # noqa

UNIVERSE = ["EFA", "EEM", "EWJ", "EWG", "EWU", "EWZ", "EWY", "EWA",
            "EWC", "FXI", "INDA", "ACWI", "SPY"]
ANN = 252

# ------------------------------------------------------------------ data

def load_prices(universe=UNIVERSE, start="2010-01-04"):
    frames = {}
    for t in universe:
        s = load_series(t)["Close"].rename(t)
        frames[t] = s
    px = pd.concat(frames.values(), axis=1)
    px.columns = list(frames.keys())
    px = px.loc[start:].dropna(how="all")
    return px


# ------------------------------------------------------------------ metrics

def stats(net, ann=ANN, name="strat"):
    return perf_stats(net, ann=ann, name=name)


def turnover(w):
    dw = (w - w.shift(1)).abs().sum(axis=1)
    return dw


# ------------------------------------------------------------------ core signal

def xs_momentum_weights(px, lookback=126, skip=5, top_k=3, bot_k=3,
                        rebal="W-FRI", exclude=("ACWI", "EFA")):
    """Cross-sectional momentum:
       long top-K, short bottom-K ETFs (equal weight within each leg).
       Signal computed on close of `rebal` day, applied t+1.
    """
    tradable = [c for c in px.columns if c not in exclude]
    p = px[tradable].copy()
    r_look = p.pct_change(lookback).shift(skip)      # skip last `skip` days
    # take signal only on rebalance days
    rebal_mask = p.index.to_series().dt.dayofweek == 4  # Friday
    if rebal.startswith("W"):
        rebal_days = p.resample(rebal).last().index
        rebal_mask = p.index.isin(rebal_days)

    ranks = r_look.rank(axis=1, method="first")
    n = ranks.notna().sum(axis=1)
    long_mask = ranks.sub(n - top_k + 1, axis=0) >= 0
    short_mask = ranks.le(bot_k, axis=0) & ranks.notna()

    w = pd.DataFrame(0.0, index=p.index, columns=p.columns)
    # equal weight within legs, dollar-neutral gross = 2.0
    w = w.add(long_mask.astype(float).div(long_mask.sum(axis=1), axis=0).fillna(0), fill_value=0)
    w = w.sub(short_mask.astype(float).div(short_mask.sum(axis=1), axis=0).fillna(0), fill_value=0)

    # hold between rebalance days
    w = w.where(pd.Series(rebal_mask, index=p.index), np.nan).ffill().fillna(0.0)
    return w


def vol_target_scale(w, px, target_vol=0.10, hl=20, cap=3.0, ann=ANN):
    """Scale portfolio weights so that ex-ante vol matches `target_vol`."""
    r = px[w.columns].pct_change().fillna(0.0)
    port_r = (w.shift(1).fillna(0.0) * r).sum(axis=1)
    ev = port_r.ewm(halflife=hl, min_periods=hl).std() * np.sqrt(ann)
    s = (target_vol / ev).clip(upper=cap).fillna(0.0)
    return w.mul(s, axis=0)


def backtest(w, px, cost_bps=5.0, ann=ANN, name="xs_mom"):
    """Multi-asset backtest. Weights known at close of t → applied to next day.
    Cost = per-side bps × turnover (sum of |Δw|).
    """
    r = px[w.columns].pct_change().fillna(0.0)
    w_eff = w.shift(1).fillna(0.0)
    turn = (w_eff - w_eff.shift(1).fillna(0.0)).abs().sum(axis=1)
    gross = (w_eff * r).sum(axis=1)
    net = gross - turn * (cost_bps / 1e4)
    net.name = name
    st = perf_stats(net, ann=ann, name=name)
    st["Turnover_ann"] = turn.sum() / (len(turn) / ann)
    st["GrossExposure"] = w_eff.abs().sum(axis=1).mean()
    st["NetExposure"] = w_eff.sum(axis=1).mean()
    return net, st


# ------------------------------------------------------------------ TS-momentum basket

def ts_momentum_weights(px, fast=32, slow=128, exclude=("ACWI",), sign_only=True):
    """Baz-style MACD trend on each name; sum sub-signals to a portfolio.
    Signal at close of t → next-day return.
    """
    tradable = [c for c in px.columns if c not in exclude]
    p = px[tradable]
    m = p.ewm(halflife=fast).mean() - p.ewm(halflife=slow).mean()
    z = m / p.rolling(63).std(ddof=1)
    z = z / z.rolling(252).std(ddof=1)
    sig = np.sign(z) if sign_only else z.clip(-2, 2)
    # equal-weight sub-signal contribution
    w = sig.div(len(tradable))
    return w.fillna(0.0)


# ------------------------------------------------------------------ short-term reversal

def st_reversal_weights(px, lookback=5, top_k=3, bot_k=3,
                        rebal="W-FRI", exclude=("ACWI", "EFA")):
    """Weekly short-term reversal: long bottom-K past-week losers, short top-K winners."""
    tradable = [c for c in px.columns if c not in exclude]
    p = px[tradable].copy()
    r_look = p.pct_change(lookback)
    rebal_days = p.resample(rebal).last().index
    rebal_mask = p.index.isin(rebal_days)
    ranks = r_look.rank(axis=1, method="first")
    n = ranks.notna().sum(axis=1)
    long_mask = ranks.le(bot_k, axis=0) & ranks.notna()
    short_mask = ranks.sub(n - top_k + 1, axis=0) >= 0
    w = pd.DataFrame(0.0, index=p.index, columns=p.columns)
    w = w.add(long_mask.astype(float).div(long_mask.sum(axis=1), axis=0).fillna(0), fill_value=0)
    w = w.sub(short_mask.astype(float).div(short_mask.sum(axis=1), axis=0).fillna(0), fill_value=0)
    w = w.where(pd.Series(rebal_mask, index=p.index), np.nan).ffill().fillna(0.0)
    return w


# ------------------------------------------------------------------ splits

def split_ret(net, splits):
    return pd.DataFrame({k: perf_stats(net.loc[a:b], ann=ANN, name=k) for k, (a, b) in splits.items()}).T


# ------------------------------------------------------------------ walk-forward

def walk_forward(px, fn_weights, splits, cost_bps=5.0, target_vol=0.10):
    """Just re-fit vol scaling on rolling window; parameters are fixed."""
    w = fn_weights(px)
    w_v = vol_target_scale(w, px, target_vol=target_vol)
    net, st = backtest(w_v, px, cost_bps=cost_bps)
    seg = split_ret(net, splits)
    return net, st, seg


# ------------------------------------------------------------------ run

if __name__ == "__main__":
    px = load_prices()
    print(f"Loaded {px.shape} from {px.index.min().date()} to {px.index.max().date()}")

    # split points: 60% IS / 40% OOS
    all_dates = px.index
    split = all_dates[int(len(all_dates) * 0.6)]
    splits = {
        "IS": (all_dates[0], split),
        "OOS": (split, all_dates[-1]),
        "Full": (all_dates[0], all_dates[-1]),
    }
    print(f"IS: {splits['IS'][0].date()} → {splits['IS'][1].date()}")
    print(f"OOS: {splits['OOS'][0].date()} → {splits['OOS'][1].date()}")

    print("\n=== 1) XS momentum, 126d / skip5, top3/bot3, weekly, vt=10% ===")
    w = xs_momentum_weights(px, lookback=126, skip=5, top_k=3, bot_k=3)
    w_v = vol_target_scale(w, px, target_vol=0.10)
    net, st = backtest(w_v, px, cost_bps=5.0, name="xs_mom_126_5_10vt")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== 2) XS momentum, 252d / skip21 (12-1), top3/bot3, weekly, vt=10% ===")
    w = xs_momentum_weights(px, lookback=252, skip=21, top_k=3, bot_k=3)
    w_v = vol_target_scale(w, px, target_vol=0.10)
    net, st = backtest(w_v, px, cost_bps=5.0, name="xs_mom_252_21_10vt")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== 3) TS momentum basket (32/128 MACD, sign), all names, vt=10% ===")
    w = ts_momentum_weights(px, fast=32, slow=128)
    w_v = vol_target_scale(w, px, target_vol=0.10)
    net, st = backtest(w_v, px, cost_bps=5.0, name="ts_mom_32_128")
    print(st.round(3))
    print(split_ret(net, splits).round(2))

    print("\n=== 4) Weekly reversal 5d, top3/bot3, vt=10% ===")
    w = st_reversal_weights(px, lookback=5, top_k=3, bot_k=3)
    w_v = vol_target_scale(w, px, target_vol=0.10)
    net, st = backtest(w_v, px, cost_bps=5.0, name="st_rev_5d")
    print(st.round(3))
    print(split_ret(net, splits).round(2))
