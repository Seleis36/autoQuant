"""Exp 20 - Final performance summary + chart for BULT."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from research_lib import *
from strategy import *
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 60)

H = load_hourly()
SPEC = dict(vol_target=0.35, vol_hl=20, gate_thr=-0.010, b=0.5); COST = 3.0
w, P = build_signals(H, **SPEC); hret = P["hret"]
net, turn = backtest_hourly(w, hret, COST)
bh, _ = backtest_hourly(pd.Series(1.0, index=hret.index), hret, 0.0)

eq, eqb = (1+net).cumprod(), (1+bh).cumprod()
print("=== FINAL: BTC US-Close Liquidity Timer (BULT) ===")
print(pd.DataFrame([stats(net, turn, "BULT @3bp"), stats(bh, None, "Buy & Hold")]).round(3).to_string())

# monthly returns table
m = (1+net).resample("ME").prod()-1
mt = m.to_frame("r"); mt["y"]=mt.index.year; mt["m"]=mt.index.month
piv = mt.pivot_table(index="y", columns="m", values="r")*100
piv["YEAR"] = ((1+net).resample("YE").prod()-1).values*100
print("\n=== monthly returns (%) ===")
print(piv.round(1).fillna(0).to_string())

# risk / relationship stats
d_net = (1+net).resample("1D").prod()-1
d_bh  = (1+bh).resample("1D").prod()-1
z = pd.concat([d_net.rename("s"), d_bh.rename("b")], axis=1).dropna()
beta = np.polyfit(z.b, z.s, 1)[0]
alpha_ann = (z.s.mean() - beta*z.b.mean())*365
print(f"\ncorrelation to buy&hold (daily): {z.s.corr(z.b):.3f}")
print(f"beta to BTC: {beta:.3f}   annualised alpha: {alpha_ann*100:.1f}%")
print(f"avg exposure: {w.mean()*100:.1f}%   time with any exposure: {(w>0).mean()*100:.1f}%")
print(f"up-day capture: {z[z.b>0].s.mean()/z[z.b>0].b.mean():.3f}   "
      f"down-day capture: {z[z.b<0].s.mean()/z[z.b<0].b.mean():.3f}")
worst = z.s.nsmallest(5); print(f"\n5 worst days: " + ", ".join(f"{i.date()}:{v*100:.1f}%" for i,v in worst.items()))

# cost / target grid for the report
print("\n=== headline Sharpe across cost x vol-target ===")
grid = {}
for vt in [0.25, 0.30, 0.35, 0.40, 0.50]:
    row = {}
    for c in [0.0, 3.0, 5.0, 10.0]:
        ww, PP = build_signals(H, **{**SPEC, "vol_target": vt})
        nn, _ = backtest_hourly(ww, PP["hret"], c)
        row[f"{c}bp"] = nn.mean()/nn.std()*np.sqrt(HANN)
    grid[f"voltgt {int(vt*100)}%"] = row
print(pd.DataFrame(grid).T.round(2).to_string())

# ---- chart
fig, ax = plt.subplots(3, 1, figsize=(13, 12), height_ratios=[3,1.2,1.2], sharex=True)
ax[0].plot(eq.index, eq.values, lw=1.6, color="#1f77b4", label="BULT (3bp/side)")
ax[0].plot(eqb.index, eqb.values, lw=1.2, color="#999999", label="BTC buy & hold")
ax[0].set_yscale("log"); ax[0].set_ylabel("growth of $1 (log)")
ax[0].set_title("BTC US-Close Liquidity Timer — spot, long/flat, no leverage\n"
                f"Sharpe {stats(net,turn)['Sharpe']:.2f} (IS 1.74 / OOS 1.20) · CAGR "
                f"{stats(net,turn)['CAGR%']:.1f}% · MaxDD {stats(net,turn)['MaxDD%']:.1f}%", fontsize=12)
ax[0].axvline(pd.Timestamp("2022-01-01"), color="k", ls="--", lw=0.9)
ax[0].text(pd.Timestamp("2022-01-15"), eq.max()*0.5, "out-of-sample →", fontsize=9)
ax[0].axvline(pd.Timestamp("2024-01-11"), color="g", ls=":", lw=0.9)
ax[0].legend(loc="upper left"); ax[0].grid(alpha=0.3)

ax[1].fill_between(eq.index, (eq/eq.cummax()-1).values*100, 0, color="#1f77b4", alpha=0.6, label="BULT")
ax[1].fill_between(eqb.index, (eqb/eqb.cummax()-1).values*100, 0, color="#999999", alpha=0.4, label="B&H")
ax[1].set_ylabel("drawdown %"); ax[1].legend(loc="lower left"); ax[1].grid(alpha=0.3)

expo = w.resample("1D").mean()*100
ax[2].plot(expo.index, expo.values, lw=0.7, color="#d62728")
ax[2].set_ylabel("exposure %"); ax[2].set_xlabel("date"); ax[2].grid(alpha=0.3)
plt.tight_layout()
out = "/home/seleis/autoQuant/alphas/bult_performance.png"
os.makedirs(os.path.dirname(out), exist_ok=True)
plt.savefig(out, dpi=115); print(f"\nchart -> {out}")

# hour-of-day profile chart (the core evidence)
hh = pd.DatetimeIndex(hret.index).hour
prof = pd.DataFrame({"r": hret, "h": hh}).dropna()
fig2, axx = plt.subplots(1, 2, figsize=(13, 4.2))
for lab, sl, col in [("2017-2021 (IS)", slice(None,"2021-12-31"), "#7f7f7f"),
                     ("2022-2026 (OOS)", slice("2022-01-01",None), "#1f77b4"),
                     ("2024+ (ETF era)", slice("2024-01-11",None), "#2ca02c")]:
    s = prof.loc[sl]; g = s.groupby("h")["r"]
    axx[0].plot(g.mean().index, g.mean().values*1e4, marker="o", ms=3, label=lab, color=col)
    axx[1].plot(g.mean().index, (g.mean()/g.std()*np.sqrt(24*365)).values, marker="o", ms=3, label=lab, color=col)
for a, t in zip(axx, ["mean hourly return (bp)", "annualised Sharpe"]):
    a.axvspan(19.5, 22.5, color="orange", alpha=0.18)
    a.axhline(0, color="k", lw=0.7); a.set_xlabel("UTC hour"); a.set_title(t)
    a.grid(alpha=0.3); a.legend(fontsize=8)
axx[0].text(21, axx[0].get_ylim()[1]*0.82, "US close /\nETF NAV", ha="center", fontsize=8)
plt.tight_layout()
out2 = "/home/seleis/autoQuant/alphas/btc_hour_of_day.png"
plt.savefig(out2, dpi=115); print(f"chart -> {out2}")
