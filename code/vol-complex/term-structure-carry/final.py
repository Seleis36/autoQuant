"""Final honest evaluation of the reference rule (short VIXY if VIX3M/VIX>1) and the ensemble variant."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tsc_lib import *
from strategy import target_weight
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "..", "..", "..", "past_research", "vol-complex", "term-structure-carry"); os.makedirs(FIG, exist_ok=True)
pd.set_option("display.width", 220)
df = load_all(); f = features(df)
closes = df[["vixy"]]; COST = {"vixy": 5.0}
w_ref = target_weight(df.vixy, df.vix, df.vix3m)
sma200 = df.spy / df.spy.rolling(200).mean()
score = pd.DataFrame({"slope": f.slope > 1, "vrp": f.vrp10 > 0, "vixma": f.vix_ma10 < 1, "spy": sma200 > 1, "vvix": f.vvix < 95}).astype(float).mean(axis=1)
cands = {"ref: short VIXY if VIX3M/VIX>1": w_ref, "ref lag1": w_ref.shift(1).fillna(0.0), "ensemble -score(5 flags)": -score,
         "short VIXY always": pd.Series(-1.0, df.index)}
nets = {}
rows = []
for name, w in cands.items():
    for cost in [0.0, 5.0, 10.0]:
        net, st = bt_multi(pd.DataFrame({"vixy": w}), closes, {"vixy": cost}, name=name)
        r = report(net)
        rows.append({"variant": name, "cost_bp": cost, "Sh_full": r.Sharpe["full"], "Sh_IS": r.Sharpe["IS"], "Sh_OOS": r.Sharpe["OOS"],
                     "CAGR": r.CAGR["full"], "Vol": r.Vol["full"], "MaxDD": r.MaxDD["full"], "Skew": r.Skew["full"], "t_NW": r.t_NW["full"],
                     "TO": st["Turnover_ann"], "Gross": st["GrossExp"]})
        if cost == 5.0: nets[name] = net
T = pd.DataFrame(rows); print(T.round(2).to_string(index=False))
ref = nets["ref: short VIXY if VIX3M/VIX>1"]
print("\nYearly Sharpe, ref:\n", yearly_sharpe(ref).round(2).to_string())
# block bootstrap (21-day blocks) of full-sample Sharpe
rng = np.random.default_rng(0); x = ref.values; n = len(x); B = 21
sh = []
for _ in range(2000):
    starts = rng.integers(0, n - B, size=n // B + 1); s = np.concatenate([x[i:i + B] for i in starts])[:n]
    sh.append(s.mean() / s.std() * np.sqrt(ANN))
sh = np.array(sh); print(f"\nBootstrap Sharpe 5-95%: [{np.percentile(sh, 5):.2f}, {np.percentile(sh, 95):.2f}]  P(Sh>1)={np.mean(sh > 1):.2f}  P(Sh>1.5)={np.mean(sh > 1.5):.3f}")
st = rl.perf_stats(ref, ANN)
for ntr in [1, 140]:
    print(f"Deflated Sharpe prob (N trials={ntr}):", round(rl.deflated_sharpe(st.Sharpe, st.N, ntr, st.Skew, st.Kurt + 3, ANN), 3))
# ---- figures (palette: validated light categorical slots 1-3)
C = ["#2a78d6", "#eb6834", "#1baf7a"]
spy = df.spy.pct_change().fillna(0.0).loc[ref.index]
eq = pd.DataFrame({"short VIXY if contango (net 5bp)": (1 + ref).cumprod(), "short VIXY always (net 5bp)": (1 + nets["short VIXY always"]).cumprod(), "SPY": (1 + spy).cumprod()})
fig, ax = plt.subplots(figsize=(10, 4.5), facecolor="#fcfcfb"); ax.set_facecolor("#fcfcfb")
for i, c in enumerate(eq.columns): ax.plot(eq.index, eq[c], color=C[i], lw=2, label=c)
ax.set_yscale("log"); ax.set_title("Growth of $1, 2011-2026 (log scale)", loc="left", color="#0b0b0b"); ax.legend(frameon=False); ax.grid(alpha=0.2); [s.set_visible(False) for s in ax.spines.values()]
fig.tight_layout(); fig.savefig(os.path.join(FIG, "01_equity.png"), dpi=130); plt.close(fig)
dd = (1 + ref).cumprod(); dd = dd / dd.cummax() - 1
fig, ax = plt.subplots(figsize=(10, 3.2), facecolor="#fcfcfb"); ax.set_facecolor("#fcfcfb")
ax.fill_between(dd.index, dd, 0, color=C[0], alpha=0.35, lw=0); ax.plot(dd.index, dd, color=C[0], lw=1.5)
ax.set_title("Drawdown, short VIXY if contango (net 5bp)", loc="left"); ax.grid(alpha=0.2); [s.set_visible(False) for s in ax.spines.values()]
ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0)); fig.tight_layout(); fig.savefig(os.path.join(FIG, "02_drawdown.png"), dpi=130); plt.close(fig)
ys = yearly_sharpe(ref)
fig, ax = plt.subplots(figsize=(10, 3.5), facecolor="#fcfcfb"); ax.set_facecolor("#fcfcfb")
ax.bar(ys.index.astype(str), ys.values, color=[C[0] if v >= 0 else C[1] for v in ys.values], width=0.6)
ax.axhline(1.5, color="#52514e", lw=1, ls="--"); ax.text(0, 1.55, "criterion 1.5", color="#52514e", fontsize=9)
ax.set_title("Sharpe by calendar year, short VIXY if contango (net 5bp)", loc="left"); ax.grid(axis="y", alpha=0.2); [s.set_visible(False) for s in ax.spines.values()]
fig.tight_layout(); fig.savefig(os.path.join(FIG, "03_yearly_sharpe.png"), dpi=130); plt.close(fig)
# VIX-level attribution
b = pd.cut(df.vix.shift(1).loc[ref.index], [0, 13, 16, 20, 25, 35, 100])
attr = ref.groupby(b).agg(["sum", "count"]); attr["sharpe"] = ref.groupby(b).apply(lambda x: x.mean() / x.std() * np.sqrt(ANN))
print("\nP&L attribution by VIX level at position entry:\n", attr.round(3).to_string())
fig, ax = plt.subplots(figsize=(8, 3.5), facecolor="#fcfcfb"); ax.set_facecolor("#fcfcfb")
ax.bar([str(i) for i in attr.index], attr["sum"].values, color=C[0], width=0.6)
ax.set_title("Cumulative net return contribution by VIX level at entry", loc="left"); ax.grid(axis="y", alpha=0.2); [s.set_visible(False) for s in ax.spines.values()]
fig.tight_layout(); fig.savefig(os.path.join(FIG, "04_vix_level_attribution.png"), dpi=130); plt.close(fig)
pd.DataFrame({"weight": w_ref, "net_ret_5bp": ref}).to_csv(os.path.join(HERE, "reference_weights_and_returns.csv"))
