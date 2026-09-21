"""exp06 -- full validation of the deployable spec (strategy.target_weights defaults) + figures.
Reports return on CAPITAL (L=1 => capital_factor 0.5 is already inside the weights)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from carry_lib import *
from research_lib import newey_west_t
from strategy import target_weights
OUT = os.path.dirname(os.path.abspath(__file__)); FIG = os.path.join(ROOT, "alphas", "crypto-perps", "funding-carry")
pd.set_option("display.width", 200)
coins = ("BTCUSDT", "ETHUSDT")
pairs = {c: load_pair(c, start="2020-01-01") for c in coins}
idx = pd.date_range("2020-01-01", min(p.index.max() for p in pairs.values()), freq="h")
pairs = {c: p.reindex(idx).ffill() for c, p in pairs.items()}
for c in coins: pairs[c]["f"] = pairs[c]["f"].reindex(idx).fillna(0.0)  # never ffill funding
W = target_weights({c: p["S"] for c, p in pairs.items()}, {c: p["P"] for c, p in pairs.items()},
                   {c: p["f"].where(p["f"] != 0).dropna() for c, p in pairs.items()})
nets, turns = {}, {}
for c in coins:
    # backtest_carry applies weight (fraction of capital in one leg) to the one-leg return: return on capital
    net, we, turn = backtest_carry(pairs[c], W[c], fee_bps=15.0, slip_bps=5.0)
    nets[c], turns[c] = net, turn
port = sum(nets.values()); turn = sum(turns.values())
d = daily(port)
s = perf_stats(d); s["Turnover_ann"] = turn.sum() / (len(turn) / HOURS); s["AvgExposure_1leg"] = (W["BTCUSDT"] + W["ETHUSDT"]).mean()
print("=== spec: BTC+ETH, vol-target 2% (hl 30d), L=1, 20 bp/switch -- return on capital"); print(s.round(4).to_string())
print("\nexposure (one-leg, fraction of capital) percentiles:", (W["BTCUSDT"] + W["ETHUSDT"]).quantile([.05, .25, .5, .75, .95]).round(3).to_dict())
tab = {}
for k, (a, b) in SPLITS.items():
    tab[k] = perf_stats(d.loc[a:b], name=k)
tab = pd.DataFrame(tab).T; print("\nIS / OOS:"); print(tab[["CAGR", "Vol", "Sharpe", "MaxDD", "HitRate", "t_NW", "N"]].round(4))
print("\nhorizon dependence:")
for freq, ann in (("D", 365), ("W", 52), ("MS", 12), ("QS", 4)):
    x = (1 + d).resample(freq).prod() - 1
    line = f"  {freq:2s}: full {x.mean()/x.std()*np.sqrt(ann):5.2f}"
    for k, (a, b) in SPLITS.items():
        y = x.loc[a:b]; line += f"  {k} {y.mean()/y.std()*np.sqrt(ann):5.2f}"
    print(line + f"  n={len(x)} hit {(x>0).mean():.2f}")
print("\nyearly:"); print(d.groupby(d.index.year).agg(ret_pct=lambda x: ((1+x).prod()-1)*100, sharpe=lambda x: x.mean()/x.std()*np.sqrt(365), mdd_pct=lambda x: ((1+x).cumprod()/(1+x).cumprod().cummax()-1).min()*100).round(3))
print("\nworst 5 days:"); print(d.nsmallest(5).round(5))
# walk-forward: each calendar year evaluated with parameters fixed in advance (there is no fit); rolling 12m Sharpe min/median
roll = d.rolling(365).apply(lambda x: x.mean()/x.std()*np.sqrt(365)).dropna()
print("\nrolling 12-month Sharpe: min %.2f  5%% %.2f  median %.2f" % (roll.min(), roll.quantile(.05), roll.median()))
rng = np.random.default_rng(0); x = d.values; n = len(x); L = 10; sh = []
for _ in range(2000):
    st = rng.integers(0, n - L, size=n // L + 1); smp = np.concatenate([x[i:i+L] for i in st])[:n]; sh.append(smp.mean()/smp.std()*np.sqrt(365))
print("block-bootstrap daily Sharpe 5/50/95%%: %.2f / %.2f / %.2f" % tuple(np.percentile(sh, [5, 50, 95])))
xm = (1 + d).resample("MS").prod() - 1; xm = xm.values; shm = []
for _ in range(2000):
    smp = rng.choice(xm, size=len(xm), replace=True); shm.append(smp.mean()/smp.std()*np.sqrt(12))
print("bootstrap monthly Sharpe 5/50/95%%: %.2f / %.2f / %.2f  P(>3)=%.2f" % (*np.percentile(shm, [5, 50, 95]), np.mean(np.array(shm) > 3)))
btc = pairs["BTCUSDT"]["S"].resample("1D").last().pct_change(); j = pd.concat([d, btc], axis=1).dropna()
print("beta to BTC %.4f corr %.3f" % (j.cov().iloc[0,1]/j.iloc[:,1].var(), j.corr().iloc[0,1]))
print("\ncost sensitivity (per-switch bp both legs -> daily Sharpe / CAGR):")
for tot in (20, 40, 80):
    p2 = sum(backtest_carry(pairs[c], W[c], fee_bps=tot, slip_bps=0.0)[0] for c in coins); dd = daily(p2); print(f"  {tot} bp: {dd.mean()/dd.std()*np.sqrt(365):.2f} / {perf_stats(dd).CAGR*100:.2f}%")
pd.DataFrame({"port": d, "BTCUSDT": daily(nets["BTCUSDT"]), "ETHUSDT": daily(nets["ETHUSDT"]), "exposure": (W["BTCUSDT"] + W["ETHUSDT"]).resample("1D").last()}).to_parquet(os.path.join(OUT, "exp06_daily.parquet"))

# ---- figures
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"; INK, INK2, SURF = "#0b0b0b", "#52514e", "#fcfcfb"
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
                     "text.color": INK, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#e6e5e1", "grid.linewidth": 0.6, "font.size": 10})
eq = (1 + d).cumprod(); eqb = (1 + daily(nets["BTCUSDT"])).cumprod(); eqe = (1 + daily(nets["ETHUSDT"])).cumprod()
fig, ax = plt.subplots(figsize=(10, 4.2))
ax.plot(eq.index, eq, color=C1, lw=2, label="BTC+ETH carry, vol-targeted (spec)"); ax.plot(eqb.index, eqb, color=C2, lw=1.2, label="BTC sleeve"); ax.plot(eqe.index, eqe, color=C3, lw=1.2, label="ETH sleeve")
ax.set_title("Funding carry: long spot / short perp, return on capital at L=1, net of 20 bp per switch", loc="left"); ax.set_ylabel("Growth of 1"); ax.legend(frameon=False, loc="upper left")
for sr, col, dy in [(eq, C1, 0), (eqb, C2, 5), (eqe, C3, -6)]: ax.annotate(f"{sr.iloc[-1]:.3f}", (sr.index[-1], sr.iloc[-1]), xytext=(4, dy), textcoords="offset points", color=INK2, fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "equity.png"), dpi=150); plt.close(fig)
dd = eq / eq.cummax() - 1; ex = (W["BTCUSDT"] + W["ETHUSDT"]).resample("1D").last()
fig, axes = plt.subplots(2, 1, figsize=(10, 4.8), sharex=True)
axes[0].fill_between(dd.index, dd*100, 0, color=C1, alpha=0.35, lw=0); axes[0].plot(dd.index, dd*100, color=C1, lw=1); axes[0].set_title("Drawdown, % of capital", loc="left")
axes[1].plot(ex.index, ex, color=C1, lw=1.5); axes[1].set_title("Total one-leg exposure, fraction of capital (max 0.5 at L=1)", loc="left"); axes[1].set_ylim(0, 0.55)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "drawdown_exposure.png"), dpi=150); plt.close(fig)
yr = d.groupby(d.index.year).agg(sharpe=lambda x: x.mean()/x.std()*np.sqrt(365), ret=lambda x: ((1+x).prod()-1)*100)
fig, axes = plt.subplots(1, 2, figsize=(10, 3.4))
axes[0].bar(yr.index.astype(str), yr["sharpe"], color=C1, width=0.6); axes[0].axhline(3, color=C2, lw=1.2, ls="--"); axes[0].set_title("Daily-return Sharpe by calendar year (dashed = 3.0)", loc="left")
axes[1].bar(yr.index.astype(str), yr["ret"], color=C1, width=0.6); axes[1].set_title("Return on capital by year, %", loc="left")
for ax in axes: ax.grid(axis="x", visible=False)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "yearly.png"), dpi=150); plt.close(fig)
hz = []
for freq, ann, lab in (("D", 365, "daily"), ("W", 52, "weekly"), ("MS", 12, "monthly"), ("QS", 4, "quarterly")):
    x = (1 + d).resample(freq).prod() - 1; hz.append((lab, x.mean()/x.std()*np.sqrt(ann)))
fig, ax = plt.subplots(figsize=(6, 3.2)); ax.bar([h[0] for h in hz], [h[1] for h in hz], color=C1, width=0.55); ax.axhline(3, color=C2, lw=1.2, ls="--")
ax.set_title("Sharpe vs aggregation horizon (dashed = 3.0)", loc="left"); ax.grid(axis="x", visible=False)
for i, h in enumerate(hz): ax.annotate(f"{h[1]:.1f}", (i, h[1]), xytext=(0, 3 if abs(h[1]-3) > 0.6 else 10), textcoords="offset points", ha="center", color=INK2, fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "horizon.png"), dpi=150); plt.close(fig)
for f in ("drawdown.png",):
    p = os.path.join(FIG, f); os.path.exists(p) and os.remove(p)
print("figures written")
