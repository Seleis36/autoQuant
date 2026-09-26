"""Next-day SPY-hedged return by quintile of the US-session residual z, per region, IS/OOS.
Also the decay: does the reversal complete on t+1 or continue on t+2..t+5?"""
from lib import *
C, O = load()
r = C.pct_change()
allnames = ASIA + EUROPE + AMERICAS
u, z = residual_signal(C, O, allnames)
bcc = rolling_beta(r[allnames], r["SPY"], 250)
h = r[allnames] - bcc.shift(1).mul(r["SPY"], axis=0)          # hedged daily return
for per, (a, b) in {"IS": ("2003", "2012"), "OOS": ("2013", "2026")}.items():
    print(f"\n=== {per}: next-day hedged return (bp) by z quintile")
    rows = {}
    for t in allnames:
        df = pd.DataFrame({"z": z[t], "h1": h[t].shift(-1), "h2": h[t].shift(-2),
                           "h3_5": h[t].shift(-3) + h[t].shift(-4) + h[t].shift(-5)}).loc[a:b].dropna()
        if len(df) < 200: continue
        q = pd.qcut(df["z"], 5, labels=False)
        g = df.groupby(q)[["h1"]].mean()["h1"] * 1e4
        ic1 = df["z"].corr(df["h1"], method="spearman")
        ic2 = df["z"].corr(df["h2"], method="spearman")
        ic35 = df["z"].corr(df["h3_5"], method="spearman")
        tail = df.loc[df.z.abs() > 1.5]
        tail_ret = (-(np.sign(tail.z)) * tail.h1).mean() * 1e4
        rows[t] = list(g.round(1)) + [round(ic1, 3), round(ic2, 3), round(ic35, 3), round(tail_ret, 1), len(tail)]
    print(pd.DataFrame(rows, index=["Q1", "Q2", "Q3", "Q4", "Q5", "IC1", "IC2", "IC3-5", "fade|z|>1.5 bp", "n_tail"]).T.to_string())
