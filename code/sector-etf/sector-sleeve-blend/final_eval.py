"""Final evaluation of the deployable function (strategy.target_weights): headline stats,
alpha vs SPY, cost stress, bootstrap, DSR, drawdown/yearly table, vectorbt cross-check, and the
figures for alphas/sector-etf/sector-sleeve-blend/."""
import sys, os
_H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_H, "..", "shared"))
import importlib.util as iu
import numpy as np, pandas as pd
import data, sxlib as sx
sp = iu.spec_from_file_location("blend_strategy", os.path.join(_H, "strategy.py"))
m = iu.module_from_spec(sp); sp.loader.exec_module(m)
OUT = os.path.join(_H, "..", "..", "..", "alphas", "sector-etf", "sector-sleeve-blend")
START = "2002-01-01"

c = data.load_panel(); o = data.load_panel(field="Open")
W, SL, K = m.target_weights(c, o, return_sleeves=True)
rows = []
for cost in [0, 2, 5]:
    st, net = sx.summary_rf(W, c, name=f"blend@{cost}bp", cost_bps=cost, start=START); rows.append(st)
st, net = sx.summary_rf(W, c, name="blend", start=START)
for k_ in SL:
    s_, _ = sx.summary_rf(SL[k_].mul(K[k_], axis=0), c, name=f"sleeve {k_} (scaled)", start=START); rows.append(s_)
bh = pd.DataFrame(0.0, index=c.index, columns=W.columns); bh["SPY"] = 1.0
sb, spy_x = sx.summary_rf(bh, c, name="SPY buy&hold", start=START); rows.append(sb)
T = pd.DataFrame(rows).rename(columns={"CAGRx": "CAGR (excess)"})
print(sx.fmt(T.rename(columns={"CAGR (excess)": "CAGR"})).to_string())
T.to_csv(os.path.join(OUT, "stats.csv"))

# alpha vs SPY
import statsmodels.api as sm
for seg, (a, b) in sx.SPLITS.items():
    y = net.loc[max(a, START):b]; x = spy_x.loc[y.index]
    res = sm.OLS(y, sm.add_constant(x)).fit(cov_type="HAC", cov_kwds={"maxlags": 21})
    resid = y - res.params.iloc[1] * x
    print(f"{seg:5s} alpha {res.params.iloc[0]*252*100:5.2f}%/yr  t {res.tvalues.iloc[0]:.2f}  beta {res.params.iloc[1]:.2f}  "
          f"resid-Sharpe {resid.mean()/resid.std()*np.sqrt(252):.2f}")
# plain-return (non-excess) stats as the live book will show them
gross_ret, _ = sx.summary(W, c, name="blend total-return", start=START)
print("total-return (not excess) Sharpe:", gross_ret[["Sh_full", "Sh_IS", "Sh_OOS", "CAGR", "MaxDD"]].round(3).to_dict())
# 2003+ (first year with >= 3 sleeves eligible) -- reported as a secondary number only
y3 = net.loc["2003":]; print("2003+ Sharpe", round(y3.mean() / y3.std() * np.sqrt(252), 3))
# bootstrap + DSR
rng = np.random.default_rng(7); x = net.values; n = len(x); out = []
for _ in range(2000):
    idx = []; i = rng.integers(n)
    while len(idx) < n:
        idx.append(i); i = (i + 1) % n if rng.random() > 1 / 21 else rng.integers(n)
    z = x[idx]; out.append(z.mean() / z.std() * np.sqrt(252))
out = np.array(out)
print(f"bootstrap 5/50/95 {np.percentile(out,5):.2f}/{np.percentile(out,50):.2f}/{np.percentile(out,95):.2f} P(>1) {np.mean(out>1):.2f}")
sr = net.mean() / net.std() * np.sqrt(252)
for N in [30, 200, 1000]:
    print(f"DSR N={N}: {sx.dsr(sr, len(net), N, net.skew(), net.kurtosis()+3):.3f}")
yr = pd.DataFrame({"blend": net.groupby(net.index.year).apply(lambda z: (1 + z).prod() - 1),
                   "SPY": spy_x.groupby(spy_x.index.year).apply(lambda z: (1 + z).prod() - 1)}) * 100
