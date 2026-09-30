"""exp01 — do forced-liquidation days (OI collapse + price drop) mean-revert on spot?

Per coin, day D:
  doi  = log OI(coins) at the last stamp before D 23:00  minus the same 24 h earlier
  r1   = spot close(D)/close(D-1) - 1   (yfinance XXX-USD, close = D+1 00:00 UTC)
  z_*  = value / trailing-90d std (past only, excludes D)
Events (pre-declared thresholds):
  LIQ_DOWN   z_doi <= -2 and z_r1 <= -1      forced long liquidation
  PX_DOWN    z_r1 <= -2                      price-only control
  PX_DOWN_noOI  z_r1 <= -2 and z_doi > -1    big drop without a leverage flush
  LIQ_UP     z_doi <= -2 and z_r1 >= +1      short squeeze
  BUILD_UP   z_doi >= +2 and r1 > 0          leverage piling in on a rally
Forward spot return (D, D+h], raw and minus the coin's unconditional mean. Prices: Binance
spot <BASE>USDT daily closes.
Coins: BTC (2020-09+), the other majors 2021-12+ (first run: 10 majors; `--all`: the 64
funding_panel perps). IS through 2023-12, OOS 2024+ (pre-declared).
"""
import os
import sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "crypto-perps", "shared"))
import research_lib as rl  # noqa: E402
import metrics_panel as mp  # noqa: E402

import funding_panel as fp  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "code", "crypto-alts", "shared"))
import universe as uv  # noqa: E402
COINS = dict(fp.PERP_OF) if "--all" in sys.argv else {
    "BTC-USD": "BTCUSDT", "ETH-USD": "ETHUSDT", "SOL-USD": "SOLUSDT", "XRP-USD": "XRPUSDT",
    "BNB-USD": "BNBUSDT", "DOGE-USD": "DOGEUSDT", "ADA-USD": "ADAUSDT",
    "LINK-USD": "LINKUSDT", "AVAX-USD": "AVAXUSDT", "LTC-USD": "LTCUSDT"}
H = (1, 3, 7, 14)
# Binance spot closes (bar D closes at D+1 00:00 UTC, same instant as yfinance). yfinance has
# namesake-ticker prints for OP-USD / TIA-USD (2000x "returns"), so the event study uses the
# venue whose perp OI defines the event.
import venues  # noqa: E402


def _base(sym):
    return sym[4:-4] if sym.startswith("1000") else sym[:-4]


CLOSE = {}
for _tk, _sym in COINS.items():
    _p = venues.binance_path(_base(_sym))
    if os.path.exists(_p):
        _d = pd.read_parquet(_p)
        if len(_d):
            CLOSE[_tk] = _d["Close"]


def coin_frame(tk, sym):
    m = mp.load_metrics(sym)
    if m is None:
        return None
    oi = mp.daily_metrics([sym])["sum_open_interest"][sym]
    if tk not in CLOSE:
        return None
    px = CLOSE[tk].dropna()
    px = px[px > 0]
    df = pd.DataFrame({"oi": oi}).join(px.rename("px"), how="inner")
    df["doi"] = np.log(df.oi).diff()
    df["r1"] = df.px.pct_change()
    for c in ("doi", "r1"):
        df[f"z_{c}"] = df[c] / df[c].rolling(90, min_periods=60).std().shift(1)
    for h in H:
        df[f"f{h}"] = df.px.shift(-h) / df.px - 1
    df["coin"] = tk
    return df.dropna(subset=["z_doi", "z_r1"])


frames = [f for f in (coin_frame(t, s) for t, s in COINS.items()) if f is not None]
P = pd.concat(frames).replace([np.inf, -np.inf], np.nan)
P["period"] = np.where(P.index <= "2023-12-31", "IS", "OOS")
for h in H:
    P[f"x{h}"] = P[f"f{h}"] - P.groupby("coin")[f"f{h}"].transform("mean")

ev = {
    "LIQ_DOWN": (P.z_doi <= -2) & (P.z_r1 <= -1),
    "PX_DOWN": P.z_r1 <= -2,
    "PX_DOWN_noOI": (P.z_r1 <= -2) & (P.z_doi > -1),
    "LIQ_UP": (P.z_doi <= -2) & (P.z_r1 >= 1),
    "BUILD_UP": (P.z_doi >= 2) & (P.r1 > 0),
    "ALL": P.z_r1.notna(),
}
rows = []
for name, m in ev.items():
    for per in ("IS", "OOS", "all"):
        g = P[m] if per == "all" else P[m & (P.period == per)]
        row = {"event": name, "per": per, "n": len(g), "coins": g.coin.nunique()}
        for h in H:
            x = g[f"x{h}"].dropna()
            row[f"x{h}_bp"] = x.mean() * 1e4
            row[f"t{h}"] = x.mean() / x.std() * np.sqrt(len(x)) if len(x) > 2 else np.nan
        rows.append(row)
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).round(1).to_string(index=False))

P.to_parquet("exp01_panel_all.parquet" if "--all" in sys.argv else "exp01_panel.parquet")
# pooled regression of forward returns on z_r1, z_doi and their interaction
import numpy.linalg as la
for per in ("IS", "OOS"):
    g = P[P.period == per].dropna(subset=["x1", "x3", "x7", "z_r1", "z_doi"])
    X = np.column_stack([np.ones(len(g)), g.z_r1.clip(-5, 5), g.z_doi.clip(-5, 5),
                         (g.z_r1 * g.z_doi).clip(-25, 25)])
    for h in (1, 3, 7):
        y = g[f"x{h}"].values
        b = la.lstsq(X, y, rcond=None)[0]
        e = y - X @ b
        # HAC-free, but overlapping horizons inflate t; report the h=1 t as the honest one
        se = np.sqrt(np.diag(la.inv(X.T @ X)) * (e @ e) / (len(y) - 4))
        print(per, f"h{h}", "coef(bp) r1, doi, r1*doi:", np.round(b[1:] * 1e4, 1),
              "t:", np.round(b[1:] / se[1:] / np.sqrt(h), 2))
