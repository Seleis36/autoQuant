"""
BTC US-Close Liquidity Timer (BULT)  -- spot BTC, long/flat, no leverage.

Two economically distinct return sources, fused:

 (1) BASE  - daily liquidity/trend regime.  BTC post-2020 is a long-duration
     liquidity asset; credit risk appetite (HYG), IG credit / financial conditions
     (LQD), the dollar (DXY, inverted) and equity risk appetite (SPX) describe the
     regime it levers.  Combined with BTC's own trend and inverse-vol sizing.
     Slow (about 6 round trips/yr), cost-insensitive.

 (2) OVERLAY - US-close dip absorption.  BTC's entire drift is earned in the
     20:00-23:00 UTC window straddling the US equity close / spot-ETF NAV strike;
     the other 21 hours pay ~zero.  The edge is concentrated on days when BTC sold
     off BEFORE the window: scheduled, price-insensitive US demand absorbs
     overnight supply.  Traded only on those days -> few, high-edge trades.

Alignment / lookahead policy
  * hourly bar T covers [T, T+1h); hret[T] is earned by a position held during bar T
    and a weight known at time T is applied to hret[T] with NO shift.
  * every daily input is lagged one full day + one hour.
  * the overlay gate uses the 00:00->20:00 UTC return, known exactly at 20:00.
"""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"))
from research_lib import DATA_DIR, load_series, vol_target_scalar, ewm_vol, newey_west_t

HANN = 24 * 365.0
WINDOW_HOURS = (20, 21, 22)          # 20:00-23:00 UTC
MACRO = {"HYG": +1, "LQD": +1, "DX-Y.NYB": -1, "^GSPC": +1}
MACRO_LB = (50, 100, 150, 200, 250)
TREND_LB = (20, 50, 100, 150, 200)


def load_hourly(path=None):
    p = path or os.path.join(DATA_DIR, "BTCUSDT_1h.parquet")
    return pd.read_parquet(p)


def build_signals(H, vol_target=0.35, vol_hl=20, gate_thr=-0.010, b=0.5,
                  window=WINDOW_HOURS, macro=MACRO, use_macro=True, use_trend=True):
    """Returns (weight, parts) on the hourly index. weight is knowable at each bar's open."""
    hclose = H["Close"]; hidx = hclose.index
    hret = hclose.pct_change().fillna(0.0)
    hh = pd.DatetimeIndex(hidx).hour
    hday = pd.DatetimeIndex(hidx).normalize()

    dclose = hclose.resample("1D").last(); dret = dclose.pct_change()

    # --- daily regime
    trend = pd.concat([(dclose > dclose.rolling(n).mean()).astype(float)
                       for n in TREND_LB], axis=1).mean(axis=1) if use_trend \
            else pd.Series(1.0, index=dclose.index)
    if use_macro:
        parts = []
        for tkr, sgn in macro.items():
            s = load_series(tkr)["Close"].reindex(dclose.index).ffill()
            m = pd.concat([(s > s.rolling(n).mean()).astype(float) for n in MACRO_LB],
                          axis=1).mean(axis=1)
            parts.append(m if sgn > 0 else 1.0 - m)
        mac = pd.concat(parts, axis=1).mean(axis=1)
    else:
        mac = pd.Series(1.0, index=dclose.index)

    regime = (trend * mac).clip(0, 1)
    volsc = vol_target_scalar(dret, target=vol_target, halflife=vol_hl, cap=1.0)
    base_d = (regime * volsc)
    # lag 1 day, then reindex to hourly and lag 1 more hour
    base_h = base_d.shift(1).reindex(hidx, method="ffill").shift(1).fillna(0.0)

    # --- pre-window cumulative return 00:00 -> 20:00 UTC (known at 20:00)
    win_start = min(window)
    pre_cum = hret.where(hh < win_start, 0.0).groupby(hday).cumsum()
    pre_at = pre_cum[hh == win_start - 1].groupby(hday[hh == win_start - 1]).last()
    pre_h = pd.Series(pre_at.reindex(hday).values, index=hidx)

    in_win = np.isin(hh, list(window))
    gate = pd.Series((in_win & (pre_h.values < gate_thr)).astype(float), index=hidx)

    w = (base_h + b * gate).clip(0, 1)
    return w, {"hret": hret, "base": base_h, "gate": gate, "pre": pre_h,
               "regime": regime, "volsc": volsc, "dclose": dclose}


def backtest_hourly(w, hret, cost_bps=3.0):
    w = pd.Series(w).clip(0, 1).fillna(0.0)
    turn = (w - w.shift(1).fillna(0.0)).abs()
    net = w * hret - turn * cost_bps / 1e4
    return net, turn


def stats(net, turn=None, label="strategy"):
    net = pd.Series(net).dropna()
    eq = (1 + net).cumprod()
    yrs = len(net) / HANN
    dd = (eq / eq.cummax() - 1)
    mdd = dd.min()
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    dnst = net[net < 0].std()
    out = {
        "CAGR%": cagr * 100, "Vol%": net.std() * np.sqrt(HANN) * 100,
        "Sharpe": net.mean() / net.std() * np.sqrt(HANN),
        "Sortino": net.mean() / dnst * np.sqrt(HANN) if dnst > 0 else np.nan,
        "MaxDD%": mdd * 100, "Calmar": cagr / abs(mdd) if mdd < 0 else np.nan,
        "Skew": net.skew(), "t_NW": newey_west_t(net.values, lags=24 * 21),
    }
    if turn is not None:
        out["RT/yr"] = float(turn.reindex(net.index).sum() / 2 / yrs)
    return pd.Series(out, name=label)
