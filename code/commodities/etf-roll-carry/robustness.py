"""Step 5: robustness of carry ivol (the candidate). Neighbours, costs, leave-one-out, rebalance
day, yearly returns, deflated Sharpe."""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))
from factors import *
from research_lib import backtest_xs, quantile_weights, fmt, split_stats, perf_stats, deflated_sharpe

fut, etf = load_panel()
r = etf.pct_change()
vol = r.ewm(halflife=40, min_periods=40).std() * np.sqrt(ANN)
SPL = {"IS": ("2011-01-01", "2018-12-31"), "OOS": ("2019-01-01", "2026-12-31")}

def reb(w, offset=0):
    """Rebalance on the (offset)-th business day before month end."""
    g = w.index.to_series().groupby(w.index.to_period("M"))
    pos = g.cumcount(ascending=False)
    return w.where(pos == offset, axis=0).ffill().fillna(0)

def ivol(w):
    x = (np.sign(w) / vol).where(w != 0).fillna(0)
    L = x.clip(lower=0); S = x.clip(upper=0)
    return (L.div(L.sum(1).replace(0, np.nan), axis=0) * 0.5 - S.div(S.sum(1).replace(0, np.nan), axis=0) * 0.5).fillna(0)

def strat(names=None, ks=(63, 126, 252), q=0.375, offset=0, weighting="ivol"):
    cols = names or list(etf.columns)
    E, F = etf[cols], fut[cols]
    mask = E.notna() & F.notna() & E.shift(260).notna()
    s = sum(rank_xs(carry(F, E, k), mask) for k in ks) / len(ks)
    w = quantile_weights(s, mask, q=q)
    if weighting == "ivol":
        w = ivol(w.reindex(columns=etf.columns).fillna(0))
    return reb(w.reindex(columns=etf.columns).fillna(0), offset)

def row(name, w, cost=10):
    net, st = backtest_xs(w, etf, cost, ANN, name)
    net = net.loc["2011":]
    ss = split_stats(net, SPL, ann=ANN)
    return pd.Series({"Sharpe": perf_stats(net, ANN).Sharpe, "CAGR": st.CAGR, "MaxDD": st.MaxDD,
                      "SR_IS": ss.loc["IS", "Sharpe"], "SR_OOS": ss.loc["OOS", "Sharpe"],
                      "Turn": st.Turnover_ann}, name=name), net

rows = []
base, net0 = row("BASE ks=63/126/252 q=.375 ivol M", strat())
rows.append(base)
for q in (0.25, 0.5):
    rows.append(row(f"q={q}", strat(q=q))[0])
for ks in [(63,), (126,), (252,), (21, 63, 126, 252)]:
    rows.append(row(f"ks={ks}", strat(ks=ks))[0])
for off in (5, 10, 15):
    rows.append(row(f"rebalance {off}bd before month-end", strat(offset=off))[0])
for c in (5, 20, 30):
    rows.append(row(f"cost {c}bp", strat(), cost=c)[0])
for a in etf.columns:
    rows.append(row(f"drop {a}", strat(names=[x for x in etf.columns if x != a]))[0])
print(fmt(pd.DataFrame(rows)).to_string())

print("\nyearly returns of BASE (%):")
print((net0.groupby(net0.index.year).apply(lambda x: (1 + x).prod() - 1) * 100).round(1).to_string())
st = perf_stats(net0, ANN)
for n in (10, 50, 100, 150):
    print(f"deflated Sharpe prob, N trials={n}: {deflated_sharpe(st.Sharpe, len(net0), n, st.Skew, st.Kurt + 3, ANN):.3f}")

print("\n=== tranched book: mean of 4 monthly books rebalanced 0/5/10/15 bd before month-end ===")
def tranched(**kw):
    return sum(strat(offset=o, **kw) for o in (0, 5, 10, 15)) / 4
rows = []
T, netT = row("TRANCHED base", tranched())
rows.append(T)
for q in (0.25, 0.5):
    rows.append(row(f"TRANCHED q={q}", tranched(q=q))[0])
for ks in [(63,), (126,), (252,)]:
    rows.append(row(f"TRANCHED ks={ks}", tranched(ks=ks))[0])
rows.append(row("TRANCHED drop natgas", tranched(names=[x for x in etf.columns if x != "natgas"]))[0])
rows.append(row("TRANCHED cost 20bp", tranched(), cost=20)[0])
print(fmt(pd.DataFrame(rows)).to_string())
st = perf_stats(netT, ANN)
print(st.round(3).to_string())
for n in (10, 50, 100, 150):
    print(f"tranched DSR prob, N={n}: {deflated_sharpe(st.Sharpe, len(netT), n, st.Skew, st.Kurt + 3, ANN):.3f}")
