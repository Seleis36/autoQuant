"""Relative (vs SPY) time-series trend on country ETF spreads."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
import numpy as np, pandas as pd
import data as D, xs

COUNTRIES = ["EWJ", "EWG", "EWU", "EWZ", "EWY", "EWA", "EWC", "FXI", "INDA"]
LB = (21, 63, 126, 252)
SPL = {"FULL": ("2001", "2026"), "IS": ("2001", "2012"), "OOS": ("2013", "2026")}


def load(extra=()):
    C = D.load_panel(COUNTRIES + ["EEM", "EFA", "ACWI", "SPY"] + list(extra), "Close", start="1998-12-01")
    return C, C.pct_change()


def roll_beta(ret, names, win=252, bench="SPY"):
    x = ret[bench]
    v = x.rolling(win, min_periods=126).var()
    return pd.DataFrame({t: ret[t].rolling(win, min_periods=126).cov(x) / v for t in names})


def spread_returns(ret, names, beta_win=252, hedge="beta"):
    """Daily return of (ETF_i - b_i SPY) with b known at t-1; hedge='dollar' uses b = 1."""
    b = roll_beta(ret, names, beta_win).shift(1) if hedge == "beta" else pd.DataFrame(1.0, index=ret.index, columns=names)
    return ret[names] - b.mul(ret["SPY"], axis=0), b


def trend_signal(spread_ret, lbs=LB, kind="sign"):
    px = np.log((1 + spread_ret.fillna(0.0)).cumprod())
    px = px.where(spread_ret.notna())
    parts = []
    for l in lbs:
        m = px - px.shift(l)
        if kind == "sign":
            parts.append(np.sign(m))
        else:  # vol-normalised, clipped
            sd = spread_ret.rolling(252, min_periods=126).std() * np.sqrt(l)
            parts.append((m / sd).clip(-2, 2) / 2)
    s = sum(parts) / len(parts)
    return s


def build_weights(sig, spread_ret, beta, names, reb, target=0.10, per_leg_vol=126, hedge_beta=None):
    """Per-spread position = sig * (1/vol_spread), equal risk; ETF weights + netted SPY hedge;
    whole book scaled to `target` ex-ante vol on the trailing covariance of ETF+SPY returns."""
    vol = spread_ret.rolling(per_leg_vol, min_periods=60).std() * np.sqrt(252)
    pos = (sig / vol).loc[reb, names]
    pos = pos.where(np.isfinite(pos), 0.0).fillna(0.0)
    hb = (hedge_beta if hedge_beta is not None else beta.shift(-1)).loc[reb, names].fillna(1.0)  # beta known at t
    w = pos.copy()
    w["SPY"] = -(pos * hb).sum(axis=1)
    return w


def book(C, ret, w_reb, target=0.10, cost=5.0, spy_cost=1.0, start="2001-01-01", name="book"):
    w = xs.vol_target_book(w_reb, ret[w_reb.columns], target=target)
    net, gross, turn, We = xs.run(w, C.loc[start:, w_reb.columns], cost_bps=cost, spy_cost_bps=spy_cost, name=name)
    return net, gross, turn, We


def row(net, turn, We, name, gross=None):
    r = xs.summarize(net, SPL, turn, We, name=name)
    if gross is not None:
        r["FULL_SR_gross"] = xs.summarize(gross, SPL)["FULL_SR"]
    return r
