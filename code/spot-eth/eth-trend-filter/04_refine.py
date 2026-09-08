"""Refine the winning ETH-price-above-SMA(50) signal with overlays.

Overlays tested (each layered on top of the base signal):
  1. BTC trend confirmation (long only if BTC also above own SMA)
  2. Vol-conditional reduction (reduce when 30d vol > high threshold)
  3. Drawdown control (cut when in deep DD)
  4. Ratio (ETH/BTC) tilt as continuous scaler
  5. Weekday effect

Also: cost sensitivity, and a walk-forward re-selection.
"""
import os, sys, itertools
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "code", "shared")))

import numpy as np, pandas as pd
from research_lib import load_btc, backtest, perf_stats, fmt, realized_vol, ewm_vol

eth = load_btc(ticker="ETH-USD")["Close"].rename("ETH")
btc = load_btc(ticker="BTC-USD")["Close"].rename("BTC")
df = pd.concat([eth, btc], axis=1, sort=True).dropna()
eth_c = df["ETH"]; btc_c = df["BTC"]
ratio = eth_c / btc_c
eth_r = eth_c.pct_change()
btc_r = btc_c.pct_change()

IS_END = "2023-12-31"; OOS_START = "2024-01-01"

def evaluate(w, name="s", cost=10.0):
    net, st = backtest(w, eth_c, cost_bps=cost, name=name)
    is_st = perf_stats(net.loc[:IS_END], name=f"{name}_IS")
    oos_st = perf_stats(net.loc[OOS_START:], name=f"{name}_OOS")
    return net, st, is_st, oos_st

def base_signal(win=50):
    return (eth_c > eth_c.rolling(win).mean()).astype(float)

print("== Base signal: ETH > SMA(w) ==")
for w in [30, 40, 50, 60, 70, 100]:
    net, st, is_, oo = evaluate(base_signal(w), name=f"sma{w}")
    print(f"SMA{w}: Full {st.Sharpe:.2f} | IS {is_.Sharpe:.2f} | OOS {oo.Sharpe:.2f} "
          f"| CAGR {st.CAGR*100:.1f}% | MDD {st.MaxDD*100:.1f}% | TIM {st.TimeInMkt*100:.1f}%")

print("\n== SMA50 + BTC>SMA(w_b) filter (both must be up) ==")
b50 = base_signal(50)
for wb in [30, 50, 70, 100, 150, 200]:
    btc_sig = (btc_c > btc_c.rolling(wb).mean()).astype(float)
    w = b50 * btc_sig
    net, st, is_, oo = evaluate(w, name=f"eb_{wb}")
    print(f"BTC>SMA{wb}: Full {st.Sharpe:.2f} | IS {is_.Sharpe:.2f} | OOS {oo.Sharpe:.2f} "
          f"| CAGR {st.CAGR*100:.1f}% | MDD {st.MaxDD*100:.1f}% | TIM {st.TimeInMkt*100:.1f}%")

print("\n== SMA50 + vol regime filter (long only when vol <= high threshold) ==")
vol30 = realized_vol(eth_r, 30)
for q in [0.99, 0.95, 0.90, 0.85, 0.80]:
    # rolling percentile threshold, expanding (past only)
    thr = vol30.expanding(252).quantile(q).shift(1)
    keep = (vol30 <= thr).astype(float)
    w = b50 * keep
    net, st, is_, oo = evaluate(w, name=f"vf_{q}")
    print(f"vol<=q{q}: Full {st.Sharpe:.2f} | IS {is_.Sharpe:.2f} | OOS {oo.Sharpe:.2f} "
          f"| CAGR {st.CAGR*100:.1f}% | MDD {st.MaxDD*100:.1f}% | TIM {st.TimeInMkt*100:.1f}%")

print("\n== SMA50 + inverse-vol scaling (cap 1.0) ==")
def vt_scalar(ret, target, hl=20):
    v = ewm_vol(ret, halflife=hl)
    return (target / v).clip(0.0, 1.0).fillna(0.0)
