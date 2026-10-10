"""cef-discount-reversion -- deployable strategy: dollar-neutral long/short of bond closed-end
funds on the short-term dislocation of their discount to NAV.

Mechanism. A closed-end fund has no creation/redemption, so its price is set by (mostly
retail) order flow while its NAV is set by the bond market. Flow pushes the price away from
NAV for days at a time; with no arbitrage channel the gap closes only as the flow fades. A
fund whose discount is wider than its own recent average AND wider than its peers' is being
sold for non-fundamental reasons and outperforms over the next one to three weeks; the
reverse for a fund that has run rich.

Signal (all at the close of day s, published NAV included)
    disc      = ln(unadjusted close / NAV)
    dev       = disc - mean(disc over the last `win` sessions)
    rdev      = dev - median(dev) across the fund's group (muni / taxable), liquid funds only
    long      from rdev <= -x_in  until rdev >= -x_out
    short     from rdev >= +x_in  until rdev <= +x_out
Book
    `unit` of capital per name on the smaller side; the larger side is scaled down to the
    same notional (dollar-neutral); each side capped at gross_cap / 2.
Timing
    The NAV struck at close s is published that evening, so the state computed at close s
    is traded at close s+1: row t of the returned frame is the weight held from close t to
    close t+1 and uses prices and NAVs up to close t-`signal_lag` only (signal_lag = 1).
    That one-session skip also keeps the bid-ask bounce of the signal's own closing print
    out of the fill.

Inputs are wide frames (date x ticker): UNADJUSTED closes, NAV per share, share volume, and
a ticker -> "muni" / "taxable" map. Use `load_inputs()` for the research panel.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PANEL = os.path.join(ROOT, "data", "CEF_BOND_panel_d.parquet")
UNIVERSE_CSV = os.path.join(HERE, "cef_universe.csv")

DEFAULTS = dict(
    win=60,            # sessions in the discount's rolling mean
    minp=30,
    x_in=0.025,        # enter at a 2.5 log-point group-relative dislocation
    x_out=0.0,         # leave when it has closed
    unit=0.05,         # capital per name on the smaller side
    gross_cap=1.0,     # 0.5 long / 0.5 short at most
    min_dv=1e6,        # trailing median daily dollar volume
    liq_win=60,
    min_price=3.0,
    min_hist=250,      # sessions listed before a fund is eligible
    group_min=10,      # liquid funds needed in a group for its median to count
    signal_lag=1,      # sessions between the signal's close and the entry close
)
SPLIT_JUMP = 0.4       # one-day discount move that can only be an unadjusted NAV split
MAX_DEV = 0.5          # |discount - its rolling mean| beyond this is a data break
GLITCH = np.log(3.0)   # one-day price move by more than a factor of 3 = bad print
# Yahoo's dividend history for DHY is 10x too large against its prices (implied distribution
# yield ~100 % a year, every year), so its adjusted closes -- which price the book -- are
# wrong. Excluded outright.
EXCLUDE = ("DHY",)


def clean_discount(close: pd.DataFrame, nav: pd.DataFrame, anchor_last: bool = False) -> pd.DataFrame:
    """ln(close / NAV) up to a per-fund constant, with the Yahoo NAV-ticker traps removed.

    * Yahoo split-adjusts the price history but not the NAV ticker, so after a (reverse)
      split every earlier ln(close / NAV) is off by ln(ratio). The series is therefore
      rebuilt from its own daily changes with any one-day move larger than SPLIT_JUMP set
      to zero. Only t and t-1 enter each step, so the result at t does not depend on
      anything after t, and a constant offset cannot reach a deviation-from-own-mean signal.
    * A NAV print that moves more than 15 % in a day is not used on that day.

    `anchor_last=True` shifts each fund so its latest value is the true current discount
    (research only: needed for level sorts, irrelevant for the deployed deviation signal).
    """
    nav = nav.where(nav > 0)
    close = close.where(close > 0)
    nr = nav.pct_change(fill_method=None)
    raw = np.log(close / nav.mask(nr.abs() > 0.15))
    step = raw.ffill().diff()
    step = step.mask(step.abs() > SPLIT_JUMP, 0.0)
    disc = step.cumsum().where(raw.notna())
    if anchor_last:
        last = raw.ffill().iloc[-1] - step.cumsum().ffill().iloc[-1]
        disc = disc.add(last, axis=1)
    return disc


def liquid_mask(close, nav, volume, disc, min_dv=1e6, min_price=3.0, liq_win=60, min_hist=250):
    """Point-in-time tradable set. Every test uses data up to the row's own close only.

    * trailing median dollar volume and trailing median price (a median, so that one bad
      print cannot make a sub-$3 fund eligible for a day -- Yahoo did exactly that to DHY);
    * listed for `min_hist` sessions;
    * a NAV that is a real daily NAV: not frozen for 10 sessions (weekly / monthly strikes)
      and not a copy of the closing price (Yahoo mirrors the price for funds that publish no
      daily NAV: OXLC, OCCI, EARN, FSSL, PDCC);
    * no price print in the last `liq_win` sessions that moved by more than a factor of 3
      in a day (a data break, never a bond-fund return).
    """
    dv = (close * volume).rolling(liq_win, min_periods=liq_win // 2).median()
    px = close.rolling(liq_win, min_periods=liq_win // 2).median()
    age = close.notna().cumsum()
    stale = (nav.diff() == 0).rolling(10).sum() == 10
    mirror = ((nav - close).abs() < 1e-6).rolling(20, min_periods=1).sum() >= 3
    glitch = (np.log(close).diff().abs() > GLITCH).rolling(liq_win, min_periods=1).sum() > 0
    ok = (dv >= min_dv) & (px >= min_price) & (age >= min_hist) & disc.notna()
    ok = ok & ~stale & ~mirror & ~glitch
    ok.loc[:, [c for c in ok.columns if c in EXCLUDE]] = False
    return ok


def relative_deviation(disc, mask, group, win=60, minp=30, group_min=10):
    dev = disc - disc.rolling(win, min_periods=minp).mean()
    dev = dev.where(mask & (dev.abs() < MAX_DEV))
    out = pd.DataFrame(np.nan, index=dev.index, columns=dev.columns)
    for g in pd.unique(group.dropna()):
        cols = group.index[group == g].intersection(dev.columns)
        n = dev[cols].notna().sum(axis=1)
        med = dev[cols].median(axis=1).where(n >= group_min)
        out[cols] = dev[cols].sub(med, axis=0)
    return out


def _states(sig: pd.DataFrame, x_in: float, x_out: float) -> pd.DataFrame:
    a = sig.values
    state = np.zeros(a.shape[1])
    out = np.zeros_like(a)
    for i in range(a.shape[0]):
        x = a[i]
        ok = ~np.isnan(x)
        state[~ok] = 0.0
        state[ok & (state > 0) & (x >= -x_out)] = 0.0
        state[ok & (state < 0) & (x <= x_out)] = 0.0
        state[ok & (x <= -x_in)] = 1.0
        state[ok & (x >= x_in)] = -1.0
        out[i] = state
    return pd.DataFrame(out, index=sig.index, columns=sig.columns)


def target_weights(close: pd.DataFrame, nav: pd.DataFrame, volume: pd.DataFrame,
                   group: pd.Series, **kw) -> pd.DataFrame:
    """Target weights (date x ticker), row t held from close t to close t+1."""
    p = {**DEFAULTS, **kw}
    idx = pd.DatetimeIndex(close.index).sort_values()
    close, nav, volume = close.reindex(idx), nav.reindex(idx), volume.reindex(idx)
    group = group.reindex(close.columns)
    disc = clean_discount(close, nav)
    mask = liquid_mask(close, nav, volume, disc, p["min_dv"], p["min_price"], p["liq_win"], p["min_hist"])
    rdev = relative_deviation(disc, mask, group, p["win"], p["minp"], p["group_min"])
    st = _states(rdev, p["x_in"], p["x_out"])
    long, short = (st > 0).astype(float), (st < 0).astype(float)
    nl, ns = long.sum(axis=1), short.sum(axis=1)
    side = np.minimum(np.minimum(nl, ns) * p["unit"], p["gross_cap"] / 2)
    w = long.div(nl.replace(0, np.nan), axis=0).mul(side, axis=0).fillna(0.0) \
        - short.div(ns.replace(0, np.nan), axis=0).mul(side, axis=0).fillna(0.0)
    return w.shift(p["signal_lag"]).fillna(0.0)


def load_inputs(start="2003-01-01"):
    """(close_unadjusted, nav, volume, group, adj_close) from the research panel."""
    p = pd.read_parquet(PANEL)
    p = p[p["date"] >= start]
    wide = {c: p.pivot(index="date", columns="ticker", values=c).sort_index()
            for c in ["close", "nav", "volume", "adj_close"]}
    group = pd.read_csv(UNIVERSE_CSV).set_index("ticker")["group"].reindex(wide["close"].columns)
    return wide["close"], wide["nav"], wide["volume"], group, wide["adj_close"]


if __name__ == "__main__":
    close, nav, volume, group, adj = load_inputs()
    w = target_weights(close, nav, volume, group)
    last = w.iloc[-1]
    print("weights for the close of", w.index[-1].date())
    print(last[last != 0].sort_values().round(4).to_string())
    print("gross %.2f  net %.3f  names %d" % (last.abs().sum(), last.sum(), (last != 0).sum()))
    print("average gross since 2004: %.2f" % w.loc["2004":].abs().sum(axis=1).mean())
