"""Final evaluation of the deployable rule (imports strategy.py), figures, spec tables."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared")); sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import statsmodels.api as sm
import vc_data as vc, research_lib as rl, vc_plot as vp
from fetch_cot_vix import fetch_tff
from strategy import target_weight
import matplotlib.pyplot as plt

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
ALPHA = os.path.join(REPO, "alphas", "vol-complex", "vix-cot-positioning")
REP = os.path.join(REPO, "past_research", "vol-complex", "vix-cot-positioning")
P = vc.panel()
tff = fetch_tff()
w = target_weight(P["VIXY"], P["VIX"], P["VIX3M"], tff)
net, st = vc.bt(w, P["VIXY"], 5, "vix-cot-positioning")
carry_w = pd.Series(np.where((P["VIX3M"] / P["VIX"]).shift(1) > 1, -1.0, 0.0), index=P.index)
cnet, cst = vc.bt(carry_w, P["VIXY"], 5, "carry (lag 1)")
old = pd.read_parquet(os.path.join(HERE, "ens_returns.parquet"))["ens25_lag1"]
print("matches 05 ensemble:", np.allclose(old.values, net.values))

rows = {}
for nm, r, s in (("strategy", net, st), ("carry ref lag1", cnet, cst)):
    for k, (a, b) in vc.SPLITS.items():
        p = rl.perf_stats(r.loc[a:b], ann=252)
        rows[(nm, k)] = {"Sharpe": p["Sharpe"], "CAGR": p["CAGR"], "Vol": p["Vol"], "MaxDD": p["MaxDD"],
                         "Skew": p["Skew"], "t_NW": p["t_NW"], "Sortino": p["Sortino"]}
    rows[(nm, "FULL")].update({"Turnover_ann": s["Turnover_ann"], "AvgExposure": s["AvgExposure"]})
T = pd.DataFrame(rows).T
print(T.round(3))
T.round(4).to_csv(os.path.join(ALPHA, "stats.csv"))
spy = P["SPY"].pct_change()
for k, (a, b) in vc.SPLITS.items():
    d = pd.concat([net.rename("y"), spy.rename("spy")], axis=1).loc[a:b].dropna()
    m = sm.OLS(d["y"], sm.add_constant(d["spy"])).fit(cov_type="HAC", cov_kwds={"maxlags": 10})
    print(k, "SPY beta %.2f alpha %.1f%%/yr t %.2f" % (m.params["spy"], 100 * 252 * m.params["const"], m.tvalues["const"]))
e = w.shift(1)
print("time short %.1f%%, avg |w| when short %.2f, full-size days %.1f%%" % (
    100 * (e < 0).mean(), -e[e < 0].mean(), 100 * (e <= -0.999).mean()))
worst = net.nsmallest(8)
print("worst days:\n", pd.DataFrame({"net": worst, "w": e.loc[worst.index], "VIXY": P["VIXY"].pct_change().loc[worst.index]}).round(3))
print("VIXY worst daily returns (gap risk at -1x):", P["VIXY"].pct_change().nlargest(5).round(3).to_dict())

# truncation test: weights computed on data cut at D equal the full-run weights at D
for cut in ["2019-06-14", "2022-03-31", "2024-08-02", "2026-06-30"]:
    Pc = P.loc[:cut]
    tc = tff[tff["avail_utc"] < pd.Timestamp(cut) + pd.Timedelta(days=1)]
    wc = target_weight(Pc["VIXY"], Pc["VIX"], Pc["VIX3M"], tc)
    print("truncation", cut, "max |diff|", float((wc - w.loc[:cut]).abs().max()))
yr = pd.DataFrame({"strategy": vc.yearly_sharpe(net), "carry_lag1": vc.yearly_sharpe(cnet),
                   "strategy_ret": net.groupby(net.index.year).apply(lambda r: (1 + r).prod() - 1)})
yr.round(3).to_csv(os.path.join(ALPHA, "yearly.csv"))
pd.DataFrame({"weight_VIXY": w, "net_ret": net, "carry_lag1_net": cnet}).to_parquet(
    os.path.join(ALPHA, "backtest_series.parquet"))

vp.style()
eq, ceq = (1 + net).cumprod(), (1 + cnet).cumprod()
fig, ax = plt.subplots(2, 1, figsize=(8, 5.6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
ax[0].plot(eq, color=vp.SERIES[0], label="COT-gated short VIXY"); ax[0].plot(ceq, color=vp.SERIES[1], label="contango carry (lag 1)")
ax[0].set_yscale("log"); ax[0].set_title("Growth of $1, net of 5 bp/side (log scale)"); ax[0].legend(loc="upper left")
vp.direct_label(ax[0], eq, "%.1fx" % eq.iloc[-1], vp.SERIES[0]); vp.direct_label(ax[0], ceq, "%.1fx" % ceq.iloc[-1], vp.SERIES[1])
ax[0].axvline(pd.Timestamp("2019-01-01"), color=vp.NEUTRAL, lw=1, ls="--"); ax[0].text(pd.Timestamp("2019-02-01"), ax[0].get_ylim()[0] * 1.3, "OOS →", color=vp.INK2, fontsize=8)
ax[1].plot(eq / eq.cummax() - 1, color=vp.SERIES[0]); ax[1].plot(ceq / ceq.cummax() - 1, color=vp.SERIES[1])
ax[1].set_title("Drawdown"); ax[1].yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
fig.tight_layout(); fig.savefig(os.path.join(ALPHA, "equity_drawdown.png")); fig.savefig(os.path.join(REP, "01_equity_drawdown.png"))

W = tff.set_index("date"); am = (W["am_long"] - W["am_short"]) / W["oi"]
fig, ax = plt.subplots(2, 1, figsize=(8, 4.8), sharex=True)
ax[0].plot(am.loc["2010":], color=vp.SERIES[0], lw=1.2); ax[0].axhline(0, color=vp.NEUTRAL, lw=0.8)
ax[0].set_title("Asset-manager net share of VIX-futures open interest (CFTC TFF, weekly)")
ax[0].yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
for d in ["2018-02-05", "2020-03-16", "2024-08-05", "2025-04-08"]:
    for a_ in ax: a_.axvline(pd.Timestamp(d), color=vp.SERIES[1], lw=0.8, ls=":")
ax[1].fill_between(e.index, -e.values, 0, color=vp.SERIES[0], alpha=0.5, lw=0)
ax[1].set_title("Strategy short VIXY exposure (dotted: VIX spike days)"); ax[1].set_ylim(0, 1.05)
fig.tight_layout(); fig.savefig(os.path.join(ALPHA, "signal_exposure.png")); fig.savefig(os.path.join(REP, "02_signal_exposure.png"))

fig, ax = plt.subplots(figsize=(8, 3.2))
x = np.arange(len(yr)); bw = 0.38
ax.bar(x - bw / 2 - 0.01, yr["strategy"], bw, color=vp.SERIES[0], label="COT-gated short VIXY")
ax.bar(x + bw / 2 + 0.01, yr["carry_lag1"], bw, color=vp.SERIES[1], label="contango carry (lag 1)")
ax.set_xticks(x); ax.set_xticklabels(yr.index, fontsize=8); ax.axhline(0, color=vp.INK2, lw=0.8)
ax.set_title("Sharpe by calendar year"); ax.legend(loc="upper left", ncol=2)
fig.tight_layout(); fig.savefig(os.path.join(ALPHA, "yearly_sharpe.png")); fig.savefig(os.path.join(REP, "03_yearly_sharpe.png"))
print(yr.round(2))