print(yr.round(1).T.to_string())
yr.to_csv(os.path.join(OUT, "yearly_excess_returns.csv"))
g = W.abs().sum(axis=1).loc[START:]
print(f"gross mean {g.mean():.2f} p99 {g.quantile(.99):.2f} max {g.max():.2f}; net long mean {W.sum(axis=1).loc[START:].mean():.2f}")
# vectorbt cross-check (total returns, 2 bp fees, target percent at close)
import vectorbt as vbt
px = c[W.columns].loc[START:].ffill().bfill(); tw = W.loc[START:]
pf = vbt.Portfolio.from_orders(px, size=tw, size_type="targetpercent", fees=2e-4, group_by=True,
                               cash_sharing=True, call_seq="auto", freq="1D", init_cash=1e7)
vr = pf.returns()
tr, tnet = sx.summary(W, c, start=START)
print(f"vectorbt full scale (cash account cannot borrow -> under-holds on the ~2 % of days net long > 1): "
      f"Sharpe {vr.mean()/vr.std()*np.sqrt(252):.3f} vs research {tnet.mean()/tnet.std()*np.sqrt(252):.3f}; corr {vr.corr(tnet):.4f}")
pf3 = vbt.Portfolio.from_orders(px, size=tw / 3, size_type="targetpercent", fees=2e-4, group_by=True,
                                cash_sharing=True, call_seq="auto", freq="1D", init_cash=1e7)
v3 = pf3.returns(); _, t3 = sx.summary(W / 3, c, start=START)
print(f"vectorbt at 1/3 scale (no margin needed): Sharpe {v3.mean()/v3.std()*np.sqrt(252):.3f} vs research "
      f"{t3.mean()/t3.std()*np.sqrt(252):.3f}; corr {v3.corr(t3):.4f}")
# figures
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
eq = (1 + net).cumprod(); eqs = (1 + spy_x).cumprod()
ax[0].plot(eq.index, eq, color="#1f5fa8", lw=1.4, label="sector-sleeve-blend (excess of T-bills, 2 bp)")
ax[0].plot(eqs.index, eqs, color="#9a9a9a", lw=1.0, label="SPY buy & hold (excess)")
ax[0].axvline(pd.Timestamp("2015-01-01"), color="k", ls=":", lw=0.8); ax[0].text(pd.Timestamp("2015-03-01"), ax[0].get_ylim()[1]*0.9, "OOS", fontsize=9)
ax[0].set_yscale("log"); ax[0].legend(frameon=False, loc="upper left"); ax[0].set_ylabel("growth of 1")
ax[0].spines[["top", "right"]].set_visible(False)
dd = eq / eq.cummax() - 1
ax[1].fill_between(dd.index, dd, 0, color="#1f5fa8", alpha=0.4); ax[1].set_ylabel("drawdown")
ax[1].spines[["top", "right"]].set_visible(False)
plt.tight_layout(); plt.savefig(os.path.join(OUT, "equity_drawdown.png"), dpi=120); plt.close()
# sleeve contributions
fig, ax = plt.subplots(figsize=(10, 4.5))
colors = {"ON": "#1f5fa8", "CAL": "#d9822b", "DIP": "#3a9a5b", "RATE": "#8e5ea2"}
for k_ in SL:
    _, sn = sx.summary_rf(SL[k_].mul(K[k_], axis=0), c, start=START)
    ax.plot(sn.index, sn.cumsum() * 100, color=colors[k_], lw=1.2, label=k_)
ax.axvline(pd.Timestamp("2015-01-01"), color="k", ls=":", lw=0.8)
ax.set_ylabel("cumulative excess return, % (sum)"); ax.legend(frameon=False, ncol=4)
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout(); plt.savefig(os.path.join(OUT, "sleeve_contributions.png"), dpi=120); plt.close()
pd.DataFrame({"net_excess_2bp": net, "spy_excess": spy_x}).to_parquet(os.path.join(OUT, "backtest_series.parquet"))
