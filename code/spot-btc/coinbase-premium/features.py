"""Daily feature panel for coinbase-premium.

Convention: the daily row stamped D holds everything observable at 00:00 UTC of D+1
(i.e. at the close of calendar day D). `ret_fwd` is the return from that instant to
00:00 UTC of D+2 -- the return a weight decided at row D actually earns.

All hourly caches index bars by OPEN time. The bar opened 23:00 on D closes at 00:00 D+1,
so `close_D` = Close of the 23:00 bar of day D.
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"))
from research_lib import DATA_DIR  # noqa: E402

ANN = 365.0


def _p(name):
    return os.path.join(DATA_DIR, f"{name}.parquet")


def _naive(df):
    if df.index.tz is not None:
        df = df.tz_convert("UTC").tz_localize(None)
    return df.sort_index()


def load_hourly_flow():
    df = pd.read_parquet(_p("BTCUSDT_1h_flow"))
    return _naive(df)


def daily_from_hourly(h):
    """Aggregate hourly bars into calendar-day rows (UTC)."""
    day = h.index.floor("D")
    g = h.groupby(day)
    d = pd.DataFrame({
        "open": g["Open"].first(),
        "high": g["High"].max(),
        "low": g["Low"].min(),
        "close": g["Close"].last(),
        "vol": g["Volume"].sum(),
        "qv": g["qv"].sum(),
        "n": g["n"].sum(),
        "tb": g["tb"].sum(),
        "tq": g["tq"].sum(),
        "nbars": g["Close"].count(),
    })
    return d


def build_panel():
    h = load_hourly_flow()
    d = daily_from_hourly(h)
    d = d[d["nbars"] >= 20]          # drop partial days (exchange outages / first day)
    px = d["close"]
    ret = px.pct_change()
    out = pd.DataFrame(index=d.index)
    out["close"] = px
    out["ret"] = ret
    out["ret_fwd"] = ret.shift(-1)

    # ---- price-derived controls
    out["rv20"] = ret.rolling(20).std() * np.sqrt(ANN)
    out["ewv20"] = ret.ewm(halflife=20, min_periods=20).std() * np.sqrt(ANN)
    for n in (20, 50, 100, 200):
        out[f"sma{n}_up"] = (px > px.rolling(n).mean()).astype(float)
    for n in (5, 10, 20, 60):
        out[f"mom{n}"] = px.pct_change(n)
    out["dd_20"] = px / px.rolling(20).max() - 1
    out["range_d"] = (d["high"] - d["low"]) / d["close"]

    # ---- taker order-flow imbalance (spot, Binance)
    tbr = d["tb"] / d["vol"]                      # taker-buy share of base volume, [0,1]
    out["tbr1"] = tbr
    for n in (3, 7, 14, 30):
        out[f"tbr{n}"] = (d["tb"].rolling(n).sum() / d["vol"].rolling(n).sum())
    # z-scored vs trailing 90d
    out["tbr1_z"] = (tbr - tbr.rolling(90).mean()) / tbr.rolling(90).std()
    out["tbr7_z"] = (out["tbr7"] - out["tbr7"].rolling(90).mean()) / out["tbr7"].rolling(90).std()
    # net taker flow in quote currency, normalised by 30d quote volume
    net_q = 2 * d["tq"] - d["qv"]
    out["netflow1"] = net_q / d["qv"].rolling(30).mean()
    out["netflow7"] = net_q.rolling(7).sum() / d["qv"].rolling(30).mean()
    # volume / trade-count anomalies
    out["vol_ratio7"] = d["qv"] / d["qv"].rolling(30).mean()
    out["ntr_ratio"] = d["n"] / d["n"].rolling(30).mean()
    out["avg_trade"] = (d["qv"] / d["n"]) / (d["qv"].rolling(30).sum() / d["n"].rolling(30).sum())

    # last-hours flow: taker share in the final 4 hours of the day (16-24h... use 20:00-23:00)
    hh = h.copy(); hh["day"] = hh.index.floor("D"); hh["hr"] = hh.index.hour
    late = hh[hh["hr"] >= 20].groupby("day")
    out["tbr_late"] = (late["tb"].sum() / late["Volume"].sum()).reindex(out.index)
    us = hh[(hh["hr"] >= 13) & (hh["hr"] < 21)].groupby("day")
    out["tbr_us"] = (us["tb"].sum() / us["Volume"].sum()).reindex(out.index)
    asia = hh[hh["hr"] < 8].groupby("day")
    out["tbr_asia"] = (asia["tb"].sum() / asia["Volume"].sum()).reindex(out.index)

    # ---- perp funding (8h settlements; known at settlement time)
    f = _naive(pd.read_parquet(_p("BTCUSDT_funding_8h")))
    f.index = f.index.round("h")
    fr = f["fundingRate"]
    # settlement at 00:00 of D+1 belongs to day D (it is known exactly at the row's stamp)
    fday = fr.groupby((fr.index - pd.Timedelta(hours=1)).floor("D")).sum()
    out["fund1"] = fday.reindex(out.index)
    for n in (3, 7, 14, 30):
        out[f"fund{n}"] = out["fund1"].rolling(n).mean()
    out["fund_z90"] = (out["fund7"] - out["fund7"].rolling(90).mean()) / out["fund7"].rolling(90).std()
    out["fund_ann"] = out["fund7"] * 3 * ANN  # annualised, on the daily-sum basis / 3 settlements
    out["fund_last"] = fr.reindex(out.index + pd.Timedelta(days=1)).values  # the 00:00 D+1 settlement

    # ---- premium index (mark vs index), hourly
    pm = _naive(pd.read_parquet(_p("BTCUSDT_premium_1h")))
    pmd = pm.groupby(pm.index.floor("D"))
    out["prem_mean"] = pmd["Close"].mean().reindex(out.index)
    out["prem_last"] = pmd["Close"].last().reindex(out.index)
    out["prem_min"] = pmd["Low"].min().reindex(out.index)
    for n in (3, 7, 14):
        out[f"prem{n}"] = out["prem_mean"].rolling(n).mean()
    out["prem_z90"] = (out["prem_mean"] - out["prem_mean"].rolling(90).mean()) / out["prem_mean"].rolling(90).std()

    # ---- Coinbase premium vs Binance (USDT) and vs Bitstamp (USD)
    cb = _naive(pd.read_parquet(_p("COINBASE_BTCUSD_1h")))
    cbd = cb.groupby(cb.index.floor("D"))["Close"].last()
    out["cb_close"] = cbd.reindex(out.index)
    out["cbprem_bin"] = out["cb_close"] / px - 1
    cbmean = (cb["Close"].reindex(h.index) / h["Close"] - 1).groupby(h.index.floor("D")).mean()
    out["cbprem_bin_mean"] = cbmean.reindex(out.index)
    try:
        bs = _naive(pd.read_parquet(_p("BITSTAMP_1h")))
        bsd = bs.groupby(bs.index.floor("D"))["Close"].last()
        out["cbprem_bs"] = (cbd / bsd - 1).reindex(out.index)
        bsmean = (cb["Close"].reindex(bs.index) / bs["Close"] - 1).groupby(bs.index.floor("D")).mean()
        out["cbprem_bs_mean"] = bsmean.reindex(out.index)
    except Exception:
        pass
    for c in ("cbprem_bin", "cbprem_bin_mean", "cbprem_bs_mean"):
        if c in out:
            out[f"{c}_z90"] = (out[c] - out[c].rolling(90).mean()) / out[c].rolling(90).std()
            out[f"{c}_7"] = out[c].rolling(7).mean()

    # ---- USDT/USD (stablecoin premium)
    try:
        u = _naive(pd.read_parquet(_p("BITSTAMP_USDTUSD_1d")))["Close"]
        out["usdt_prem"] = u.reindex(out.index) - 1
        out["usdt_prem7"] = out["usdt_prem"].rolling(7).mean()
        out["usdt_prem_z90"] = (out["usdt_prem"] - out["usdt_prem"].rolling(90).mean()) / out["usdt_prem"].rolling(90).std()
    except Exception:
        pass

    # ---- Deribit DVOL (implied vol) vs realised
    try:
        dv = _naive(pd.read_parquet(_p("DERIBIT_DVOL_BTC_1d")))["Close"]
        out["dvol"] = dv.reindex(out.index) / 100.0
        out["vrp"] = out["dvol"] - out["rv20"]
        out["dvol_chg5"] = out["dvol"].pct_change(5)
        out["dvol_z90"] = (out["dvol"] - out["dvol"].rolling(90).mean()) / out["dvol"].rolling(90).std()
    except Exception:
        pass

    return out


if __name__ == "__main__":
    p = build_panel()
    print(p.shape, p.index[0], p.index[-1])
    print(p.notna().sum().to_string())
