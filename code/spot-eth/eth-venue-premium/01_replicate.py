"""eth-venue-premium 01: pre-registered replication of spot-btc/coinbase-premium on ETH.

PRIMARY (fixed before any ETH result was seen): the BTC spec unchanged --
  prem = Coinbase ETH-USD close / Binance ETHUSDT close - 1 (hourly, bar-open stamps)
  z = (prem - mean_720) / std_720 ; hysteresis enter z>0, exit z<-1.5
  w = state x 1{C > SMA(1200h)} x min(0.40 / EWMvol(hl 480h, ann 8760), 1)
Splits: IS <= 2023-12-31 / OOS >= 2024 (this asset class) and the BTC study's <= 2022 / >= 2023.
10 bp per side, hourly backtest, Sharpe on UTC-daily compounded returns.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import pandas as pd
from ethdata import rl, bars, bt, row, to_daily, trend_filter_weights_daily
from fetch_coinbase import load as cb_load

H = 24 * 365
bn = bars("ETHUSDT", "1h")["Close"]
cb = cb_load("ETH-USD")["Close"].reindex(bn.index)
bnb = bars("BTCUSDT", "1h")["Close"].reindex(bn.index)
cbb = cb_load("BTC-USD")["Close"].reindex(bn.index)

# alignment check: return correlation at lags
rb, rc = bn.pct_change(), cb.pct_change()
print("ret corr Binance vs Coinbase at lag -1/0/+1:", [round(rb.corr(rc.shift(k)), 3) for k in (-1, 0, 1)])
prem = cb / bn - 1
print("premium bp by year (mean, std):")
print((prem.groupby(prem.index.year).agg(["mean", "std"]) * 1e4).round(1).T.to_string())


def zscore(p, win=720):
    p = p.dropna()
    z = (p - p.rolling(win).mean()) / p.rolling(win).std()
    return z.reindex(bn.index)


def hysteresis(z, enter=0.0, exit_=-1.5):
    zv = z.to_numpy(float); out = np.zeros(len(zv)); s = 0.0
    for i, v in enumerate(zv):
        if not np.isnan(v):
            if s == 0.0 and v > enter: s = 1.0
            elif s == 1.0 and v < exit_: s = 0.0
        out[i] = s
    return pd.Series(out, index=z.index)


ret = bn.pct_change()
def vscale(target=0.40, hl=480):
    v = ret.ewm(halflife=hl, min_periods=hl).std() * np.sqrt(H)
    return (target / v).clip(0, 1).fillna(0)
trend50 = (bn > bn.rolling(1200).mean()).astype(float)
trend40 = (bn > bn.rolling(960).mean()).astype(float)
z_eth = zscore(prem)
z_btc = zscore(cbb / bnb - 1)
st_eth = hysteresis(z_eth)
st_btc = hysteresis(z_btc)

d = bn.resample("1D").last()
w_live = trend_filter_weights_daily(d).shift(1, freq="D").reindex(bn.index, method="ffill").fillna(0)
live, _ = bt(w_live, bn)

V = {
    "PRIMARY: ETH prem x SMA50d x vol40": st_eth * trend50 * vscale(),
    "ref: SMA50d x vol40 (no premium)": trend50 * vscale(),
    "ref: live eth-trend-filter (daily)": w_live,
    "ETH prem x vol40 (no trend)": st_eth * vscale(),
    "ETH prem x SMA40d x vol50": st_eth * trend40 * vscale(0.5),
    "BTC prem x SMA50d x vol40 (on ETH)": st_btc * trend50 * vscale(),
    "BTC prem x vol40 (no trend, on ETH)": st_btc * vscale(),
    "live TF x ETH prem state": w_live * st_eth,
}
rows, nets = [], {}
for k, w in V.items():
    net, s = bt(w, bn)
    nets[k] = net
    nd = to_daily(net)
    r = row(nd, ann=365, extra=dict(v=k, AvgExp=s["AvgExposure"], TIM=s["TimeInMkt"], Turn=s["Turnover_ann"],
                                    rho_live=np.corrcoef(net, live)[0, 1]))
    r["Sh_IS22"] = rl.perf_stats(nd.loc[:"2022-12-31"], ann=365)["Sharpe"]
    r["Sh_OOS23"] = rl.perf_stats(nd.loc["2023-01-01":], ann=365)["Sharpe"]
    rows.append(r)
df = pd.DataFrame(rows).set_index("v")
pd.set_option("display.width", 250)
print(df[["Sh_Full", "Sh_IS", "Sh_OOS", "Sh_IS22", "Sh_OOS23", "CAGR", "MDD", "AvgExp", "TIM", "Turn", "rho_live"]].round(2).to_string())
nd = {k: to_daily(v) for k, v in nets.items()}
yr = pd.DataFrame({k: v.groupby(v.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(365)) for k, v in nd.items()
                   if k.startswith(("PRIMARY", "ref: SMA50", "ref: live", "ETH prem x vol40"))})
print(yr.round(2).to_string())
pd.to_pickle(nets, "/tmp/evp_nets.pkl")
