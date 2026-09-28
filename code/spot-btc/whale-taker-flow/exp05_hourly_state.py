"""Hourly state-machine expression of the whale-minus-retail imbalance (coinbase-premium style).

Signal: LmS_W = imb(L >= $100k aggTrades) - imb(S < $1k) over trailing W hours, z-scored vs
its trailing 720 h (30 d). State: enter z > e, exit z < x (hysteresis). Weight:
state x [SMA(1200 h) trend or 1] x inverse-EWMA-vol (hl 480 h, target 40%, cap 1).
Grid, fixed in advance: W in {24, 72, 168} x (e, x) in {(0,0), (0,-1), (0.5,-0.5), (1,-1),
(0,-1.5)} x trend in {none, SMA50d} = 30 configs. Selection on IS = 2018-01-01 -> 2022-12-31
(2017 excluded from selection: z-score warm-up and a pre-2018 regime flagged in exp02).
OOS = 2023-01-01 -> 2026-08-31. 10 bp/side, hourly Binance BTCUSDT.
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
from exp04_hourly_ic import hourly_groups, lms  # noqa: E402

HPY = 365 * 24
IS = ("2018-01-01", "2022-12-31")
OOS = ("2023-01-01", "2026-08-31 23:00")


def hysteresis(z, enter, exit_):
    zv = z.to_numpy(dtype=float)
    out = np.zeros(len(zv))
    s = 0.0
    for i, v in enumerate(zv):
        if not np.isnan(v):
            if s == 0.0 and v > enter:
                s = 1.0
            elif s == 1.0 and v < exit_:
                s = 0.0
        out[i] = s
    return pd.Series(out, index=z.index)


def stats(w, close, cost=10.0):
    net, _ = rl.backtest(w, close, cost_bps=cost, ann=HPY)
    wl = w.reindex(close.index).fillna(0).shift(1).fillna(0)
    out = {}
    for k, (a, b) in {"full": (IS[0], OOS[1]), "IS": IS, "OOS": OOS}.items():
        s = net.loc[a:b]
        out[f"Sh_{k}"] = s.mean() / s.std() * np.sqrt(HPY)
    s = net.loc[IS[0]:OOS[1]]
    eq = (1 + s).cumprod()
    out["CAGR"] = eq.iloc[-1] ** (HPY / len(s)) - 1
    out["MaxDD"] = (eq / eq.cummax() - 1).min()
    out["Turn"] = wl.loc[IS[0]:OOS[1]].diff().abs().sum() / (len(s) / HPY)
    out["Expo"] = wl.loc[IS[0]:OOS[1]].mean()
    return net, out


def main():
    h = btc_hourly().loc[:OOS[1]]
    close = h.Close
    fl = hourly_groups().reindex(close.index)
    r = close.pct_change()
    ewv = r.ewm(halflife=480, min_periods=480).std() * np.sqrt(HPY)
    vs = (0.40 / ewv).clip(0, 1).fillna(0)
    trend = (close > close.rolling(1200).mean()).astype(float)
    rows, nets = [], {}
    for nm, w in (("vol B&H", vs), ("SMA50d x vol", trend * vs)):
        nets[nm], st = stats(w, close); rows.append(pd.Series(st, name=nm))
    for W in (24, 72, 168):
        x, _, _ = lms(fl, W)
        z = (x - x.rolling(720, min_periods=360).mean()) / x.rolling(720, min_periods=360).std()
        for e, xx in ((0, 0), (0, -1), (0.5, -0.5), (1, -1), (0, -1.5)):
            st_ = hysteresis(z, e, xx)
            for tr in ("none", "sma50d"):
                w = st_ * vs * (trend if tr == "sma50d" else 1.0)
                nm = f"W{W} e{e} x{xx} {tr}"
                nets[nm], st = stats(w, close); rows.append(pd.Series(st, name=nm))
    res = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(res.round(2).to_string())
    res.to_csv(os.path.join(HERE, "exp05_hourly_state.csv"))
    g = res.iloc[2:]
    print("\ngrid (30): median Sh full/IS/OOS", g[["Sh_full", "Sh_IS", "Sh_OOS"]].median().round(2).tolist(),
          " IS->OOS spearman", round(g.Sh_IS.corr(g.Sh_OOS, method="spearman"), 2))
    for tr in ("none", "sma50d"):
        gg = g[g.index.str.endswith(tr)]
        best = gg.Sh_IS.idxmax()
        print(f"IS-selected ({tr}): {best}  IS {gg.loc[best, 'Sh_IS']:.2f}  OOS {gg.loc[best, 'Sh_OOS']:.2f}  "
              f"| median OOS {gg.Sh_OOS.median():.2f}")
    pd.to_pickle(nets, os.path.join(HERE, "_exp05_nets.pkl"))


if __name__ == "__main__":
    main()
