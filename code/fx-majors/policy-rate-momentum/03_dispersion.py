"""policy-rate-momentum -- last re-framing: trade the 12m policy-rate-change book only when
policy cycles actually diverge (cross-sectional std of the 12m changes above its own
expanding median, known at the rebalance). Pre-registered single rule, no tuning."""
import os, sys, importlib
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared")); sys.path.insert(0, HERE)
from macro_data import short_rates, h10_fx  # noqa: E402
ext = importlib.import_module("02_extend"); scr = importlib.import_module("01_screen")
G8 = ext.G8
fx = h10_fx().loc["1999-01-01":].ffill().dropna()
rates = short_rates(); me = fx.resample("ME").last().index
rows = []
for k in (6, 12, 24):
    s = (rates[G8] - rates[G8].shift(int(round(k * 30.4375)))).reindex(me, method="ffill").dropna(how="all")
    disp = s.std(axis=1)
    gate = (disp > disp.expanding(24).median()).astype(float)
    for kind, f in (("lin", scr.xs_linear), ("bilat", scr.bilateral)):
        W = f(s).mul(gate, axis=0)
        net = ext.monthly_book_returns(fx, W)
        for lab, a, b in (("1999-2009", "1999", "2009"), ("2010-2019", "2010", "2019"), ("2020-2026", "2020", "2026"), ("ALL", "1999", "2026")):
            st = ext.stats_m(net.loc[a:b], f"dpol{k}_{kind}_gated"); st["period"] = lab; rows.append(st)
df = pd.DataFrame(rows)
print(df.pivot_table(index=df.index, columns="period", values="Sharpe")[["1999-2009", "2010-2019", "2020-2026", "ALL"]].round(2))
df.to_csv(os.path.join(HERE, "03_dispersion.csv"))
