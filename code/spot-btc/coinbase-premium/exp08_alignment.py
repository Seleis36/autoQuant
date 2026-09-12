"""exp08 -- integrity checks after exp06:
  (1) timestamp alignment across venues: lagged correlations of hourly returns
  (2) three-way premium decomposition on the common window (hysteresis gate, same trend x vol)
  (3) same-bar sensitivity: corr(change in premium, Binance return) within the bar
  (4) vectorbt cross-check with the correct order timing (size = w, executed at close_t)
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "shared"))
from research_lib import DATA_DIR, backtest, split_stats
from strategy import target_weight, premium_zscore, hysteresis_state, HOURS_PER_YEAR as HANN
IS_END, OOS_START = "2022-12-31", "2023-01-01"
def naive(df): return (df.tz_convert("UTC").tz_localize(None) if df.index.tz is not None else df).sort_index()
b = naive(pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_1h_flow.parquet")))["Close"]
c = naive(pd.read_parquet(os.path.join(DATA_DIR, "COINBASE_BTCUSD_1h.parquet")))["Close"]
s = naive(pd.read_parquet(os.path.join(DATA_DIR, "BITSTAMP_1h.parquet")))["Close"]
y = naive(pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_1h.parquet")))["Close"]   # bult's original cache
i = b.index.intersection(c.index).intersection(s.index).intersection(y.index)
b, c, s, y = b.loc[i], c.loc[i], s.loc[i], y.loc[i]
rb, rc, rs, ry = b.pct_change(), c.pct_change(), s.pct_change(), y.pct_change()
print("common window", i[0], "->", i[-1], len(i))
print("=== (1) corr(r_binance_t, r_other_{t+lag}); a spike at lag!=0 means the other file is stamped differently")
for nm, r in (("coinbase", rc), ("bitstamp", rs), ("bult BTCUSDT_1h cache", ry)):
    print(f"  {nm:22s}", {lag: round(rb.corr(r.shift(-lag)), 3) for lag in (-2, -1, 0, 1, 2)})
print("  price level check (mean ratio to binance):", {"coinbase": round((c / b).mean(), 4), "bitstamp": round((s / b).mean(), 4)})
print("  sample of last rows:\n", pd.DataFrame({"binance": b, "coinbase": c, "bitstamp": s}).tail(3))

print("\n=== (2) three-way decomposition on the common window: hysteresis(0,-1.5) x sma50 x vol, 10bp")
trend = (b > b.rolling(1200).mean()).astype(float)
ewv = rb.ewm(halflife=480, min_periods=480).std() * np.sqrt(HANN); scale = (0.40 / ewv).clip(0, 1).fillna(0)
def z_of(num, den): return premium_zscore(den, num)
combos = {"coinbase/binance": z_of(c, b), "coinbase/bitstamp": z_of(c, s), "bitstamp/binance": z_of(s, b),
          "coinbase/binance, 24h-mean prem": None}
prem24 = (c / b - 1).rolling(24).mean(); combos["coinbase/binance, 24h-mean prem"] = (prem24 - prem24.rolling(720).mean()) / prem24.rolling(720).std()
p24s = (c / s - 1).rolling(24).mean(); combos["coinbase/bitstamp, 24h-mean prem"] = (p24s - p24s.rolling(720).mean()) / p24s.rolling(720).std()
for nm, z in combos.items():
    w = hysteresis_state(z) * trend * scale
    n_, st = backtest(w, b, cost_bps=10, ann=HANN); sp = split_stats(n_, {"IS": (None, IS_END), "OOS": (OOS_START, None)}, ann=HANN)
    print(f"  {nm:34s} full {st['Sharpe']:.2f} IS {sp.loc['IS','Sharpe']:.2f} OOS {sp.loc['OOS','Sharpe']:.2f} expo {st['AvgExposure']:.2f} TO {st['Turnover_ann']:.0f}")
n_, st = backtest(trend * scale, b, cost_bps=10, ann=HANN); sp = split_stats(n_, {"IS": (None, IS_END), "OOS": (OOS_START, None)}, ann=HANN)
print(f"  {'trend x vol only':34s} full {st['Sharpe']:.2f} IS {sp.loc['IS','Sharpe']:.2f} OOS {sp.loc['OOS','Sharpe']:.2f}")
print("  tercile spreads of next-1h Binance return (bp) by each z, full window:")
r1 = rb.shift(-1)
for nm, z in combos.items():
    df = pd.DataFrame({"z": z, "y": r1}).dropna(); q = pd.qcut(df["z"].rank(method="first"), 3, labels=False)
    m = df["y"].groupby(q).mean() * 1e4
    print(f"    {nm:34s}", m.round(2).tolist())

print("\n=== (3) same-bar sensitivity: corr(d prem_t, r_binance_t) and corr(d prem_t, r_coinbase_t)")
dprem = (c / b - 1).diff()
print("  vs binance", round(dprem.corr(rb), 3), " vs coinbase", round(dprem.corr(rc), 3))
print("  lag-1 autocorr of hourly returns: binance", round(rb.autocorr(1), 4), "coinbase", round(rc.autocorr(1), 4), "bitstamp", round(rs.autocorr(1), 4))

print("\n=== (4) vectorbt cross-check, size=w at close_t (earns bar t+1)")
import vectorbt as vbt
w = target_weight(b, c)
net, st = backtest(w, b, cost_bps=10, ann=HANN)
pf = vbt.Portfolio.from_orders(b, size=w, size_type="targetpercent", fees=0.001, init_cash=1.0, freq="1h")
r = pf.returns()
print("  vbt Sharpe", round(r.mean() / r.std() * np.sqrt(HANN), 4), "custom", round(st["Sharpe"], 4), "corr", round(r.corr(net), 5),
      "| total return vbt", round(pf.total_return(), 3), "custom", round((1 + net).prod() - 1, 3), "| max |diff|", round((r - net).abs().max(), 6))