for tgt in [0.5, 0.6, 0.7, 0.8, 1.0, 1.5]:
    w = b50 * vt_scalar(eth_r, tgt)
    net, st, is_, oo = evaluate(w, name=f"vt_{tgt}")
    print(f"vol-target={tgt}: Full {st.Sharpe:.2f} | IS {is_.Sharpe:.2f} | OOS {oo.Sharpe:.2f} "
          f"| CAGR {st.CAGR*100:.1f}% | MDD {st.MaxDD*100:.1f}% | TIM {st.TimeInMkt*100:.1f}%")

print("\n== SMA50 + ratio momentum tilt (scale weight by ratio 60d z-score sign) ==")
r_z = (ratio - ratio.rolling(60).mean()) / ratio.rolling(60).std()
# tilt = 1 if z>0.5, 0.5 if -0.5<z<=0.5, 0 if z<=-0.5
tilt = pd.Series(0.5, index=r_z.index)
tilt = tilt.where(r_z.shift(0) > -0.5, 0.0)
tilt = tilt.where(r_z <= 0.5, 1.0)
w = b50 * tilt
net, st, is_, oo = evaluate(w, name="ratio_tilt")
print(f"ratio-tilt: Full {st.Sharpe:.2f} | IS {is_.Sharpe:.2f} | OOS {oo.Sharpe:.2f} "
      f"| CAGR {st.CAGR*100:.1f}% | MDD {st.MaxDD*100:.1f}% | TIM {st.TimeInMkt*100:.1f}%")

print("\n== Cost sensitivity for SMA50 base ==")
for c in [0.0, 5.0, 10.0, 20.0, 40.0]:
    net, st, is_, oo = evaluate(b50, name=f"c{c}", cost=c)
    print(f"cost={c}bp: Full {st.Sharpe:.2f} | IS {is_.Sharpe:.2f} | OOS {oo.Sharpe:.2f} "
          f"| turnover/yr={st.Turnover_ann:.1f}")

print("\n== Walk-forward: pick best SMA window on trailing 730d, apply next 90d ==")
windows = [20, 30, 40, 50, 60, 70, 100, 150, 200]
wf_w = pd.Series(0.0, index=eth_c.index)
train_days = 730; step = 90
dates = eth_c.index
start_i = train_days
i = start_i
picks = []
while i < len(dates):
    end_i = min(i + step, len(dates))
    train_end = dates[i-1]
    train_start = dates[max(0, i - train_days)]
    best_win = None; best_sh = -np.inf
    for wi in windows:
        w_full = (eth_c > eth_c.rolling(wi).mean()).astype(float)
        net_full, _ = backtest(w_full, eth_c, cost_bps=10.0)
        seg = net_full.loc[train_start:train_end]
        sh = perf_stats(seg).Sharpe
        if pd.notna(sh) and sh > best_sh:
            best_sh = sh; best_win = wi
    picks.append((dates[i], best_win, best_sh))
    w_apply = (eth_c > eth_c.rolling(best_win).mean()).astype(float)
    wf_w.loc[dates[i]:dates[end_i-1]] = w_apply.loc[dates[i]:dates[end_i-1]].values
    i = end_i

net_wf, st_wf = backtest(wf_w, eth_c, cost_bps=10.0, name="walkfwd")
is_wf = perf_stats(net_wf.loc[:IS_END], name="wf_IS")
oo_wf = perf_stats(net_wf.loc[OOS_START:], name="wf_OOS")
print(f"Walk-fwd: Full {st_wf.Sharpe:.2f} | IS {is_wf.Sharpe:.2f} | OOS {oo_wf.Sharpe:.2f} "
      f"| CAGR {st_wf.CAGR*100:.1f}% | MDD {st_wf.MaxDD*100:.1f}%")
print("First 5 & last 5 picks:")
for d, w, sh in picks[:5]: print(f"  {d.date()} win={w} trainSh={sh:.2f}")
print("  ...")
for d, w, sh in picks[-5:]: print(f"  {d.date()} win={w} trainSh={sh:.2f}")
from collections import Counter
print("Pick histogram:", Counter([p[1] for p in picks]))
