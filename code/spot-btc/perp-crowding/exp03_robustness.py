"""Robustness of the contrarian retail-positioning signal.

Features: glob = log global long/short ACCOUNT ratio (retail crowd), topacc = log top-trader
ACCOUNT ratio (the IS-strongest feature). Contrarian: long when the crowd is LESS long than usual.
Normalisations: expanding rank (exp02), rolling 365 d rank, rolling 90 d z, rolling 180 d z.
Forms: A standalone x vol; B gate on SMA50 x vol. 10 bp/side, daily, 2021-03 -> 2026-09.
Then: cost sensitivity, and hourly AND-filter on coinbase-premium (daily crowding state known
at the previous 00:00 UTC applied to the next 24 hourly bars).
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_daily, btc_hourly, evaluate  # noqa: E402
import research_lib as rl  # noqa: E402
from exp01_screen import daily_metrics, features  # noqa: E402
from exp02_backtest import START, exp_rank  # noqa: E402


def norms(x):
    return {
        "exprank": exp_rank(x),
        "rank365": x.rolling(365, min_periods=180).apply(lambda a: (a[:-1] < a[-1]).mean(), raw=True) - 0.5,
        "z90": (x - x.rolling(90, min_periods=45).mean()) / x.rolling(90, min_periods=45).std(),
        "z180": (x - x.rolling(180, min_periods=90).mean()) / x.rolling(180, min_periods=90).std(),
    }


def main():
    d = btc_daily()
    close = d.Close
    f = features(daily_metrics(close.index), close)
    r = close.pct_change()
    vs = rl.vol_target_scalar(r, target=0.40, halflife=20, cap=1.0)
    trend = (close > close.rolling(50).mean()).astype(float)
    rows, states = [], {}
    for nm, w in (("vol B&H", vs), ("SMA50 x vol", trend * vs)):
        _, st = evaluate(w, close, start=START, name=nm); rows.append(st)
    for feat in ("glob", "topacc"):
        for nk, s in norms(f[feat]).items():
            on = (-s > 0).astype(float)            # contrarian: crowd less long than usual
            states[(feat, nk)] = on
            _, st = evaluate(on * vs, close, start=START, name=f"A {feat} {nk}"); rows.append(st)
            _, st = evaluate(on * trend * vs, close, start=START, name=f"B {feat} {nk}"); rows.append(st)
    for c in (0.0, 5.0, 20.0):
        on = states[("glob", "exprank")]
        _, st = evaluate(on * trend * vs, close, start=START, cost_bps=c, name=f"B glob exprank @{c:g}bp"); rows.append(st)
        _, st = evaluate(trend * vs, close, start=START, cost_bps=c, name=f"SMA50 x vol @{c:g}bp"); rows.append(st)
    res = pd.concat(rows)
    pd.set_option("display.width", 200)
    print(res.round(2).to_string())
    g = res[res.index.str.startswith(("A ", "B "))]
    for k in ("A", "B"):
        s = g[g.index.str.startswith(k + " ") & ~g.index.str.contains("@")]
        print(k, "median full/IS/OOS", s[["Sh_full", "Sh_IS", "Sh_OOS"]].median().round(2).tolist(), "n", len(s))

    # hourly AND-filter on coinbase-premium
    import importlib.util
    spec = importlib.util.spec_from_file_location("cbp", os.path.join(REPO, "code", "spot-btc", "coinbase-premium", "strategy.py"))
    cbp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cbp)
    HPY = 365 * 24

    def stats(w, px, cost=10.0):
        net, _ = rl.backtest(w, px, cost_bps=cost, ann=HPY)
        eq = (1 + net).cumprod()
        wl = w.reindex(px.index).fillna(0).shift(1).fillna(0)
        return net, {"MaxDD": (eq / eq.cummax() - 1).min(), "Expo": wl.mean()}

    hh = btc_hourly()
    hc = hh.Close
    cbc = pd.read_parquet(os.path.join(REPO, "data", "COINBASE_BTCUSD_1h.parquet"))["Close"].reindex(hc.index).ffill(limit=3)
    sp = cbp.hysteresis_state(cbp.premium_zscore(hc, cbc, 720), 0.0, -1.5)
    hr = hc.pct_change()
    ewv = hr.ewm(halflife=480, min_periods=480).std() * np.sqrt(HPY)
    hvs = (0.40 / ewv).clip(0, 1).fillna(0)
    htr = (hc > hc.rolling(1200).mean()).astype(float)
    base = sp * htr * hvs
    out = []
    for nm, w in [("cbprem live spec", base)] + [
            (f"cbprem AND {feat} {nk}", base * states[(feat, nk)].shift(1).reindex(hc.index, method="ffill").fillna(0))
            for feat in ("glob", "topacc") for nk in ("exprank", "z90")]:
        net, st = stats(w.loc["2021-03-01":], hc.loc["2021-03-01":])
        sh = lambda a, b: net.loc[a:b].mean() / net.loc[a:b].std() * np.sqrt(HPY)  # noqa: E731
        out.append(pd.Series({"Sh_2021-03+": sh("2021-03-01", None), "IS(21-22)": sh("2021-03-01", "2022-12-31"),
                              "OOS": sh("2023-01-01", None), "MaxDD": st["MaxDD"], "Expo": st["Expo"]}, name=nm))
    print(pd.DataFrame(out).round(2).to_string())


if __name__ == "__main__":
    main()
