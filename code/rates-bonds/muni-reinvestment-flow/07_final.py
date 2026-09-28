"""muni-reinvestment-flow -- final validation of strategy.py.

1. Backtest strategy.target_weights with research_lib.backtest_xs (weights shifted one bar,
   cost on sum |dw|), 2 bp/side, ann = 252: 2008-2016 / 2017-2026 / full, per year.
2. Cost ladder 0-5 bp; sensitivities fixed in advance: n_days 3 / 7, 5-ETF basket incl. HYD,
   MUB-only.
3. Lookahead: truncation test -- weights computed on data cut at every month's last two and
   first two sessions of 2019-2026 must equal the full-run weights on the cut date.
4. Relation to the deployed rates sleeve (treasury-flow-calendar): correlation and blend.
5. Deflated Sharpe over the configurations tried for this short name.
6. Figures + series into alphas/rates-bonds/muni-reinvestment-flow/.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
import strategy as S  # noqa: E402
from rb_data import etf_close, rl  # noqa: E402

pd.set_option("display.width", 220)
ANN = 252.0
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
ALPHA = os.path.join(ROOT, "alphas", "rates-bonds", "muni-reinvestment-flow")
os.makedirs(ALPHA, exist_ok=True)
SPLITS = {"2008-16": ("2008", "2016"), "2017-26": ("2017", "2026"), "full 08-26": ("2008", "2026")}


def bt(w, px, cost):
    net, st = rl.backtest_xs(w, px[w.columns], cost_bps=cost, ann=ANN)
    return net.loc["2008":], st


def summary(net):
    out = {}
    for k, (a, b) in SPLITS.items():
        s = rl.perf_stats(net.loc[a:b], ann=ANN)
        out[k] = s[["Sharpe", "CAGR", "Vol", "MaxDD", "t_NW"]]
    return pd.DataFrame(out).T


def main():
    px = etf_close(S.TICKERS + ["HYD"])
    px = px.loc["2007-01-01":]
    w = S.target_weights(px[S.TICKERS])
    net, st = bt(w, px, 2.0)
    print("=== PRIMARY: 4-ETF basket, first 5 sessions, beta-hedged, 2 bp/side ===")
    print(summary(net).round(3).to_string())
    turn = (w.shift(1).fillna(0) - w.shift(2).fillna(0)).abs().sum(axis=1).loc["2008":]
    expo = (w.shift(1).fillna(0).abs().sum(axis=1) > 0).loc["2008":]
    print(f"annual turnover {turn.mean() * ANN:.1f}x, share of sessions held {expo.mean():.3f}, "
          f"avg gross when held {w.shift(1).abs().sum(axis=1).loc['2008':][expo].mean():.2f}, "
          f"avg muni notional when held {w.shift(1)[['MUB','TFI','ITM','SHM']].sum(axis=1).loc['2008':][expo].mean():.2f}, "
          f"avg hedge notional {-w.shift(1)[['IEF','SHY']].sum(axis=1).loc['2008':][expo].mean():.2f}")
    py = net.groupby(net.index.year).apply(lambda x: pd.Series({"sharpe": x.mean() / x.std() * np.sqrt(ANN),
                                                               "ret_pct": ((1 + x).prod() - 1) * 100}))
    py = py.unstack()
    print("\nper year:"); print(py.round(2).T.to_string())

    print("\n=== cost ladder (Sharpe) ===")
    rows = {}
    for c in (0, 0.5, 1, 2, 3, 5):
        n, _ = bt(w, px, c)
        rows[f"{c} bp"] = summary(n)["Sharpe"]
    print(pd.DataFrame(rows).round(2).to_string())

    print("\n=== sensitivities, 2 bp (Sharpe) ===")
    sens = {}
    for lab, kw, cols in (("n_days=3", dict(n_days=3), S.TICKERS), ("n_days=7", dict(n_days=7), S.TICKERS),
                          ("5-ETF incl. HYD", dict(pairs={**S.PAIRS, "HYD": "IEF"}), S.TICKERS + ["HYD"]),
                          ("MUB only", dict(pairs={"MUB": "IEF"}), ["MUB", "IEF"])):
        ww = S.target_weights(px[cols], **kw)
        n, _ = bt(ww, px, 2.0)
        sens[lab] = summary(n)["Sharpe"]
    print(pd.DataFrame(sens).round(2).to_string())

    # 3. truncation test
    idx = px.index
    cuts = []
    for per, g in pd.Series(idx, index=idx).loc["2019":"2026-08"].groupby(idx[(idx >= "2019") & (idx < "2026-09")].to_period("M")):
        cuts += list(g.iloc[:2]) + list(g.iloc[-2:])
    bad = 0
    for c in cuts:
        wt = S.target_weights(px[S.TICKERS].loc[:c]).iloc[-1]
        if not np.allclose(wt.values, w.loc[c, wt.index].values, atol=1e-12):
            bad += 1
            print("  MISMATCH at", c.date(), wt.round(4).to_dict(), w.loc[c].round(4).to_dict())
    print(f"\ntruncation test: {len(cuts)} cut dates (first 2 / last 2 sessions of each month 2019-2026), mismatches: {bad}")

    # 4. relation to treasury-flow-calendar
    tfc = pd.read_parquet(os.path.join(ROOT, "alphas", "rates-bonds", "treasury-flow-calendar", "backtest_series.parquet"))["net_ret"]
    tfc.index = pd.to_datetime(tfc.index)
    j = pd.concat([net.rename("muni"), tfc.rename("tfc")], axis=1).dropna()
    print(f"\ncorr with treasury-flow-calendar: daily {j.corr().iloc[0, 1]:.3f}, "
          f"weekly {j.resample('W').sum().corr().iloc[0, 1]:.3f}, monthly {j.resample('ME').sum().corr().iloc[0, 1]:.3f}")
    vm, vt = j.muni.std(), j.tfc.std()
    for lab, k in (("tfc alone", 0.0), ("tfc + muni at equal risk", vt / vm), ("tfc + muni at half risk", 0.5 * vt / vm)):
        b = j.tfc + k * j.muni
        print(f"  {lab:28s} (muni scale {k:4.1f}x): Sharpe full {b.mean()/b.std()*np.sqrt(ANN):.2f}, "
              f"2017-26 {b.loc['2017':].mean()/b.loc['2017':].std()*np.sqrt(ANN):.2f}")

    # 5. deflated Sharpe: book configurations tried under this short name
    n_trials = 5 + 30 + 4 + 6       # seasonal books, 05 grid (5 instr x 3 windows x 2 hedge), 07 sensitivities, cost cells
    s = rl.perf_stats(net, ann=ANN)
    dsr = rl.deflated_sharpe(s["Sharpe"], s["N"], n_trials, skew=s["Skew"], kurt=s["Kurt"] + 3, ann=ANN)
    print(f"\ndeflated Sharpe probability (full 2008-26, {n_trials} trials): {dsr:.3f}")

    # 6. save + figures
    out = pd.DataFrame({"net_ret_2bp": net, "gross_ret": bt(w, px, 0.0)[0]})
    out.to_parquet(os.path.join(ALPHA, "backtest_series.parquet"))
    w.loc["2008":].to_parquet(os.path.join(ALPHA, "weights.parquet"))
    figures(net, out.gross_ret, py)


def figures(net, gross, py):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ink, ink2, grid, surf = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
    blue, orange, aqua = "#2a78d6", "#eb6834", "#1baf7a"
    plt.rcParams.update({"axes.edgecolor": grid, "axes.labelcolor": ink2, "xtick.color": ink2,
                         "ytick.color": ink2, "text.color": ink, "axes.facecolor": surf,
                         "figure.facecolor": surf, "font.size": 10})
    # 1 equity curve (one axis), gross and net
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for s, c, lab in ((gross, aqua, "gross"), (net, blue, "net of 2 bp/side")):
        eq = (1 + s).cumprod() - 1
        ax.plot(eq.index, eq * 100, color=c, lw=2, label=lab)
    ax.axvline(pd.Timestamp("2017-01-01"), color=ink2, lw=1, ls="--")
    ax.text(pd.Timestamp("2017-02-01"), ax.get_ylim()[1] * 0.92, "2017-: effect visible in ETF prices", color=ink2, fontsize=9)
    ax.set_ylabel("cumulative return, % (1x muni notional)")
    ax.set_title("Muni month-start book: long 4 muni ETFs / short beta x Treasuries, first 5 sessions", loc="left", fontsize=11)
    ax.grid(axis="y", color=grid, lw=0.8); ax.legend(frameon=False, loc="upper left")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout(); fig.savefig(os.path.join(ALPHA, "01_equity_curve.png"), dpi=130); plt.close(fig)
    # 2 per-year Sharpe bars
    fig, ax = plt.subplots(figsize=(9, 3.6))
    sh = py["sharpe"]
    ax.bar(sh.index.astype(str), sh.values, color=[blue if v >= 0 else orange for v in sh.values], width=0.7)
    ax.axhline(0, color=ink2, lw=1)
    ax.set_ylabel("net Sharpe (2 bp/side)")
    ax.set_title("Per-year net Sharpe", loc="left", fontsize=11)
    ax.grid(axis="y", color=grid, lw=0.8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout(); fig.savefig(os.path.join(ALPHA, "02_per_year_sharpe.png"), dpi=130); plt.close(fig)
    # 3 NAV holdout by era (from 03_nav_holdout.csv)
    t = pd.read_csv(os.path.join(_HERE, "03_nav_holdout.csv"))
    m = t.groupby("window").D_bp.mean().reindex(["1990-99", "2000-07", "2008-16", "2017-26"])
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(m.index, m.values, color=blue, width=0.6)
    for i, v in enumerate(m.values):
        ax.text(i, v + 0.3, f"{v:.1f}", ha="center", color=ink, fontsize=9)
    ax.set_ylabel("bp per month")
    ax.set_title("Muni fund NAVs: first-5-session excess over the rest of the month\n(six funds, hedged price return; 1990-2016 not used for discovery)", loc="left", fontsize=10)
    ax.grid(axis="y", color=grid, lw=0.8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout(); fig.savefig(os.path.join(ALPHA, "03_nav_holdout_by_era.png"), dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
