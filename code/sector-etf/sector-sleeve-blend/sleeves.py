"""Sleeve weight builders for the blend. Each spec is fixed by literature or was the
selection-free reference of its own idea -- nothing re-optimised here.
  ON   overnight-sentiment-reversal ENS (strategy.target_weights of that idea)
  CAL  EW sector basket long on TOM[-3,+3] (Etula et al.), scheduled-FOMC day & day before
       (Lucca-Moench), last day before a weekday holiday (Ariel)
  DIP  Connors canonical per sector: RSI(2) < 10 and close > SMA200 -> long 1/9, exit close > SMA5
       (max 10 days)
  RATE rate-beta (L126) x sign of 1-month DGS10 change, monthly, SPY-hedged
"""
import os, sys
_H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_H, "..", "shared"))
sys.path.insert(0, os.path.join(_H, "..", "overnight-sentiment-reversal"))
sys.path.insert(0, os.path.join(_H, "..", "equity-flow-calendar"))
import numpy as np, pandas as pd
import data, sxlib as sx, cal
from strategy import target_weights as on_weights

S = data.SECTORS


def w_on(c, o):
    return on_weights(c, o)


def w_cal(c):
    fn = cal.next_day_features(c.index)
    fl = cal.features(c.index.append(pd.DatetimeIndex([c.index[-1] + pd.offsets.BDay(1)])))
    fn.iloc[-1] = fl.iloc[-1]
    td = fn["tdom"]; fo = fn["fomc_off"]; tf = fn["to_fomc"]
    on = ((td.between(-3, 3) & (td != 0)) | (fo == 0) | (tf == -1) | fn["pre_hol"].astype(bool)).astype(float)
    m = c[S].notna().astype(float)
    w = m.div(m.sum(axis=1), axis=0).fillna(0).mul(on, axis=0)
    w["SPY"] = 0.0
    return w


def _rsi(p, n=2):
    d = p.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def w_dip(c):
    px = c[S]
    ent = ((_rsi(px) < 10) & (px > px.rolling(200).mean())).fillna(False).values
    ext = (px > px.rolling(5).mean()).fillna(False).values
    pos = np.zeros(ent.shape)
    for j in range(ent.shape[1]):
        held = 0
        for i in range(ent.shape[0]):
            if held:
                if ext[i, j] or held >= 10:
                    held = 0
                else:
                    held += 1; pos[i, j] = 1; continue
            if ent[i, j]:
                held = 1; pos[i, j] = 1
    w = pd.DataFrame(pos / 9.0, index=c.index, columns=S)
    w["SPY"] = 0.0
    return w


def w_rate(c):
    r = c.pct_change(); spy = r["SPY"]
    dgs = pd.read_parquet(os.path.join(sx.rl.DATA_DIR, "FRED_DGS10_d.parquet"))["DGS10"]
    dgs.index = pd.to_datetime(dgs.index)
    y = dgs.reindex(c.index.union(dgs.index)).ffill().reindex(c.index)
    dy = y.diff().fillna(0)
    L = 126
    out = {}
    for s in S:
        yy = r[s]
        cm = spy.rolling(L).cov(yy); cy = dy.rolling(L).cov(yy)
        vm = spy.rolling(L).var(); vy = dy.rolling(L).var(); cmy = spy.rolling(L).cov(dy)
        out[s] = (vm * cy - cmy * cm) / (vm * vy - cmy ** 2)
    by = pd.DataFrame(out)
    mask = data.universe_mask(c[S])
    sig = by.mul(np.sign(y.diff(21).shift(1)), axis=0).where(mask)
    sig = sig.sub(sig.mean(axis=1), axis=0)
    w = sig.div(sig.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    me = c.index.to_series().groupby(c.index.to_period("M")).transform("max") == c.index.to_series()
    w = w.where(me).ffill().fillna(0)
    beta = sx.beta_to(r[S], spy, 126).fillna(1)
    w["SPY"] = -(w * beta).sum(axis=1)
    return w


def all_sleeves(c, o):
    return {"ON": w_on(c, o), "CAL": w_cal(c), "DIP": w_dip(c), "RATE": w_rate(c)}
