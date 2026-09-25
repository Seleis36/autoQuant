"""flush-rebound 02: conditional re-framings of the down-shock rebound.

A. volume spike during the drop (forced flow)          B. ETH-specific drop vs BTC (ratio shock)
C. trend regime (above/below 40d SMA, daily closes)   D. funding crowded before the drop
E. daily horizon (drop measured over 1-3 days at the 00:00 UTC close, hold 1-5 days)
All forward returns are measured from the close of the event bar; events de-clustered by H.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np
import pandas as pd
from ethdata import bars, IS_END, OOS_START, _ROOT

h = bars("ETHUSDT", "1h"); b = bars("BTCUSDT", "1h").reindex(h.index)
c = h["Close"]; cb = b["Close"].ffill()
lr = np.log(c).diff()
sig = lr.ewm(halflife=168, min_periods=168).std()
rat = np.log(c / cb)
sig_r = rat.diff().ewm(halflife=168, min_periods=168).std()
qv_avg = h["qv"].rolling(24 * 30, min_periods=168).mean()
sma40d = c.rolling(24 * 40, min_periods=24 * 40).mean()   # 40-day SMA on hourly closes
fund = pd.read_parquet(os.path.join(_ROOT, "data", "ETHUSDT_fundingRate.parquet"))["last_funding_rate"]
fund = fund.reindex(h.index, method="ffill")                # funding known at its stamp
fund_7d = fund.rolling(24 * 7, min_periods=24).mean()


def declus(ev, H):
    idx, last = [], None
    for t in ev[ev].index:
        if last is None or (t - last) >= pd.Timedelta(hours=H):
            idx.append(t); last = t
    return pd.DatetimeIndex(idx)


def stats(ev, H, label):
    fwd = np.log(c.shift(-H) / c)
    f = fwd.reindex(declus(ev.fillna(False), H)).dropna()
    out = dict(label=label, H=H)
    for part, (a, b_) in {"IS": (None, IS_END), "OOS": (OOS_START, None)}.items():
        fp = f.loc[a:b_]
        out[f"n_{part}"] = len(fp)
        out[f"bp_{part}"] = fp.mean() * 1e4 if len(fp) else np.nan
        out[f"t_{part}"] = fp.mean() / fp.std() * np.sqrt(len(fp)) if len(fp) > 3 else np.nan
    return out


rows = []
for k in [2, 4, 8, 12]:
    z = np.log(c / c.shift(k)) / (sig.shift(k) * np.sqrt(k))
    zr = (rat - rat.shift(k)) / (sig_r.shift(k) * np.sqrt(k))
    vr = h["qv"].rolling(k).sum() / (qv_avg.shift(k) * k)
    for Z in [2.0, 3.0]:
        base = z < -Z
        for H in [12, 24, 48]:
            rows.append(stats(base, H, f"k{k} Z{Z} base"))
            for V in [2.0, 3.0]:
                rows.append(stats(base & (vr > V), H, f"k{k} Z{Z} vol>{V}"))
            rows.append(stats(base & (zr < -2), H, f"k{k} Z{Z} ETHrel<-2"))
            rows.append(stats(base & (zr > -0.5), H, f"k{k} Z{Z} ETHrel>-0.5 (market-wide)"))
            rows.append(stats(base & (c.shift(k) > sma40d.shift(k)), H, f"k{k} Z{Z} uptrend"))
            rows.append(stats(base & (c.shift(k) < sma40d.shift(k)), H, f"k{k} Z{Z} downtrend"))
            rows.append(stats(base & (fund_7d.shift(k) > fund_7d.rolling(24 * 180, min_periods=24 * 30).median().shift(k)),
                              H, f"k{k} Z{Z} fund_hi"))
            rows.append(stats(base & (fund_7d.shift(k) <= fund_7d.rolling(24 * 180, min_periods=24 * 30).median().shift(k)),
                              H, f"k{k} Z{Z} fund_lo"))

# E. daily horizon at 00:00 UTC closes
d = h.resample("1D").agg({"Close": "last"})  # stamped at day open; close known at next 00:00
cd = d["Close"]
lrd = np.log(cd).diff(); sigd = lrd.ewm(halflife=30, min_periods=30).std()
for k in [1, 2, 3]:
    zd = np.log(cd / cd.shift(k)) / (sigd.shift(k) * np.sqrt(k))
    for Z in [1.5, 2.0, 2.5]:
        for Hd in [1, 3, 5]:
            fwd = np.log(cd.shift(-Hd) / cd)
            ev = zd < -Z
            idx, last = [], None
            for t in ev[ev].index:
                if last is None or (t - last) >= pd.Timedelta(days=Hd):
                    idx.append(t); last = t
            f = fwd.reindex(pd.DatetimeIndex(idx)).dropna()
            out = dict(label=f"daily k{k}d Z{Z}", H=Hd * 24)
            for part, (a, b_) in {"IS": (None, IS_END), "OOS": (OOS_START, None)}.items():
                fp = f.loc[a:b_]
                out[f"n_{part}"] = len(fp); out[f"bp_{part}"] = fp.mean() * 1e4
                out[f"t_{part}"] = fp.mean() / fp.std() * np.sqrt(len(fp)) if len(fp) > 3 else np.nan
            rows.append(out)

df = pd.DataFrame(rows).round(2)
pd.set_option("display.width", 250, "display.max_rows", 1000)
print(df.to_string(index=False))
df.to_csv(os.path.join(os.path.dirname(__file__), "02_conditional.csv"), index=False)
df["cond"] = df.label.str.split(" ", n=2).str[2]
print(df.groupby("cond")[["t_IS", "t_OOS"]].mean().round(2))
