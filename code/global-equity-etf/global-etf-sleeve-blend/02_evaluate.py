"""Evaluate the blend spec: full/IS/OOS, costs, lag, sleeve attribution, bootstrap, truncation."""
import sys
sys.path.insert(0, "../shared")
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
import data as D, xs, research_lib as rl
import strategy as S
C = D.load_panel(S.COLUMNS, "Close", start="1998-12-01")
SPL = {"FULL": ("2001-07-02", "2026"), "IS": ("2001-07-02", "2012"), "OOS": ("2013", "2026")}
W = S.target_weights(C)
rows, nets = [], {}
def ev(Wx, name, cost=5.0, spy=1.0, lag=0):
    Wx = Wx.shift(lag).fillna(0.0) if lag else Wx
    net, gross, turn, We = xs.run(Wx.loc["2001-07-02":], C.loc["2001-07-02":], cost_bps=cost, spy_cost_bps=spy, name=name)
    r = xs.summarize(net, SPL, turn, We, name=name); r["MaxGross"] = We.abs().sum(axis=1).max()
    r["p99Gross"] = We.abs().sum(axis=1).quantile(0.99)
    rows.append(r); nets[name] = net; return net
net = ev(W, "BLEND spec 5bp")
ev(W, "BLEND 2bp", 2.0, 0.5); ev(W, "BLEND 10bp", 10.0, 2.0)
ev(W, "BLEND +1d lag", lag=1)
ev(S.target_weights(C, b_weight=0.0), "trend sleeve only (x0.67)")
ev(S.target_weights(C, a_weight=0.0), "FOMC sleeve only (x0.87)")
ev(S.target_weights(C, 0.67 * 1.0, 0.87 * 0.5), "FOMC risk share ~1/3")
df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(df[["FULL_SR", "IS_SR", "OOS_SR", "FULL_CAGR", "IS_CAGR", "OOS_CAGR", "MaxDD", "Vol", "t_NW", "Turn/yr", "Gross", "Net", "p99Gross", "MaxGross"]].round(3).to_string())
n = nets["BLEND spec 5bp"]; n = n[n.index >= n.ne(0).idxmax()]
for per, (a, b) in SPL.items():
    x = n.loc[a:b]; eq = (1 + x).cumprod(); print(per, "MaxDD %.1f%%" % ((eq / eq.cummax() - 1).min() * 100))
spy = C["SPY"].pct_change().reindex(n.index)
print("corr to SPY daily %.3f" % n.corr(spy))
print("calendar years (%):", ((1 + n).groupby(n.index.year).prod() - 1).mul(100).round(1).to_dict())
rng = np.random.default_rng(1); x = n.values; N = len(x); srs = []
for _ in range(2000):
    idx = []
    while len(idx) < N:
        s0 = rng.integers(0, N); Lb = rng.geometric(1 / 63); idx.extend(range(s0, min(s0 + Lb, N)))
    xb = x[np.array(idx[:N])]; srs.append(xb.mean() / xb.std() * np.sqrt(252))
srs = np.array(srs)
print(f"bootstrap SR median {np.median(srs):.2f}, 5% {np.percentile(srs,5):.2f}, P>0 {np.mean(srs>0):.3f}, P>0.5 {np.mean(srs>0.5):.3f}")
st = rl.perf_stats(n, ann=252)
print("DSR N=100:", round(rl.deflated_sharpe(st['Sharpe'], len(n), 100, st['Skew'], st['Kurt'] + 3, ann=252), 3))
for d in ["2009-03-31", "2019-12-31", "2026-09-15"]:
    d = C.index[C.index <= d][-1]
    print("truncation", d.date(), "max diff", f"{(S.target_weights(C.loc[:d]).loc[d] - W.loc[d]).abs().max():.1e}")
pd.DataFrame(nets).to_parquet("nets_02.parquet"); W.to_parquet("spec_weights.parquet")
