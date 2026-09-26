"""Portfolio book: fade the US-session residual of the Asian (and European) ETFs, SPY-hedged.
Variants: linear z (clipped), tail-only |z|>k, region sets; gross and net at 2/5/10 bp."""
import sys
from lib import *
sys.path.insert(0, "../../shared")
import research_lib as rl

C, O = load()
res = []
def run(names, mode, k=1.5, cost=5.0, tag=""):
    u, z = residual_signal(C, O, names)
    r = C.pct_change()
    vol = r[names].rolling(60, min_periods=40).std() * np.sqrt(252)
    if mode == "linear":
        s = -z.clip(-3, 3)
    elif mode == "tail":
        s = -np.sign(z).where(z.abs() > k, 0.0)
    elif mode == "tailz":
        s = -z.clip(-3, 3).where(z.abs() > k, 0.0)
    # risk budget: each unit of signal = 10% ann vol per name /n names
    w = (s * (0.10 / vol)).div(len(names)).fillna(0.0)
    net, gross, te, ts = hedged_book(w, C, names, cost_etf=cost, cost_spy=min(cost, 1.0))
    out = {}
    for per, (a, b) in {"FULL": ("2003", "2026"), "IS": ("2003", "2012"), "OOS": ("2013", "2026")}.items():
        n = net.loc[a:b]; g = gross.loc[a:b]
        out[per + "_net"] = n.mean() / n.std() * np.sqrt(252)
        out[per + "_gross"] = g.mean() / g.std() * np.sqrt(252)
    out["turn_etf"] = te.mean() * 252; out["gross_lev"] = w.abs().sum(axis=1).mean()
    out["vol"] = net.std() * np.sqrt(252)
    res.append(pd.Series(out, name=f"{tag}|{mode}|k{k}|c{cost}"))
    return net

for names, tag in [(["EWJ", "EWY", "EWA", "FXI", "INDA", "EEM"], "ASIA6"), (["EWJ", "EWY", "EWA", "INDA"], "ASIA4"),
                   (EUROPE, "EUR"), (AMERICAS, "AMER"), (ASIA + EUROPE, "ASIA+EUR")]:
    for mode, k in [("linear", 0), ("tail", 1.0), ("tail", 1.5), ("tail", 2.0), ("tailz", 1.0)]:
        for cost in [0.0, 2.0, 5.0]:
            run(names, mode, k, cost, tag)
df = pd.DataFrame(res).round(2)
pd.set_option("display.width", 250)
print(df.to_string())
