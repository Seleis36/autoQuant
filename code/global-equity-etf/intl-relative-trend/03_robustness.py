"""Robustness of the deployable spec (strategy.target_weights) on the ETF era, 2001-2026.
All numbers come from the strategy function itself."""
import sys
sys.path.insert(0, "../shared")
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
import data as D, xs, research_lib as rl
import strategy as S

C = D.load_panel(S.COUNTRIES + ["SPY"], "Close", start="1998-12-01")
SPL = {"FULL": ("2001", "2026"), "IS": ("2001", "2012"), "OOS": ("2013", "2026")}
rows, nets = [], {}

def evaluate(W, name, cost=5.0, spy_cost=1.0, lag=0):
    W = W.shift(lag).fillna(0.0) if lag else W
    net, gross, turn, We = xs.run(W.loc["2001-01-01":], C.loc["2001-01-01":], cost_bps=cost, spy_cost_bps=spy_cost, name=name)
    r = xs.summarize(net, SPL, turn, We, name=name)
    r["MaxGross"] = We.abs().sum(axis=1).max()
    rows.append(r); nets[name] = net
    return net

base = S.target_weights(C)
evaluate(base, "SPEC blend50 (5bp)")
evaluate(S.target_weights(C, blend=1.0), "AGG only")
evaluate(S.target_weights(C, blend=0.0), "DIV only")
evaluate(base, "SPEC +1 day lag", lag=1)
evaluate(base, "SPEC +5 day lag", lag=5)
evaluate(base, "SPEC 2bp", cost=2.0, spy_cost=0.5)
evaluate(base, "SPEC 10bp", cost=10.0, spy_cost=2.0)
evaluate(S.target_weights(C, beta_win=126), "beta_win 126")
evaluate(S.target_weights(C, beta_win=504), "beta_win 504")
evaluate(S.target_weights(C, lookbacks=(252,)), "lookback 252 only")
evaluate(S.target_weights(C, lookbacks=(126, 252)), "lookbacks 126,252")
evaluate(S.target_weights(C, lookbacks=(252, 504)), "lookbacks 252,504")
evaluate(S.target_weights(C, lookbacks=(63, 126, 252, 504)), "lookbacks 63..504")
evaluate(S.target_weights(C, vol_win=63), "vol_win 63")
# mid-month rebalance: shift the rebalance calendar by ~10 trading days
agg, div, ret = S.sleeve_weights(C)
def mid_month(close):
    idx = close.index
    s = pd.Series(idx, index=idx)
    return pd.DatetimeIndex(s.groupby([idx.year, idx.month]).nth(10).values)
S._rebalance_dates_orig = S._rebalance_dates
S._rebalance_dates = lambda index: mid_month(pd.DataFrame(index=index))
evaluate(S.target_weights(C), "mid-month rebalance")
S._rebalance_dates = S._rebalance_dates_orig

df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(df[["FULL_SR", "IS_SR", "OOS_SR", "FULL_CAGR", "MaxDD", "Vol", "t_NW", "Turn/yr", "Gross", "Net", "MaxGross"]].round(2).to_string())

net = nets["SPEC blend50 (5bp)"]
net = net[net.index >= net.ne(0).idxmax()]
spy = C["SPY"].pct_change().reindex(net.index)
print("\nfirst active day:", net.index[0].date(), " corr(daily, SPY) =", round(net.corr(spy), 3),
      " corr(monthly, SPY) =", round((1 + net).resample("ME").prod().sub(1).corr((1 + spy).resample("ME").prod().sub(1)), 3))
yr = (1 + net).groupby(net.index.year).prod() - 1
print("calendar-year returns (%):", (yr * 100).round(1).to_dict())
# stationary block bootstrap of the annualised Sharpe (block 63d)
rng = np.random.default_rng(0); x = net.values; n = len(x); B = 2000; srs = []
for _ in range(B):
    idx = []
    while len(idx) < n:
        s0 = rng.integers(0, n); L = rng.geometric(1 / 63)
        idx.extend(range(s0, min(s0 + L, n)))
    xb = x[np.array(idx[:n])]
    srs.append(xb.mean() / xb.std() * np.sqrt(252))
srs = np.array(srs)
print(f"bootstrap SR: median {np.median(srs):.2f}, 5% {np.percentile(srs,5):.2f}, P(SR>0) {np.mean(srs>0):.3f}, P(SR>0.5) {np.mean(srs>0.5):.3f}")
st = rl.perf_stats(net, ann=252)
print("DSR (N=60 trials):", round(rl.deflated_sharpe(st['Sharpe'], len(net), 60, st['Skew'], st['Kurt'] + 3, ann=252), 3))
pd.DataFrame(nets).to_parquet("nets_03.parquet")
base.to_parquet("spec_weights.parquet")
