"""Headline stats for the spec (from 2018-03-08, the first fully populated universe date)."""
from common import *
w = pd.read_parquet("weights_final.parquet").loc["2018-03-08":]
net = pd.read_parquet("robust_03_nets.parquet")["BASE dil12w|h30|bn"].loc["2018-03-08":]
for nm, (a, b) in {"full": ("2018-03-08", "2026-12-31"), "IS": S.IS, "OOS": S.OOS}.items():
    ps = rl.perf_stats(net.loc[a:b])
    print(f"{nm}: Sharpe {ps['Sharpe']:.2f} CAGR {ps['CAGR']:.1%} Vol {ps['Vol']:.1%} MaxDD {ps['MaxDD']:.1%} Sortino {ps['Sortino']:.2f} t_NW {ps['t_NW']:.2f}")
g = w.abs().sum(axis=1); turn = (w - w.shift(1)).abs().sum(axis=1)
alts = w.drop(columns="BTC-USD")
print(f"gross avg {g.mean():.2f} max {g.max():.2f}; alt long {alts.clip(lower=0).sum(axis=1).mean():.2f} short {-alts.clip(upper=0).sum(axis=1).mean():.2f}; BTC leg avg {w['BTC-USD'].mean():+.3f} range [{w['BTC-USD'].min():+.2f},{w['BTC-USD'].max():+.2f}]; net {w.sum(axis=1).mean():+.3f}; turnover {turn.sum() / (len(turn) / 365):.1f}x/yr")
btc = S.load()["btc"].pct_change().reindex(net.index)
print("beta to BTC", round(net.cov(btc) / btc.var(), 3), " corr to BAB", round(net.corr(S.bab_reference()), 2))
rng = np.random.default_rng(7); x = net.values; B = 30; nb = len(x) // B
bs = np.array([(lambda y: y.mean() / y.std() * np.sqrt(365))(x[np.concatenate([np.arange(s, s + B) for s in rng.integers(0, len(x) - B, nb)])]) for _ in range(2000)])
print(f"bootstrap mean {bs.mean():.2f} 5-95% [{np.percentile(bs, 5):.2f},{np.percentile(bs, 95):.2f}] P>0 {np.mean(bs > 0):.2f} P>0.5 {np.mean(bs > 0.5):.2f}")
ps = rl.perf_stats(net)
for n in (10, 24, 50, 100):
    print(f"DSR @{n}:", round(rl.deflated_sharpe(ps["Sharpe"], len(net), n, ps["Skew"], ps["Kurt"] + 3), 3))
short = (-w.clip(upper=0)).sum(axis=1).shift(1).fillna(0)
for rate in (0.05, 0.10, 0.20):
    print(f"short carry {rate:.0%}:", {k: round(v, 2) for k, v in S.row(net - short * rate / 365).items() if k in ("full", "IS", "OOS")}, f"short notional {short.mean():.2f}")
