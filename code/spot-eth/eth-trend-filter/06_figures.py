"""Charts for the alpha spec."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "code", "shared")))

import numpy as np, pandas as pd, matplotlib.pyplot as plt
from research_lib import load_btc, backtest, perf_stats, ewm_vol

eth = load_btc(ticker="ETH-USD")["Close"].rename("ETH")
btc = load_btc(ticker="BTC-USD")["Close"].rename("BTC")
df = pd.concat([eth, btc], axis=1, sort=True).dropna()
eth_c = df["ETH"]; eth_r = eth_c.pct_change()

def base_sig(win=40): return (eth_c > eth_c.rolling(win).mean()).astype(float)
def vt(ret, target, hl=20, cap=1.0): return (target / ewm_vol(ret, halflife=hl)).clip(0.0, cap).fillna(0.0)

w_final = base_sig(40) * vt(eth_r, 0.5, hl=20)
net_final, st_final = backtest(w_final, eth_c, cost_bps=10.0, name="final")
net_bh, st_bh = backtest(pd.Series(1.0, index=eth_c.index), eth_c, cost_bps=0.0, name="bh")
net_sma40, st_sma40 = backtest(base_sig(40), eth_c, cost_bps=10.0, name="sma40")

out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "alphas", "spot-eth", "eth-trend-filter"))
os.makedirs(out_dir, exist_ok=True)

# --- Chart 1: equity curves
fig, ax = plt.subplots(figsize=(11,5))
(1+net_bh).cumprod().plot(ax=ax, label=f"ETH buy&hold (Sh={st_bh.Sharpe:.2f}, MDD {st_bh.MaxDD*100:.0f}%)",
                          color="#888", alpha=0.7)
(1+net_sma40).cumprod().plot(ax=ax, label=f"SMA(40) long/flat (Sh={st_sma40.Sharpe:.2f}, MDD {st_sma40.MaxDD*100:.0f}%)",
                             color="steelblue")
(1+net_final).cumprod().plot(ax=ax, label=f"FINAL SMA(40) + vol-target (Sh={st_final.Sharpe:.2f}, MDD {st_final.MaxDD*100:.0f}%)",
                              color="crimson", linewidth=2)
ax.set_yscale("log"); ax.set_title("eth-trend-filter — cumulative equity (log scale), 2017-11 to 2026-09")
ax.legend(loc="upper left"); ax.grid(alpha=0.3)
ax.axvline(pd.Timestamp("2024-01-01"), color="k", linestyle="--", alpha=0.4)
ax.text(pd.Timestamp("2024-01-15"), 1.2, "OOS →", fontsize=9)
plt.tight_layout(); plt.savefig(os.path.join(out_dir, "01_equity.png"), dpi=110); plt.close()

# --- Chart 2: drawdown
fig, ax = plt.subplots(figsize=(11,4))
def dd(net): eq=(1+net).cumprod(); return eq/eq.cummax()-1
dd(net_bh).plot(ax=ax, label="Buy&Hold", color="#888", alpha=0.7)
dd(net_final).plot(ax=ax, label="FINAL", color="crimson")
ax.set_title("Drawdown"); ax.legend(); ax.grid(alpha=0.3)
ax.axvline(pd.Timestamp("2024-01-01"), color="k", linestyle="--", alpha=0.4)
plt.tight_layout(); plt.savefig(os.path.join(out_dir, "02_drawdown.png"), dpi=110); plt.close()

# --- Chart 3: rolling 1y Sharpe
fig, ax = plt.subplots(figsize=(11,4))
r1y_final = net_final.rolling(365).mean() / net_final.rolling(365).std() * np.sqrt(365)
r1y_bh = net_bh.rolling(365).mean() / net_bh.rolling(365).std() * np.sqrt(365)
r1y_bh.plot(ax=ax, label="Buy&Hold", color="#888", alpha=0.7)
r1y_final.plot(ax=ax, label="FINAL", color="crimson")
ax.axhline(1.0, color="k", linestyle=":", alpha=0.5)
ax.axhline(0.0, color="k", alpha=0.3)
ax.set_title("Rolling 1-year Sharpe"); ax.legend(); ax.grid(alpha=0.3)
ax.axvline(pd.Timestamp("2024-01-01"), color="k", linestyle="--", alpha=0.4)
plt.tight_layout(); plt.savefig(os.path.join(out_dir, "03_rolling_sharpe.png"), dpi=110); plt.close()

# --- Chart 4: weight over time
fig, ax = plt.subplots(figsize=(11,4))
w_plot = w_final.shift(1).dropna()
ax.fill_between(w_plot.index, 0, w_plot.values, step="pre", color="steelblue", alpha=0.6)
ax.set_ylim(0, 1.05); ax.set_title("Applied weight (SMA gate × vol-target scalar, capped at 1.0)")
ax.grid(alpha=0.3)
ax.axvline(pd.Timestamp("2024-01-01"), color="k", linestyle="--", alpha=0.4)
plt.tight_layout(); plt.savefig(os.path.join(out_dir, "04_weight.png"), dpi=110); plt.close()

print("Saved charts to", out_dir)
print(os.listdir(out_dir))
