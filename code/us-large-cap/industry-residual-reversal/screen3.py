"""Screen 3: (b) vol-regime scaling of the reversal book; (c) extreme-move event study
(return per trade vs round-trip cost). No earnings data yet."""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
from panel import load_panel
from xs_lib import *
from research_lib import load_series

P = load_panel()
C, O, V, M = P["close"], P["open"], P["volume"], P["member"]
sec = P["sector"].fillna("UNK")
ret = C.pct_change(); logret = np.log(C).diff()
hist_ok = C.notna().rolling(60).sum().ge(55)
mask = M & hist_ok & C.notna()
def cum(n): return (C / C.shift(n) - 1)
def sres(x): return group_demean(x, sec, mask)
vix = load_series("^VIX")["Close"].reindex(C.index).ffill()
mkt = ret.where(mask).mean(axis=1)
mvol = mkt.rolling(21).std() * np.sqrt(252)

# ---- (b) regime scaling on rev5_sec + rev21_sec linear hold 3 (best cheap combo) and decile hold 1
Z = lambda s: zscore_xs(s, mask)
sig = (Z(-sres(cum(5))) + Z(-sres(cum(21)))) / 2
w_lin = smooth_weights(linear_weights(rank_xs(sig, mask), mask), 3)
w_dec = decile_weights(Z(-sres(cum(5))), mask, q=0.1)
print("== regime scaling (net 5bp)")
for label, base in [("lin3 rev5+21", w_lin), ("dec1 rev5", w_dec)]:
    for sc_name, sc in [("none", pd.Series(1.0, index=C.index)),
                        ("vix/20 cap2", (vix / 20).clip(0, 2)),
                        ("vix>20 only", (vix > 20).astype(float)),
                        ("vix>25 only", (vix > 25).astype(float)),
                        ("mvol/15 cap2", (mvol / 0.15).clip(0, 2)),
                        ("(vix/20)^2 cap3", ((vix / 20) ** 2).clip(0, 3))]:
        w = base.mul(sc.shift(0), axis=0)   # scalar known at close t
        net, st = xs_backtest(w, ret, cost_bps=5.0); g, gs = xs_backtest(w, ret, cost_bps=0.0)
        sp = split_perf(net, SPLITS)
        print(f"{label:14s} {sc_name:16s} gross {gs['Sharpe']:.2f} net {st['Sharpe']:.2f} IS {sp.loc['IS','Sharpe']:.2f} OOS {sp.loc['OOS','Sharpe']:.2f} turn {st['Turnover_ann']:.0f} avgGross {st['AvgGross']:.2f}")

# ---- (c) event study: extreme sector-residual moves
print("\n== event study: sector-residual z-score events (fwd sector-residual returns, bp)")
vol20 = logret.rolling(20).std()
for win in [1, 3]:
    r_res = sres(cum(win))
    z = r_res.div(vol20.shift(win) * np.sqrt(win))     # move relative to own vol, vol lagged
    z = z.where(mask)
    fwd = {h: sres(C.shift(-h) / C - 1) for h in [1, 3, 5, 10]}
    for thr in [-2.0, -2.5, -3.0, 2.0, 2.5, 3.0]:
        ev = (z < thr) if thr < 0 else (z > thr)
        n = ev.sum().sum()
        line = f"win{win} z{'<' if thr<0 else '>'}{abs(thr)}: N={n} ({n/16.7:.0f}/yr)"
        for h, f in fwd.items():
            x = f.where(ev).stack().dropna()
            xi = x[x.index.get_level_values(0) < "2018-01-01"]; xo = x[x.index.get_level_values(0) >= "2018-01-01"]
            line += f" | h{h}: {x.mean()*1e4:+.0f}bp t={x.mean()/x.std()*np.sqrt(len(x)):.1f} IS {xi.mean()*1e4:+.0f} OOS {xo.mean()*1e4:+.0f}"
        print(line, flush=True)
