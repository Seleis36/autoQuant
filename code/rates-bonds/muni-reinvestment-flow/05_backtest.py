"""muni-reinvestment-flow -- the tradable book: long muni ETF / short beta x Treasury ETF over the
first 5 trading days of every month.

Rule (window fixed by the NAV holdout statistic in 03, before any book was run):
  at the close of the LAST trading day of month m-1, go long 1.0 muni ETF and short b x hedge ETF
  (b = trailing 252-day OLS beta of the muni ETF's daily return on the hedge ETF's, known at that
  close); hold through the close of trading day 5 of month m; flat otherwise.
Primary: MUB vs IEF. Also TFI / ITM vs IEF, SHM vs SHY, and an equal-weight basket of the four.
Sensitivity: window 3 / 5 / 7 days; unhedged muni leg; cost 0-5 bp/side on both legs.
Primary cost: 2 bp/side on both legs (MUB / IEF quoted spreads are ~1 bp; muni ETFs at ~$46
(TFI/ITM/SHM) quote ~2 bp, so 2 bp/side is ~2x their half-spread).
Windows: 2008-2016 (ETF effect absent), 2017-2026 (discovery sample), per year.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from rb_data import etf_close, ANN  # noqa: E402

pd.set_option("display.width", 220)
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
PAIRS = {"MUB": "IEF", "TFI": "IEF", "ITM": "IEF", "SHM": "SHY"}


def window_mask(idx, n):
    s = pd.Series(np.arange(len(idx)), index=idx)
    per = idx.to_period("M")
    day = s - s.groupby(per).transform("min") + 1
    return day <= n


def pair_weights(r, muni, hedge, n=5, hedged=True):
    """Target weights at each close (decided at that close, applied to the next day's return)."""
    idx = r.index
    beta = (r[muni].rolling(252, min_periods=126).cov(r[hedge]) / r[hedge].rolling(252, min_periods=126).var())
    held = window_mask(idx, n)                       # days whose RETURN we want to hold
    decide = held.shift(-1, fill_value=False)        # weight set at the prior close
    w = pd.DataFrame(0.0, index=idx, columns=[muni, hedge])
    w.loc[decide, muni] = 1.0
    if hedged:
        w.loc[decide, hedge] = -beta[decide]
    return w.fillna(0.0), beta


def run(w, r, cost_bp):
    we = w.shift(1).fillna(0.0)
    gross = (we * r[w.columns].fillna(0)).sum(axis=1)
    turn = (we - we.shift(1).fillna(0)).abs().sum(axis=1)
    return gross - turn * cost_bp / 1e4, turn


def stats(x):
    x = x.dropna()
    if len(x) < 50 or x.std() == 0:
        return dict(sharpe=np.nan)
    eq = (1 + x).cumprod()
    return dict(sharpe=x.mean() / x.std() * np.sqrt(ANN), ann_ret=x.mean() * ANN * 100,
                vol=x.std() * np.sqrt(ANN) * 100, mdd=(eq / eq.cummax() - 1).min() * 100)


def main():
    px = etf_close(sorted(set(PAIRS) | set(PAIRS.values())))
    r = px.pct_change().loc["2008":]
    rows, nets = [], {}
    for n in (3, 5, 7):
        for hedged in (True, False):
            for cost in (0, 1, 2, 3, 5):
                ws = []
                for m, h in PAIRS.items():
                    w, beta = pair_weights(r, m, h, n, hedged)
                    net, turn = run(w, r, cost)
                    key = (m, n, hedged, cost)
                    nets[key] = net
                    ws.append(w)
                    for sp, (a, b) in {"08-16": ("2008", "2016"), "17-26": ("2017", "2026"), "full": ("2008", "2026")}.items():
                        rows.append(dict(inst=m, n=n, hedged=hedged, cost=cost, split=sp, **stats(net.loc[a:b]),
                                         turn_yr=turn.loc[a:b].mean() * ANN))
                wb = sum(x.reindex(columns=sorted(set(PAIRS) | set(PAIRS.values())), fill_value=0) for x in ws) / len(ws)
                net, turn = run(wb, r, cost)
                nets[("BASKET", n, hedged, cost)] = net
                for sp, (a, b) in {"08-16": ("2008", "2016"), "17-26": ("2017", "2026"), "full": ("2008", "2026")}.items():
                    rows.append(dict(inst="BASKET", n=n, hedged=hedged, cost=cost, split=sp, **stats(net.loc[a:b]),
                                     turn_yr=turn.loc[a:b].mean() * ANN))
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(_HERE, "05_backtest.csv"), index=False)
    prim = t[(t.n == 5) & (t.hedged) & (t.cost == 2)]
    print("=== primary: first 5 days, hedged, 2 bp/side ===")
    print(prim.drop(columns=["n", "hedged", "cost"]).round(2).to_string(index=False))
    print("\n=== Sharpe 2017-26 by window / hedge (2 bp) ===")
    print(t[(t.cost == 2) & (t.split == "17-26")].pivot_table(index="inst", columns=["hedged", "n"], values="sharpe").round(2).to_string())
    print("\n=== Sharpe 2008-16 by window / hedge (2 bp) ===")
    print(t[(t.cost == 2) & (t.split == "08-16")].pivot_table(index="inst", columns=["hedged", "n"], values="sharpe").round(2).to_string())
    print("\n=== cost ladder, 5d hedged, Sharpe 2017-26 / full ===")
    c = t[(t.n == 5) & (t.hedged)]
    print(c.pivot_table(index="inst", columns=["split", "cost"], values="sharpe")[["17-26", "full"]].round(2).to_string())
    print("\n=== per-year Sharpe, 5d hedged, 2 bp ===")
    py = {}
    for m in list(PAIRS) + ["BASKET"]:
        x = nets[(m, 5, True, 2)]
        py[m] = x.groupby(x.index.year).apply(lambda s: s.mean() / s.std() * np.sqrt(ANN) if s.std() > 0 else np.nan)
    print(pd.DataFrame(py).round(2).to_string())
    pd.DataFrame({f"{k[0]}_n{k[1]}_{'h' if k[2] else 'u'}_c{k[3]}": v for k, v in nets.items()
                  if k[1] == 5 and k[3] in (0, 2)}).to_parquet(os.path.join(_HERE, "05_nets.parquet"))
    # correlation with the deployed treasury-flow-calendar
    p = os.path.join(ROOT, "alphas", "rates-bonds", "treasury-flow-calendar", "backtest_series.parquet")
    if os.path.exists(p):
        tfc = pd.read_parquet(p)
        col = [c for c in tfc.columns if "net" in c.lower() or "ret" in c.lower()]
        s = tfc[col[0]] if col else tfc.iloc[:, 0]
        s.index = pd.to_datetime(s.index)
        for m in ("MUB", "BASKET"):
            x = nets[(m, 5, True, 2)]
            j = pd.concat([x, s], axis=1).dropna()
            print(f"\ncorr with treasury-flow-calendar ({col[:1]}), {m}: daily {j.corr().iloc[0, 1]:.3f}, "
                  f"monthly {j.resample('ME').sum().corr().iloc[0, 1]:.3f}")


if __name__ == "__main__":
    main()
