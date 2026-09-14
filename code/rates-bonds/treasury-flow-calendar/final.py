"""Final numbers and figures for the alpha spec, computed from strategy.py's own weights."""
import os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../../shared"))
sys.path.insert(0, HERE)
import research_lib as rl
import backtest_calendar as bc
import strategy as st

ANN = 252; COST = 2.0
ALPHA = os.path.join(HERE, "../../../alphas/rates-bonds/treasury-flow-calendar")
os.makedirs(ALPHA, exist_ok=True)

# dataviz reference palette (validated: node validate_palette.js "#2a78d6,#eb6834,#1baf7a")
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, SURF, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e6e5e1"
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": GRID,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
                     "axes.spines.right": False, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "font.size": 10, "legend.frameon": False})


def main():
    pd.set_option("display.width", 220)
    tlt = bc.load_close("TLT")
    w = st.target_weight(tlt)
    net, _ = rl.backtest(w, tlt, COST, ANN, "treasury-flow-calendar")
    bh = tlt.pct_change().fillna(0)

    # ---- headline table
    print("\n== strategy.py weights on TLT, 2 bp/side ==")
    _, df = bc.evaluate(w, tlt, COST, "final")
    print(rl.fmt(df).to_string())
    _, dfb = bc.evaluate(pd.Series(1.0, index=tlt.index), tlt, 0.0, "TLT b&h")
    print("\n== TLT buy & hold (0 bp) =="); print(rl.fmt(dfb)[["Sharpe", "CAGR", "Vol", "MaxDD"]].to_string())

    # ---- per-leg attribution (each leg alone, same cost)
    idx = tlt.index
    legs = {"month-end (last 3d, long)": bc.leg_month_end(idx, 3),
            "FOMC (day before + day, long)": bc.leg_fomc(idx, 1, True),
            "pre-auction 10y/20y (2d, short)": bc.leg_pre_auction(idx, ("10y", "20y"), 2)}
    leg_net = {k: rl.backtest(v, tlt, COST, ANN, k)[0] for k, v in legs.items()}
    print("\n== per-leg, 2010-26 ==")
    for k, v in leg_net.items():
        s = rl.perf_stats(v.loc["2010":], ANN); print(f"  {k:36s} Sharpe {s['Sharpe']:.2f}  CAGR {s['CAGR']*100:.1f}%  t_NW {s['t_NW']:.2f}")

    # ---- cost / leverage table
    print("\n== cost sensitivity (full 2010-26 / OOS 2018-26 Sharpe) ==")
    for c in (0, 1, 2, 3, 5):
        n_, _ = rl.backtest(w, tlt, c, ANN); print(f"  {c} bp/side: {rl.perf_stats(n_.loc['2010':], ANN)['Sharpe']:.2f} / {rl.perf_stats(n_.loc['2018':], ANN)['Sharpe']:.2f}")

    full = net.loc["2010":]
    out = pd.DataFrame({"weight": w, "tlt_close": tlt, "net_ret": net, "tlt_ret": bh})
    out.to_parquet(os.path.join(ALPHA, "backtest_series.parquet"))
    out.loc["2010":, ["weight", "net_ret"]].to_csv(os.path.join(ALPHA, "weights_and_returns.csv"))

    # ---- figures
    eq = (1 + full).cumprod(); eqb = (1 + bh.loc["2010":]).cumprod()
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(eq.index, eq, color=C1, lw=2, label="treasury-flow-calendar (net, 2 bp)")
    ax.plot(eqb.index, eqb, color=C2, lw=2, label="TLT buy & hold")
    ax.axvline(pd.Timestamp("2018-01-01"), color=INK2, lw=0.8, ls="--"); ax.text(pd.Timestamp("2018-02-01"), eq.max() * 0.95, "OOS →", color=INK2)
    ax.set_yscale("log"); ax.set_title("Growth of $1, 2010–2026 (log scale)", loc="left", color=INK)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.1f")); ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.text(eq.index[-1], eq.iloc[-1], f"  {eq.iloc[-1]:.2f}", color=INK, va="center")
    ax.text(eqb.index[-1], eqb.iloc[-1], f"  {eqb.iloc[-1]:.2f}", color=INK, va="center")
    ax.legend(loc="upper left"); fig.tight_layout(); fig.savefig(os.path.join(ALPHA, "01_equity.png"), dpi=150); plt.close(fig)

    dd = eq / eq.cummax() - 1; ddb = eqb / eqb.cummax() - 1
    fig, ax = plt.subplots(figsize=(10, 3.2))
    ax.fill_between(dd.index, dd, 0, color=C1, alpha=0.35, lw=0); ax.plot(dd.index, dd, color=C1, lw=1.2, label="strategy")
    ax.plot(ddb.index, ddb, color=C2, lw=1.2, label="TLT buy & hold")
    ax.set_title("Drawdown from peak", loc="left"); ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.legend(loc="lower left"); fig.tight_layout(); fig.savefig(os.path.join(ALPHA, "02_drawdown.png"), dpi=150); plt.close(fig)

    yr = full.groupby(full.index.year); ys = yr.mean() / yr.std() * np.sqrt(ANN)
    fig, ax = plt.subplots(figsize=(10, 3.4))
    ax.bar(ys.index, ys.values, color=[C1 if v >= 0 else C2 for v in ys.values], width=0.7)
    ax.axhline(1.0, color=INK2, lw=0.8, ls="--"); ax.text(ys.index[0] - 0.4, 1.03, "Sharpe = 1", color=INK2, fontsize=9)
    for x, v in ys.items(): ax.text(x, v + (0.06 if v >= 0 else -0.18), f"{v:.1f}", ha="center", fontsize=8, color=INK)
    ax.set_title("Net Sharpe by calendar year (2 bp/side)", loc="left"); ax.grid(axis="x", visible=False)
    ax.set_xticks(list(ys.index)); ax.set_xticklabels([str(y) for y in ys.index], fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(ALPHA, "03_yearly_sharpe.png"), dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4))
    for (k, v), c in zip(leg_net.items(), (C1, C2, C3)):
        cum = v.loc["2010":].cumsum(); ax.plot(cum.index, cum, color=c, lw=2, label=k)
        ax.text(cum.index[-1], cum.iloc[-1], f"  {cum.iloc[-1]*100:.0f}%", color=INK, va="center", fontsize=9)
    ax.set_title("Cumulative net return by leg (simple sum, 2010–2026)", loc="left")
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0)); ax.legend(loc="upper left")
    fig.tight_layout(); fig.savefig(os.path.join(ALPHA, "04_leg_attribution.png"), dpi=150); plt.close(fig)

    # weight over a sample year
    ws = w.loc["2025-01-01":"2025-06-30"]
    fig, ax = plt.subplots(figsize=(10, 2.6))
    ax.step(ws.index, ws.values, where="post", color=C1, lw=1.5)
    ax.fill_between(ws.index, ws.values, 0, step="post", color=C1, alpha=0.25, lw=0)
    ax.set_title("Target weight, Jan–Jun 2025 (+1 long, −1 short, 0 flat)", loc="left"); ax.set_ylim(-1.2, 1.2)
    fig.tight_layout(); fig.savefig(os.path.join(ALPHA, "05_weight_sample.png"), dpi=150); plt.close(fig)
    print("\nfigures written to", ALPHA)


if __name__ == "__main__":
    main()
