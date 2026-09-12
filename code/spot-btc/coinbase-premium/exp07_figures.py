"""exp07 -- figures for the report / alpha folder."""
import os, sys, warnings
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OUT = os.path.join(ROOT, "alphas", "spot-btc", "coinbase-premium"); os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
from research_lib import DATA_DIR, backtest
from strategy import target_weight, premium_zscore, HOURS_PER_YEAR as HANN
def naive(df): return (df.tz_convert("UTC").tz_localize(None) if df.index.tz is not None else df).sort_index()
b = naive(pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_1h_flow.parquet")))
c = naive(pd.read_parquet(os.path.join(DATA_DIR, "COINBASE_BTCUSD_1h.parquet")))
idx = b.index.intersection(c.index); px, cx = b.loc[idx, "Close"], c.loc[idx, "Close"]
w = target_weight(px, cx)
net, st = backtest(w, px, cost_bps=10, ann=HANN); bh, _ = backtest(pd.Series(1.0, index=px.index), px, cost_bps=10, ann=HANN)
eq, eqb = (1 + net).cumprod(), (1 + bh).cumprod()
pd.DataFrame({"strategy": eq, "buy_hold": eqb, "weight": w}).resample("D").last().to_csv(os.path.join(OUT, "equity.csv"))
fig, ax = plt.subplots(3, 1, figsize=(12, 10), sharex=True, gridspec_kw={"height_ratios": [3, 1, 1]})
ax[0].plot(eq, label=f"coinbase-premium (Sharpe {st['Sharpe']:.2f}, 10bp)", color="#1f77b4"); ax[0].plot(eqb, label="BTC buy & hold", color="#999", lw=0.8)
ax[0].set_yscale("log"); ax[0].axvline(pd.Timestamp("2023-01-01"), color="k", ls="--", lw=0.8); ax[0].legend(); ax[0].set_title("Equity (log), IS | OOS split at 2023-01-01")
dd = eq / eq.cummax() - 1; ax[1].fill_between(dd.index, dd, 0, color="#d62728", alpha=0.5); ax[1].set_title("Drawdown")
ax[2].plot(w.resample("D").mean(), color="#2ca02c", lw=0.7); ax[2].set_title("Target weight (daily mean)")
plt.tight_layout(); plt.savefig(os.path.join(OUT, "equity.png"), dpi=110); plt.close()
# premium signal figure
z = premium_zscore(px, cx); prem = (cx / px - 1) * 1e4
fig, ax = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
ax[0].plot(prem.rolling(24).mean(), lw=0.6, color="#1f77b4"); ax[0].axhline(0, color="k", lw=0.5); ax[0].set_title("Coinbase premium vs Binance, bp (24h mean)")
ax[1].plot(z.resample("D").last(), lw=0.6, color="#ff7f0e"); ax[1].axhline(0, color="k", lw=0.5); ax[1].axhline(-1.5, color="r", lw=0.5, ls="--"); ax[1].set_title("Premium z-score (30d) with enter=0 / exit=-1.5 thresholds")
plt.tight_layout(); plt.savefig(os.path.join(OUT, "premium_signal.png"), dpi=110); plt.close()
# conditional forward-return figure (daily panel)
P = pd.read_parquet(os.path.join(HERE, "panel.parquet"))
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
for a, (nm, seg) in zip(ax, (("IS (2017-08 → 2022-12)", P.loc[:"2022-12-31"]), ("OOS (2023-01 → 2026-09)", P.loc["2023-01-01":]))):
    q = pd.qcut(seg["cbprem_bin_z90"].rank(method="first"), 5, labels=False)
    m = seg["ret_fwd"].groupby(q).mean() * 1e4
    a.bar(range(5), m, color=["#d62728" if v < 0 else "#2ca02c" for v in m]); a.set_xticks(range(5)); a.set_xticklabels(["Q1 low", "Q2", "Q3", "Q4", "Q5 high"])
    a.set_title(f"Next-day BTC return (bp) by premium z quintile, {nm}"); a.axhline(0, color="k", lw=0.5)
plt.tight_layout(); plt.savefig(os.path.join(OUT, "premium_quintiles.png"), dpi=110); plt.close()
print("figures written to", OUT)
