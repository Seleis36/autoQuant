"""terms-of-trade-fx -- is the bloc GAP just cross mean-reversion?
GAP_k = zb(dToT_k) - zb(dFX_k). Controls on the same bloc book: REV_k = -zb(dFX_k) (pure
relative reversal of AUD/CAD/NZD) and MOM_k = zb(dToT_k) (pure ToT). If GAP ~ REV, the ToT
leg adds nothing. Also: GAP with the ToT leg lagged an extra month (does the information
live in fresh commodity moves?)."""
import os, sys, importlib
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared")); sys.path.insert(0, HERE)
from fx_panel import CCYS, backtest, lag_to_fx, load_px, split_table, usd_per_ccy  # noqa: E402
from macro_data import h10_fx  # noqa: E402
from research_lib import perf_stats  # noqa: E402
s01 = importlib.import_module("01_screen"); b = importlib.import_module("02_bloc")
cmd = s01.load_cmd()
px = load_px(); idx = px.index; fxl = np.log(usd_per_ccy(px))
rows, nets = [], {}
for k in (3, 6, 12):
    d = lag_to_fx(s01.tot_change(cmd, 21 * k), idx, lag=1)
    dfx = fxl - fxl.shift(21 * k)
    sigs = {f"GAP{k}": b.zb(d) - b.zb(dfx), f"REV{k}": -b.zb(dfx), f"TOT{k}": b.zb(d),
            f"GAP{k}_totlag1m": b.zb(d.shift(21)) - b.zb(dfx)}
    for name, sg in sigs.items():
        for freq in ("M", "W"):
            net, gross, turn, st = backtest(b.hold(b.bloc_book(sg), idx, freq), px, cost=None)
            nets[f"{name}_{freq}"] = net
            t = split_table(net)
            rows.append({"sig": name, "freq": freq, "FULL": t.loc["FULL", "Sharpe"], "IS": t.loc["IS", "Sharpe"],
                         "OOS": t.loc["OOS", "Sharpe"], "turn": st["Turnover_ann"]})
df = pd.DataFrame(rows); pd.set_option("display.width", 200)
print(df.round(2).to_string())
N = pd.DataFrame(nets)
print(N[["GAP6_M", "REV6_M", "TOT6_M", "GAP12_W", "REV12_W", "TOT12_W"]].corr().round(2))
df.to_csv(os.path.join(HERE, "03_gap_control.csv"))
# H.10
h = h10_fx().loc["1999-01-01":].ffill().dropna(); hidx = h.index; r = h.pct_change(); hl = np.log(h)
out = []
cm = cmd.reindex(cmd.index.union(hidx)).ffill().reindex(hidx).shift(1)
for k in (6, 12):
    d = s01.tot_change(cm, 21 * k); dfx = hl - hl.shift(21 * k)
    for name, sg in {f"GAP{k}": b.zb(d) - b.zb(dfx), f"REV{k}": -b.zb(dfx), f"TOT{k}": b.zb(d)}.items():
        W = b.hold(b.bloc_book(sg), hidx, "M")
        net = (W.shift(1) * r[CCYS]).sum(axis=1) - (W.shift(1) - W.shift(2)).abs().sum(axis=1) * 1e-4
        row = {"sig": name}
        for per, a, bb in (("00-09", "2000", "2009"), ("10-19", "2010", "2019"), ("20-26", "2020", "2026"), ("ALL", "2000", "2026")):
            row[per] = perf_stats(net.loc[a:bb], ann=252)["Sharpe"]
        out.append(row)
print(pd.DataFrame(out).round(2).to_string())
