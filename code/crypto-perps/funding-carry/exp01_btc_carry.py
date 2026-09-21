"""exp01 -- BTC spot-long / perp-short carry: always-on vs simple funding-timing rules.
Hourly bars, 15 bp fees + 5 bp slippage per switch (both legs), capital_factor = 1 (return on one-leg notional)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from carry_lib import *

sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
df = load_pair(sym)
print(sym, df.index.min(), df.index.max(), len(df))
r = leg_returns(df)
d = daily(r)
print("gross always-on daily: mean %.5f std %.5f Sharpe %.2f" % (d.mean(), d.std(), d.mean()/d.std()*np.sqrt(365)))
print("basis b: mean %.5f std %.5f ; hourly db std %.5f" % (df.b.mean(), df.b.std(), df.b.diff().std()))
print("funding/yr %.2f%%" % (df.f.sum() / (len(df)/HOURS) * 100))
print("by year gross:", d.groupby(d.index.year).apply(lambda x: round(x.mean()/x.std()*np.sqrt(365),2)).to_dict())

rows = []
def run(name, w, **kw):
    net, we, turn = backtest_carry(df, w, **kw)
    s = summarize(net, we, turn, name=name, splits=SPLITS)
    rows.append(s); return net

# always on
run("always_on", pd.Series(1.0, index=df.index))
# trailing funding mean over k settlements > tau ; settled funding series forward-filled
fs = df["f"].where(df["f"] != 0)              # only settlement stamps
fsettle = fs.dropna()
for k in (1, 3, 6, 9, 21):
    m = fsettle.rolling(k).mean().reindex(df.index).ffill()
    for tau in (0.0, 0.00005, 0.0001):
        run(f"trail_k{k}_tau{tau*1e4:.1f}bp", (m > tau).astype(float))
# hysteresis: enter when trailing mean > hi, exit when < lo
for k in (3, 9):
    m = fsettle.rolling(k).mean().reindex(df.index).ffill()
    for hi, lo in ((0.0001, 0.0), (0.00005, -0.00005), (0.0001, -0.0001), (0.0, -0.0001)):
        st = pd.Series(np.nan, index=df.index)
        st[m > hi] = 1.0; st[m < lo] = 0.0
        run(f"hyst_k{k}_hi{hi*1e4:.1f}_lo{lo*1e4:.1f}", st.ffill().fillna(0.0))
# basis-based: current basis (P/S-1) > 0 => next funding likely positive
for tau in (0.0, 0.0002, 0.0005):
    run(f"basis_gt{tau*1e4:.0f}bp", (df["b"].rolling(8).mean() > tau).astype(float))

out = pd.DataFrame(rows)
cols = ["CAGR","Vol","Sharpe","Sharpe_IS","Sharpe_OOS","MaxDD","HitRate","t_NW","TimeInMkt","Switches/yr"]
pd.set_option("display.width", 200); pd.set_option("display.max_rows", 100)
print(out[cols].round(4).to_string())
out.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"exp01_{sym}.csv"))
