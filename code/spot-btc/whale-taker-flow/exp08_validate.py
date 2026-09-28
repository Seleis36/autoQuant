"""Validation of the two whale-flow candidates.

S1  standalone:        whale state (LmS 24 h, z 720 h, enter 0 / exit -1) x inv-vol
S2  premium AND whale: coinbase-premium state (0 / -1.5) x whale state (0 / -1.5) x SMA1200h x inv-vol

1. timing probe: whale z delayed +1/+2 bars (legal) and advanced 1 bar (illegal)
2. strict walk-forward of S1's 30-config grid (expanding, re-selected every January, 2020-2026)
3. neighbourhood of S2 (whale window x whale exit) -- plateau or peak?
4. size-bucket robustness: large = >=$1M only / >=$10k; small = <$1k / <$10k
5. cost sensitivity; yearly Sharpe; daily block bootstrap; circular-shift placebo on whale z
6. vectorbt from_orders cross-check of S2
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_hourly  # noqa: E402
import research_lib as rl  # noqa: E402
from exp01_screen import FLOW  # noqa: E402
from exp05_hourly_state import HPY, IS, OOS, hysteresis, stats  # noqa: E402
from exp06_blend import load_cbp  # noqa: E402

rng = np.random.default_rng(7)


def groups(h, large, small):
    return pd.DataFrame({"buy_L": sum(h[f"buy_b{b}"] for b in large), "sell_L": sum(h[f"sell_b{b}"] for b in large),
                         "buy_S": sum(h[f"buy_b{b}"] for b in small), "sell_S": sum(h[f"sell_b{b}"] for b in small)})


def whale_z(fl, W=24, zwin=720):
    s = fl.rolling(W, min_periods=int(W * 0.8)).sum()
    x = (s.buy_L - s.sell_L) / (s.buy_L + s.sell_L) - (s.buy_S - s.sell_S) / (s.buy_S + s.sell_S)
    return (x - x.rolling(zwin, min_periods=zwin // 2).mean()) / x.rolling(zwin, min_periods=zwin // 2).std()


def sh(net, a, b):
    s = net.loc[a:b]
    return s.mean() / s.std() * np.sqrt(HPY)


def main():
    h = btc_hourly().loc[:OOS[1]]
    close = h.Close
    raw = pd.read_parquet(FLOW).reindex(close.index)
    fl = groups(raw, [3, 4], [0])
    r = close.pct_change()
    ewv = r.ewm(halflife=480, min_periods=480).std() * np.sqrt(HPY)
    vs = (0.40 / ewv).clip(0, 1).fillna(0)
    trend = (close > close.rolling(1200).mean()).astype(float)
    cbp = load_cbp()
    cbc = pd.read_parquet(os.path.join(REPO, "data", "COINBASE_BTCUSD_1h.parquet"))["Close"].reindex(close.index).ffill(limit=3)
    sp = cbp.hysteresis_state(cbp.premium_zscore(close, cbc, 720), 0.0, -1.5)
    zw = whale_z(fl)

    def S1(z):
        return hysteresis(z, 0.0, -1.0) * vs

    def S2(z, ex=-1.5):
        return sp * hysteresis(z, 0.0, ex) * trend * vs

    out = []

    def rec(name, w, cost=10.0):
        net, st = stats(w, close, cost)
        out.append(pd.Series(st, name=name))
        return net

    n1 = rec("S1 whale standalone", S1(zw))
    n2 = rec("S2 premium AND whale", S2(zw))
    nc = rec("cbprem live spec", sp * trend * vs)
    nb = rec("vol B&H", vs)
    # 1. timing probe
    for k in (1, 2, -1):
        rec(f"S1 whale z shifted {k:+d} ({'legal' if k > 0 else 'ILLEGAL'})", S1(zw.shift(k)))
        rec(f"S2 whale z shifted {k:+d} ({'legal' if k > 0 else 'ILLEGAL'})", S2(zw.shift(k)))
    # 3. S2 neighbourhood
    for W in (12, 24, 48, 72, 168):
        for ex in (-1.0, -1.5, -2.0):
            rec(f"S2 nbhd W{W} exit{ex}", S2(whale_z(fl, W), ex))
    # 4. bucket robustness
    for lab, L, S in (("L>=1M", [4], [0]), ("L>=10k", [2, 3, 4], [0]), ("S<10k", [3, 4], [0, 1]), ("L>=1M,S<10k", [4], [0, 1])):
        z = whale_z(groups(raw, L, S))
        rec(f"S1 buckets {lab}", S1(z))
        rec(f"S2 buckets {lab}", S2(z))
    # 5. costs
    for c in (0.0, 3.0, 5.0, 20.0):
        rec(f"S1 @{c:g}bp", S1(zw), c)
        rec(f"S2 @{c:g}bp", S2(zw), c)
    res = pd.DataFrame(out)
    pd.set_option("display.width", 220)
    print(res.round(2).to_string())
    res.to_csv(os.path.join(HERE, "exp08_validate.csv"))

    # yearly
    yr = pd.DataFrame({k: n.loc[IS[0]:OOS[1]] for k, n in (("S1", n1), ("S2", n2), ("cbprem", nc), ("volB&H", nb))})
    g = yr.groupby(yr.index.year)
    print("\nyearly Sharpe:\n", (g.mean() / g.std() * np.sqrt(HPY)).round(2).T.to_string())

    # 2. walk-forward of S1's grid (30 configs of exp05), re-selected each January
    grid = {}
    for W in (24, 72, 168):
        z = whale_z(fl, W)
        for e, x in ((0, 0), (0, -1), (0.5, -0.5), (1, -1), (0, -1.5)):
            st_ = hysteresis(z, e, x)
            for tr in ("none", "sma"):
                w = st_ * vs * (trend if tr == "sma" else 1.0)
                grid[(W, e, x, tr)], _ = stats(w, close)
    wf = []
    picks = {}
    for y in range(2020, 2027):
        train_end = f"{y - 1}-12-31"
        best = max(grid, key=lambda k: sh(grid[k], IS[0], train_end))
        picks[y] = best
        wf.append(grid[best].loc[f"{y}-01-01":min(f"{y}-12-31", OOS[1])])
    wfn = pd.concat(wf)
    print("\nwalk-forward picks:", picks)
    print("walk-forward S1-grid Sharpe 2020-2026:", round(wfn.mean() / wfn.std() * np.sqrt(HPY), 2),
          "| 2023+:", round(sh(wfn, OOS[0], OOS[1]), 2),
          "| vol B&H same span:", round(sh(nb, "2020-01-01", OOS[1]), 2),
          "| cbprem same span:", round(sh(nc, "2020-01-01", OOS[1]), 2))

    # 5b. daily block bootstrap (21-day blocks) of full-sample Sharpe
    for nm, n in (("S1", n1), ("S2", n2), ("cbprem", nc)):
        d = n.loc[IS[0]:OOS[1]].resample("1D").sum()
        vals = d.values
        B, L = 2000, 21
        nb_ = int(np.ceil(len(vals) / L))
        shs = []
        for _ in range(B):
            idx = np.concatenate([np.arange(s, s + L) for s in rng.integers(0, len(vals) - L, nb_)])[:len(vals)]
            x = vals[idx]
            shs.append(x.mean() / x.std() * np.sqrt(365))
        shs = np.array(shs)
        print(f"bootstrap {nm}: median {np.median(shs):.2f}  5-95% [{np.percentile(shs, 5):.2f}, {np.percentile(shs, 95):.2f}]"
              f"  P(Sh>1) {np.mean(shs > 1):.2f}")
    # 5c. circular-shift placebo on whale z (shift >= 60 days)
    pl1, pl2 = [], []
    zv = zw.values
    for _ in range(200):
        k = int(rng.integers(60 * 24, len(zv) - 60 * 24))
        zs = pd.Series(np.roll(zv, k), index=zw.index)
        a, _ = stats(S1(zs), close)
        b, _ = stats(S2(zs), close)
        pl1.append(sh(a, IS[0], OOS[1]))
        pl2.append(sh(b, IS[0], OOS[1]))
    for nm, pl, real in (("S1", pl1, sh(n1, IS[0], OOS[1])), ("S2", pl2, sh(n2, IS[0], OOS[1]))):
        pl = np.array(pl)
        print(f"placebo {nm}: real {real:.2f} | placebo mean {pl.mean():.2f} sd {pl.std():.2f} max {pl.max():.2f} "
              f"| p = {np.mean(pl >= real):.3f}")
    # deflated Sharpe (daily P&L), trials counted across the whole whale study
    for nm, n, trials in (("S1", n1, 60), ("S2", n2, 60)):
        d = n.loc[IS[0]:OOS[1]].resample("1D").sum()
        s_ann = d.mean() / d.std() * np.sqrt(365)
        print(f"DSR {nm}: SR {s_ann:.2f}  P(true SR>0 | {trials} trials) = "
              f"{rl.deflated_sharpe(s_ann, len(d), trials, d.skew(), d.kurt() + 3, ann=365):.3f}")

    # 6. vectorbt cross-check of S2
    import vectorbt as vbt
    w2 = S2(zw).loc[IS[0]:OOS[1]]
    px = close.loc[IS[0]:OOS[1]]
    size = w2.shift(1).fillna(0)          # weight decided at close t is held over bar t+1
    pf = vbt.Portfolio.from_orders(px, size=size, size_type="targetpercent", fees=0.001, freq="1h",
                                   init_cash=1e6, cash_sharing=True)
    vr = pf.returns()
    cr = n2.loc[IS[0]:OOS[1]]
    print(f"vectorbt S2: Sharpe {vr.mean() / vr.std() * np.sqrt(HPY):.3f} vs custom {cr.mean() / cr.std() * np.sqrt(HPY):.3f}"
          f"  corr {vr.corr(cr):.4f}  total return vbt {pf.total_return():.2f}")


if __name__ == "__main__":
    main()
