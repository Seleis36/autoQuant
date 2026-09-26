"""cot-positioning -- final evaluation of strategy.target_weights (the deployable function).

  1. Equality with the research book 03_composite C.
  2. Truncation test: weights computed on data cut at T (prices AND COT reports released
     after T removed) must equal the full-run weights at T, for 40 random cut dates.
  3. Headline stats (measured costs), cost ladder, per-year, OOS block bootstrap,
     deflated Sharpe for the number of configurations tried in this idea.
  4. Figures into alphas/fx-majors/cot-positioning/.
"""
import os
import sys
import importlib

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, HERE)
from fx_panel import ANN, backtest, cost_frame, load_px, split_table, TICKERS  # noqa: E402
from research_lib import perf_stats, deflated_sharpe  # noqa: E402
import strategy  # noqa: E402
c3 = importlib.import_module("03_composite")

OUT = os.path.join(REPO, "alphas", "fx-majors", "cot-positioning")
N_TRIALS = 20 + 24 + 4 + 25 + 2      # 01 + 02 + 03 + 04 (+ Tuesday row, H.10) configurations


def main():
    os.makedirs(OUT, exist_ok=True)
    px_raw, lg, tf = strategy.load_inputs()
    px = load_px()
    W = strategy.target_weights(px_raw, lg, tf).reindex(px.index).fillna(0.0)
    Wc3 = pd.read_parquet(os.path.join(HERE, "03_composite_weights.parquet"))["C_CP_all"]
    # 03 is in currency space; convert for the comparison
    from fx_panel import to_tickers
    diff = (W - to_tickers(Wc3).reindex(W.index)).abs().max().max()
    print(f"max |strategy - 03 C| weight difference: {diff:.2e}")

    # 2. truncation test
    rng = np.random.default_rng(7)
    cuts = sorted(rng.choice(px_raw.loc["2012":].index, size=40, replace=False))
    worst = 0.0
    for T in cuts:
        T = pd.Timestamp(T)
        lgT = lg[lg["avail_utc"] < T]
        tfT = tf[tf["avail_utc"] < T]
        WT = strategy.target_weights(px_raw.loc[:T], lgT, tfT)
        worst = max(worst, (WT.iloc[-1] - strategy.target_weights(px_raw, lg, tf).loc[T]).abs().max())
    print(f"truncation test, 40 cut dates: max |w_trunc(T) - w_full(T)| = {worst:.2e}")

    # 3. headline
    net, gross, turn, st = backtest(to_currency(W), px, cost=None, name="cot-positioning")
    tab = split_table(net)
    print(tab.round(3).to_string())
    print(st[["Sharpe", "CAGR", "Vol", "MaxDD", "Calmar", "t_NW", "Turnover_ann", "AvgGross", "CostDrag_bp"]].round(3).to_string())
    ladder = {}
    for lab, c in (("0bp", 0.0), ("measured", None), ("measured x2", cost_frame(px.index, mult=2)),
                   ("measured x3", cost_frame(px.index, mult=3)), ("flat 1bp", 1.0), ("flat 2bp", 2.0)):
        n, *_ = backtest(to_currency(W), px, cost=c)
        ladder[lab] = {"FULL": perf_stats(n, ann=ANN)["Sharpe"], "OOS": perf_stats(n.loc["2020":], ann=ANN)["Sharpe"]}
    print("cost ladder:", pd.DataFrame(ladder).round(2).to_string())
    yr = net.groupby(net.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(ANN))
    yr_ret = net.groupby(net.index.year).sum()
    print("per-year Sharpe:", yr.round(2).to_dict())
    bs = c3.block_boot(net.loc["2020":].values, n=5000)
    print(f"OOS block bootstrap: mean {bs.mean():.2f} 5-95% [{np.percentile(bs,5):.2f},{np.percentile(bs,95):.2f}] P>0 {np.mean(bs>0):.3f}")
    s = perf_stats(net, ann=ANN)
    dsr = deflated_sharpe(s["Sharpe"], len(net), N_TRIALS, skew=s["Skew"], kurt=s["Kurt"] + 3, ann=ANN)
    print(f"deflated Sharpe probability (N={N_TRIALS} trials): {dsr:.3f}")
    # carry a forward book would have added (policy-rate differentials; NOT in the sim book)
    from fx_panel import carry_return
    from macro_data import short_rates
    _, _, _, stc = backtest(to_currency(W), px, cost=None, carry=carry_return(short_rates(), px.index))
    print(f"carry (reporting only): {stc['Carry_ann']*1e4:.0f} bp/yr; Sharpe incl. carry {stc['Sharpe_w_carry']:.2f}")
    # exposure
    g = W.abs().sum(axis=1)
    print(f"gross: mean {g.mean():.2f} max {g.max():.2f}; per-ticker max |w|: {W.abs().max().round(2).to_dict()}")
    pd.DataFrame({"net": net, "gross": gross}).to_parquet(os.path.join(HERE, "05_final_returns.parquet"))
    pd.DataFrame(ladder).to_csv(os.path.join(HERE, "05_cost_ladder.csv"))

    # 4. figures
    eq = (1 + net).cumprod()
    fig, ax = plt.subplots(3, 1, figsize=(10, 9), gridspec_kw={"height_ratios": [3, 1.2, 1.6]})
    ax[0].plot(eq.index, eq.values, color="#1f4e79", lw=1.4, label="net (measured 00:00 UTC half-spread)")
    ax[0].plot((1 + gross).cumprod(), color="#9dc3e6", lw=1.0, label="gross")
    ax[0].axvline(pd.Timestamp("2020-01-01"), color="grey", ls="--", lw=0.8)
    ax[0].text(pd.Timestamp("2020-02-01"), eq.max() * 0.98, "OOS →", color="grey")
    ax[0].set_title(f"cot-positioning: net Sharpe {tab.loc['FULL','Sharpe']:.2f} full / {tab.loc['IS','Sharpe']:.2f} IS / {tab.loc['OOS','Sharpe']:.2f} OOS, 5% vol target")
    ax[0].legend(loc="upper left", frameon=False)
    dd = eq / eq.cummax() - 1
    ax[1].fill_between(dd.index, dd.values, 0, color="#c00000", alpha=0.5)
    ax[1].set_ylabel("drawdown")
    ax[2].bar(yr_ret.index, yr_ret.values * 100, color=["#1f4e79" if v > 0 else "#c00000" for v in yr_ret.values])
    ax[2].set_ylabel("net return % / yr")
    ax[2].set_xticks(list(yr_ret.index[::2]))
    for a in ax:
        a.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "equity_drawdown.png"), dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4))
    Wc = to_currency(W).loc["2024":]
    for c in Wc:
        ax.plot(Wc.index, Wc[c], lw=0.9, label=c)
    ax.set_title("currency-space weights since 2024 (positive = long ccy / short USD); sum = 0 each row")
    ax.legend(ncol=7, frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "weights_recent.png"), dpi=120)
    plt.close(fig)


def to_currency(Wt):
    from fx_panel import TICKER, CCYS
    return pd.DataFrame({c: TICKER[c][1] * Wt[TICKER[c][0]] for c in CCYS})


if __name__ == "__main__":
    main()
