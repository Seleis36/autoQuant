"""Shared data for perp-spot-volume-share.

Pre-registered before any result was looked at (2026-09-30):
  feature   share = log(perp quote volume / spot quote volume), both Binance, daily bar D
            (bar D closes at D+1 00:00 UTC = the yfinance close at which the weight is set,
            so the full day's volume is known at decision time).
  universe  PIT top-20 by trailing-90d median USD volume among `funding_panel.PERP_OF` coins
            with >= 60 days of both perp and Binance-spot volume (funding-xs-crowding rules)
  P&L       spot yfinance closes, research_lib.backtest_xs, beta-neutral to BTC
  IS        2020-09-01 .. 2022-12-31,  OOS 2023-01-01 .. end
  cost      10 bp per side
"""
import os
import sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "crypto-perps", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "crypto-alts", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "crypto-perps", "retail-crowding-xs"))
import research_lib as rl  # noqa: E402
import funding_panel as fp  # noqa: E402
import universe as uv  # noqa: E402
import venues  # noqa: E402

IS = ("2020-09-01", "2022-12-31")
OOS = ("2023-01-01", "2026-12-31")
FULL = ("2020-09-01", "2026-12-31")
SPLITS = {"full": FULL, "IS": IS, "OOS": OOS}
COST = 10.0
TICKERS = list(fp.PERP_OF)
CACHE = os.path.join(_HERE, "_panel_cache.pkl")


def _spot_base(sym):
    for p in ("1000",):
        if sym.startswith(p):
            sym = sym[len(p):]
    return sym[:-4]


def load(n_top=20, min_days=60, refresh=False):
    if os.path.exists(CACHE) and not refresh:
        return pd.read_pickle(CACHE)
    panel = uv.load_panel(TICKERS)
    close = uv.clean_close(panel["Close"])
    vol = panel["Volume"].reindex_like(close)
    pq, sq = {}, {}
    for t in close.columns:
        sym = fp.PERP_OF.get(t)
        if sym is None:
            continue
        pp = os.path.join(rl.DATA_DIR, f"BINANCE_{sym}_PERP_1d.parquet")
        sp = venues.binance_path(_spot_base(sym))
        if os.path.exists(pp):
            pq[t] = pd.read_parquet(pp)["QuoteVolume"]
        if os.path.exists(sp):
            d = pd.read_parquet(sp)
            if len(d):
                sq[t] = d["QuoteVolume"]
    pq = pd.DataFrame(pq).reindex(index=close.index, columns=close.columns)
    sq = pd.DataFrame(sq).reindex(index=close.index, columns=close.columns)
    pq, sq = pq.where(pq > 0), sq.where(sq > 0)
    share = np.log(pq / sq)
    ok = share.notna().cumsum() >= min_days
    med = vol.rolling(90, min_periods=45).median()
    hist = close.notna().cumsum()
    elig = (hist >= 120) & (med >= 1e6) & close.notna() & ok & share.notna()
    mask = (med.where(elig).rank(axis=1, ascending=False) <= n_top) & elig
    start = "2020-06-01"
    out = (close.loc[start:], vol.loc[start:], pq.loc[start:], sq.loc[start:], share.loc[start:],
           mask.loc[start:])
    pd.to_pickle(out, CACHE)
    return out
