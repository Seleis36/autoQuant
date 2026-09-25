"""eth-btc-relative-momentum 02: (a) beta-hedged residual momentum (ETH - beta*BTC, beta = EWM-60d),
(b) risk-on/off pair: long ETH/short BTC when BTC > SMA(L), reverse when below,
(c) short-horizon ratio reversal (sign flipped) -- reported to show the IS/OOS regime flip."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
from ethdata import rl, bars, row, trend_filter_weights_daily
e = bars("ETHUSDT", "1h").resample("1D")["Close"].last(); b = bars("BTCUSDT", "1h").resample("1D")["Close"].last()
px = pd.concat({"ETH": e, "BTC": b}, axis=1).dropna(); r = px.pct_change()
cov = r.ETH.ewm(halflife=60, min_periods=60).cov(r.BTC); var = r.BTC.ewm(halflife=60, min_periods=60).var()
beta = (cov / var).clip(0.5, 2.0)
resid = (r.ETH - beta.shift(1) * r.BTC).fillna(0); cum = resid.cumsum()
rv = resid.ewm(halflife=20, min_periods=20).std() * np.sqrt(365)
tf, _ = rl.backtest(trend_filter_weights_daily(px.ETH), px.ETH, cost_bps=10)
rows = []
def run(sETH, sBTC, **kw):
    net, st = rl.backtest_xs(pd.DataFrame({"ETH": sETH, "BTC": sBTC}).fillna(0), px, cost_bps=10, ann=365)
    net = net.loc["2017-12-01":]
    rows.append(row(net, ann=365, extra=dict(**kw, Turn=st["Turnover_ann"], rho_tf=net.corr(tf.loc[net.index]),
                                             rho_eth=net.corr(r.ETH.loc[net.index]))))
for L in [7, 14, 30, 60, 90]:
    s = np.sign(cum - cum.shift(L)); sc = (0.2 / rv).clip(upper=1)
    run(s * sc, -s * sc * beta, v=f"(a) resid mom {L}d, beta-hedged")
for L in [20, 50, 100, 200]:
    s = np.where(px.BTC > px.BTC.rolling(L).mean(), 1.0, -1.0)
    s = pd.Series(s, index=px.index); sc = (0.2 / (np.log(px.ETH / px.BTC).diff().ewm(halflife=20).std() * np.sqrt(365))).clip(upper=1)
    run(s * sc, -s * sc, v=f"(b) risk-on pair, BTC>SMA{L}")
for L in [3, 7, 14]:
    lrat = np.log(px.ETH / px.BTC); s = -np.sign(lrat - lrat.shift(L))
    sc = (0.2 / (lrat.diff().ewm(halflife=20).std() * np.sqrt(365))).clip(upper=1)
    run(s * sc, -s * sc, v=f"(c) ratio reversal {L}d")
pd.set_option("display.width", 220)
print(pd.DataFrame(rows)[["v", "Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "Turn", "rho_tf", "rho_eth"]].round(2).to_string(index=False))
