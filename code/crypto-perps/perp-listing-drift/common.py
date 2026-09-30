"""Shared loaders for perp-listing-drift.

Pre-registered before any result was looked at (2026-09-30):
  event      = first funding settlement of a Binance USDT-M PERPETUAL (crypto underlying),
               dated to the UTC day D0 that contains it; cross-checked with exchangeInfo
               onboardDate. Tradeable only if Binance spot <BASE>USDT has a bar on D0.
  entry      = the close of D0 (the perp has been trading for hours and the listing
               was announced before that); weight applied from D0+1 (research_lib shift).
  hedge      = BTC spot, beta 1 (event study) / EWM beta (portfolio variants)
  IS         = events with D0 <= 2022-12-31;  OOS = D0 >= 2023-01-01
  cost       = 10 bp per side base case, 20 / 30 bp sensitivities (new listings are thin)
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "crypto-alts", "shared"))
import research_lib as rl  # noqa: E402
import venues  # noqa: E402

DATA = rl.DATA_DIR
IS_END = "2022-12-31"
OOS_START = "2023-01-01"
STABLE = {"USDC", "BUSD", "TUSD", "FDUSD", "USDP", "DAI", "USD1", "USDE", "EUR", "EURI",
          "PAXG", "XAUT", "BTCDOM", "DEFI", "FOOTBALL", "BLUEBIRD"}


def load_listings():
    s = pd.read_parquet(os.path.join(DATA, "BINANCE_PERP_LISTINGS.parquet"))
    s = s[(s.underlyingType == "COIN") & ~s.spot_base.isin(STABLE) & ~s.baseAsset.isin(STABLE)]
    s = s[s.first_funding.notna()].copy()
    # listing time: earliest of onboard and first funding (a relisted contract keeps the old
    # funding history but gets a new onboardDate)
    s["listed"] = s[["onboard", "first_funding"]].min(axis=1)
    s["D0"] = s["listed"].dt.floor("D")
    s["gap_days"] = (s.first_funding - s.onboard).dt.total_seconds() / 86400
    # one event per spot coin: the first perp (ignores 1000x re-denominations / relistings)
    s = s.sort_values("listed").drop_duplicates("spot_base", keep="first")
    s["spot_age"] = (s.D0 - s.spot_first).dt.days
    return s.reset_index(drop=True)


def spot_close_panel(bases):
    out = {}
    for b in bases:
        p = venues.binance_path(b)
        if os.path.exists(p):
            df = pd.read_parquet(p)
            if len(df):
                out[b] = df["Close"]
    c = pd.DataFrame(out).sort_index()
    c.index = pd.DatetimeIndex(c.index)
    return c


def spot_qvol_panel(bases):
    out = {}
    for b in bases:
        p = venues.binance_path(b)
        if os.path.exists(p):
            df = pd.read_parquet(p)
            if len(df):
                out[b] = df["QuoteVolume"]
    return pd.DataFrame(out).sort_index()


def clean_close(c, max_jump=3.0):
    """Mask bars after a pair stops trading (flat-lined) and absurd single-bar jumps."""
    c = c.copy()
    r = c.pct_change(fill_method=None)
    bad = (r.abs() > max_jump)
    c = c.mask(bad)
    return c


def daily_funding_sym(sym, lag_hours=8):
    """Funding settled and usable by the close of day D (same rule as funding_panel)."""
    p = os.path.join(DATA, f"{sym}_fundingRate.parquet")
    if not os.path.exists(p):
        return None
    f = pd.read_parquet(p)["last_funding_rate"]
    f.index = pd.DatetimeIndex(f.index).tz_localize(None)
    day = (f.index + pd.Timedelta(hours=lag_hours)).ceil("D") - pd.Timedelta(days=1)
    return f.groupby(day).sum()
