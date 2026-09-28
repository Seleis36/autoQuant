"""Final numbers from the exact spec in strategy.py, truncation (look-ahead) test, P3 overlay,
figures and equity CSV for alphas/spot-btc/perp-crowding/."""
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
ALPHA = os.path.join(REPO, "alphas", "spot-btc", "perp-crowding")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_daily, btc_hourly, evaluate  # noqa: E402
import research_lib as rl  # noqa: E402
from exp01_screen import MET  # noqa: E402
import strategy as S  # noqa: E402

START = "2021-03-01"
HPY = 365 * 24


def main():
    os.makedirs(ALPHA, exist_ok=True)
    d = btc_daily()
    close = d.Close
    ls = pd.read_parquet(MET)["count_long_short_ratio"]
    w1 = S.target_weight(close, ls)
    w2 = S.target_weight(close, ls, trend_sma=50)
    r = close.pct_change()
    vs = rl.vol_target_scalar(r, target=0.40, halflife=20, cap=1.0)
    trend = (close > close.rolling(50).mean()).astype(float)
    rows, nets = [], {}
    for nm, w in (("P1 perp-crowding (spec)", w1), ("P2 + SMA50 gate", w2), ("vol-scaled B&H", vs), ("SMA50 x vol", trend * vs)):
        nets[nm], st = evaluate(w, close, start=START, name=nm)
        x = nets[nm].loc[START:]
        st["Sortino"] = rl.perf_stats(x)["Sortino"]
        rows.append(st)
    for c in (0.0, 5.0, 20.0, 30.0):
        _, st = evaluate(w1, close, start=START, cost_bps=c, name=f"P1 @{c:g}bp"); rows.append(st)
    res = pd.concat(rows)
    pd.set_option("display.width", 200)
    print(res.round(3).to_string())
    res.to_csv(os.path.join(HERE, "exp08_final.csv"))
    g = nets["P1 perp-crowding (spec)"].loc[START:]
    gy = g.groupby(g.index.year)
    print("P1 yearly Sharpe:", (gy.mean() / gy.std() * np.sqrt(365)).round(2).to_dict(),
          "| yearly return:", ((1 + g).groupby(g.index.year).prod() - 1).round(3).to_dict())
    print("trades (side changes of the on/off state)/yr:",
          round((w1 > 0).astype(int).diff().abs().loc[START:].sum() / (len(g) / 365), 1),
          "| avg holding spell (days):", round((w1.loc[START:] > 0).sum() / max(1, (w1 > 0).astype(int).diff().clip(lower=0).loc[START:].sum()), 1))
    print("current state:", w1.dropna().tail(5).round(3).to_dict())

    # truncation test: weights computed on data cut at T must equal the full-run weights up to T
    for T in ("2022-06-30", "2024-03-15", "2025-11-01"):
        wt = S.target_weight(close.loc[:T], ls.loc[:pd.Timestamp(T) + pd.Timedelta(days=1)])
        diff = (wt - w1.reindex(wt.index)).abs().max()
        print(f"truncation at {T}: max |w_trunc - w_full| = {diff:.2e}")

    # P3: coinbase-premium live spec AND P1's state (hourly)
    spec = importlib.util.spec_from_file_location("cbp", os.path.join(REPO, "code", "spot-btc", "coinbase-premium", "strategy.py"))
    cbp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cbp)
    hc = btc_hourly().Close
    cbc = pd.read_parquet(os.path.join(REPO, "data", "COINBASE_BTCUSD_1h.parquet"))["Close"].reindex(hc.index).ffill(limit=3)
    wc = cbp.target_weight(hc, cbc)
    on = (w1 > 0).astype(float)
    on.index = on.index + pd.Timedelta(days=1) - pd.Timedelta(hours=1)
    on_h = on.reindex(hc.index, method="ffill").fillna(0)
    for nm, w in (("coinbase-premium live", wc), ("P3 coinbase-premium AND not-crowded", wc * on_h)):
        n, _ = rl.backtest(w, hc, cost_bps=10, ann=HPY)
        n = n.loc[START:]
        eq = (1 + n).cumprod()
        f = lambda s: s.mean() / s.std() * np.sqrt(HPY)  # noqa: E731
        print(f"{nm}: full {f(n):.2f} IS {f(n.loc[:'2022-12-31']):.2f} OOS {f(n.loc['2023-01-01':]):.2f} "
              f"CAGR {eq.iloc[-1] ** (HPY / len(n)) - 1:.3f} MaxDD {(eq / eq.cummax() - 1).min():.3f}")

    # equity CSV + figure
    eqs = pd.DataFrame({k: (1 + v.loc[START:]).cumprod() for k, v in nets.items()})
    eqs.to_csv(os.path.join(ALPHA, "equity.csv"), float_format="%.6f")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cols = {"P1 perp-crowding (spec)": "#2a78d6", "P2 + SMA50 gate": "#eb6834", "SMA50 x vol": "#1baf7a", "vol-scaled B&H": "#eda100"}
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True, gridspec_kw={"height_ratios": [3, 1.2], "hspace": 0.08})
    fig.patch.set_facecolor("#fcfcfb")
    for a in (ax, ax2):
        a.set_facecolor("#fcfcfb")
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            a.spines[s].set_color("#bdbcb6")
        a.tick_params(colors="#52514e", labelsize=9)
        a.grid(axis="y", color="#e7e6e1", lw=0.8)
    for k, c in cols.items():
        ax.plot(eqs.index, eqs[k], color=c, lw=2, label=k)
        ax.annotate(f"{k}  {eqs[k].iloc[-1]:.2f}x", (eqs.index[-1], eqs[k].iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=8.5, color="#0b0b0b")
    ax.axvline(pd.Timestamp("2023-01-01"), color="#8a8984", lw=1, ls="--")
    ax.text(pd.Timestamp("2023-01-10"), eqs.max().max() * 0.95, "out-of-sample →",
            fontsize=9, color="#52514e", va="top")
    ax.set_yscale("log")
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter
    ax.yaxis.set_major_locator(FixedLocator([0.5, 0.75, 1, 1.5, 2, 3, 4, 6]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}x"))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_ylabel("growth of 1 (log), net of 10 bp/side", color="#52514e", fontsize=9)
    ax.set_title("perp-crowding: long spot BTC only while Binance's retail long/short account ratio is below its historical median",
                 fontsize=10.5, color="#0b0b0b", loc="left")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    rk = S.expanding_rank(S.crowd_level(ls, close.index)).loc[START:]
    ax2.plot(rk.index, rk, color="#2a78d6", lw=1.2)
    ax2.axhline(0.5, color="#52514e", lw=1)
    ax2.fill_between(rk.index, 0, 1, where=rk < 0.5, color="#2a78d6", alpha=0.10, lw=0)
    ax2.set_ylim(0, 1)
    ax2.set_ylabel("crowd rank\n(shaded = hold)", color="#52514e", fontsize=9)
    fig.subplots_adjust(right=0.80, left=0.08, top=0.93, bottom=0.06)
    fig.savefig(os.path.join(ALPHA, "equity.png"), dpi=130, facecolor=fig.get_facecolor())
    print("wrote", os.path.join(ALPHA, "equity.png"))


if __name__ == "__main__":
    main()
