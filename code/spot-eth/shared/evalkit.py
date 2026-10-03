"""Evaluation kit for daily spot-eth signals: ICs, partial ICs, baselines, additivity.

Conventions (same as ethdata / research_lib):
    * daily bars come from the 1m Binance store, index = bar OPEN date (UTC, tz-naive);
      bar D covers [D 00:00, D+1 00:00) and its close is known at D+1 00:00;
    * a signal value at index D may use anything observable up to D+1 00:00 UTC;
    * a weight at index D is held over bar D+1 (research_lib.backtest shifts by one bar).

The lesson of the 2026-09-25 session is that ETH-native signals mostly re-express ETH's own
trend, so every idea is judged on what it adds to the live `eth-trend-filter`: partial ICs after
trend/momentum controls, the regression alpha of the sleeve on the trend filter, and the blend.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ethdata as ed  # noqa: E402
from ethdata import rl  # noqa: E402

ANN = 365.0
SPLITS = {"Full": (ed.START, None), "IS": (ed.START, ed.IS_END), "OOS": (ed.OOS_START, None)}


def daily(symbol="ETHUSDT"):
    return ed.bars(symbol, "1d")


def fwd_ret(close, h):
    """Log return from close_D to close_{D+h}, stamped D."""
    lc = np.log(close)
    return lc.shift(-h) - lc


def trend_controls(close):
    """Past-return and trend-state controls for partial ICs."""
    lc = np.log(close)
    c = {f"ret{k}": lc - lc.shift(k) for k in (1, 3, 7, 14, 30, 60)}
    c["sma40"] = (close > close.rolling(40).mean()).astype(float)
    c["rv20"] = lc.diff().rolling(20).std()
    return pd.DataFrame(c)


def _hac_t(y, x, lags):
    """OLS slope t-stat of y on [1, x] with Newey-West errors (x may be 2-D; t of the first column)."""
    X = np.column_stack([np.ones(len(y)), x])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ b
    Xe = X * e[:, None]
    S = Xe.T @ Xe
    for L in range(1, lags + 1):
        G = Xe[L:].T @ Xe[:-L]
        S += (1 - L / (lags + 1)) * (G + G.T)
    XtXi = np.linalg.inv(X.T @ X)
    V = XtXi @ S @ XtXi
    return b[1], b[1] / np.sqrt(V[1, 1])


def ic(sig, close, h=1, start=None, end=None, controls=None):
    """Spearman IC of `sig` with the h-day forward return, plus a HAC t-stat (lags = h - 1 + 5).

    With `controls` (DataFrame), sig and the forward return are both residualised on the controls
    in rank space first (partial rank IC) and the t-stat is the HAC slope t of the signal in a
    regression of the forward return on [signal, controls] (all standardised).
    """
    df = pd.DataFrame({"s": sig, "f": fwd_ret(close, h)})
    if controls is not None:
        df = df.join(controls)
    df = df.loc[start:end].replace([np.inf, -np.inf], np.nan).dropna()
    if len(df) < 60:
        return dict(ic=np.nan, t=np.nan, n=len(df))
    rk = df.rank()
    z = (df - df.mean()) / df.std()
    if controls is None:
        r = np.corrcoef(rk["s"], rk["f"])[0, 1]
        _, t = _hac_t(z["f"].to_numpy(), z[["s"]].to_numpy(), lags=h + 4)
    else:
        cols = [c for c in df.columns if c not in ("s", "f")]
        C = np.column_stack([np.ones(len(rk)), rk[cols].to_numpy()])
        rs = rk["s"].to_numpy() - C @ np.linalg.lstsq(C, rk["s"].to_numpy(), rcond=None)[0]
        rf = rk["f"].to_numpy() - C @ np.linalg.lstsq(C, rk["f"].to_numpy(), rcond=None)[0]
        r = np.corrcoef(rs, rf)[0, 1]
        _, t = _hac_t(z["f"].to_numpy(), z[["s"] + cols].to_numpy(), lags=h + 4)
    return dict(ic=r, t=t, n=len(df))


def ic_table(feats, close, horizons=(1, 3, 7, 30), controls=None, splits=None):
    """feats: dict name -> Series. Returns a wide table of IC (t) per horizon and split."""
    splits = splits or SPLITS
    rows = []
    for name, s in feats.items():
        row = {"feature": name}
        for h in horizons:
            for k, (a, b) in splits.items():
                if k == "Full":
                    continue
                o = ic(s, close, h, a, b, controls)
                row[f"h{h}_{k}"] = o["ic"]
                row[f"h{h}_{k}_t"] = o["t"]
        rows.append(row)
    return pd.DataFrame(rows).set_index("feature")


def vol_scalar(close, target=0.40, hl=20, cap=1.0):
    return rl.vol_target_scalar(close.pct_change(), target=target, halflife=hl, cap=cap, ann=ANN)


def baselines(close):
    """Weights of the reference sleeves every idea is compared against."""
    return {
        "volBH": vol_scalar(close),
        "TF_live": ed.trend_filter_weights_daily(close),          # SMA40 x vol 0.5, the live spec
        "SMA50xvol": (close > close.rolling(50).mean()).astype(float) * vol_scalar(close),
    }


def bt(w, close, cost_bps=10.0, start=None, end=None):
    net, st = rl.backtest(w, close, cost_bps=cost_bps, ann=ANN)
    return net.loc[start:end], st


def stats_row(w, close, cost_bps=10.0, start=None, end=None, splits=None, bench=None):
    """Sharpe by split + headline numbers; with `bench` (net returns of a reference sleeve) also
    the correlation and the HAC t-stat of the regression alpha on it, per split."""
    splits = splits or SPLITS
    w = pd.Series(w).reindex(close.index).fillna(0.0)
    net, _ = rl.backtest(w, close, cost_bps=cost_bps, ann=ANN)
    net = net.loc[start:end]
    we = w.shift(1).fillna(0.0).loc[net.index]
    out = {}
    for k, (a, b) in splits.items():
        seg = net.loc[a:b]
        out[f"Sh_{k}"] = seg.mean() / seg.std() * np.sqrt(ANN) if len(seg) > 30 and seg.std() > 0 else np.nan
    s = rl.perf_stats(net, ann=ANN)
    out.update(CAGR=s["CAGR"], MDD=s["MaxDD"], Vol=s["Vol"],
               Turn=we.diff().abs().sum() / (len(we) / ANN), Expo=we.mean())
    if bench is not None:
        for k, (a, b) in splits.items():
            d = pd.DataFrame({"y": net, "x": bench}).loc[a:b].dropna()
            if len(d) < 60 or d["y"].std() == 0:
                out[f"rho_{k}"] = out[f"a_t_{k}"] = np.nan
                continue
            out[f"rho_{k}"] = d["y"].corr(d["x"])
            X = np.column_stack([np.ones(len(d)), d["x"].to_numpy()])
            b_, *_ = np.linalg.lstsq(X, d["y"].to_numpy(), rcond=None)
            e = d["y"].to_numpy() - X @ b_
            Xe = X * e[:, None]
            S = Xe.T @ Xe
            for L in range(1, 22):
                G = Xe[L:].T @ Xe[:-L]
                S += (1 - L / 22) * (G + G.T)
            XtXi = np.linalg.inv(X.T @ X)
            out[f"a_t_{k}"] = b_[0] / np.sqrt((XtXi @ S @ XtXi)[0, 0])
            out[f"a_ann_{k}"] = b_[0] * ANN
    return out


def table(ws, close, cost_bps=10.0, start=None, end=None, splits=None, bench_w=None):
    """ws: dict name -> weights. bench_w: weights of the reference sleeve for rho / alpha."""
    bench = None
    if bench_w is not None:
        bench = rl.backtest(bench_w, close, cost_bps=cost_bps, ann=ANN)[0].loc[start:end]
    return pd.DataFrame({k: stats_row(w, close, cost_bps, start, end, splits, bench) for k, w in ws.items()}).T


def show(df, pct=("CAGR", "MDD", "Vol", "Expo")):
    d = df.copy()
    for c in d.columns:
        if c in pct:
            d[c] = (d[c] * 100).map(lambda v: f"{v:.1f}%")
        elif c == "Turn":
            d[c] = d[c].map(lambda v: f"{v:.0f}x")
        else:
            d[c] = d[c].map(lambda v: f"{v:.2f}" if pd.notna(v) else "")
    return d.to_string()
