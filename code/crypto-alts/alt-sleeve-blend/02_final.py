"""Final checks on strategy.py: reproduction of the research blend, headline stats at the
spec leverage, cost and short-carry stress, block bootstrap, deflated Sharpe, truncation
lookahead test, and the series/figures inputs."""
from common import *
import strategy as ST
inp = ST.load_inputs()
w = ST.blend_weights(inp)                                    # leverage 2.0
px = inp["close"].join(inp["btc_close"].rename("BTC-USD"))
extra = [c_ for c_ in w.columns if c_ not in px.columns]
if extra:
    px = px.join(inp["fund_close"][extra].reindex(px.index))
px = px.reindex(columns=w.columns)
net, st = rl.backtest_xs(w, px, 10, 365)
ref = pd.read_parquet("blend_01_nets.parquet")["bab+dilution+volume+funding"]
j = pd.concat([net / 2.0, ref], axis=1).dropna()
print("reproduction max|diff| (lev-normalised):", float((j.iloc[:, 0] - j.iloc[:, 1]).abs().max()))
n = net.loc["2018-03-08":]
wl = w.loc["2018-03-08":]
g = wl.abs().sum(axis=1); netexp = wl.sum(axis=1)
turn = (wl.shift(1) - wl.shift(2)).abs().sum(axis=1)
print("HEADLINE lev 2.0:", {k: round(float(v), 3) for k, v in S.row(net).items() if k != "name"})
for nm, (a, b) in {"full": ("2018-03-08", "2026-12-31"), "IS": S.IS, "OOS": S.OOS}.items():
    ps = rl.perf_stats(net.loc[a:b])
    print(f"  {nm}: Sharpe {ps['Sharpe']:.2f} CAGR {ps['CAGR']:.1%} Vol {ps['Vol']:.1%} MaxDD {ps['MaxDD']:.1%} Sortino {ps['Sortino']:.2f} Calmar {ps['Calmar']:.2f}")
print(f"  gross avg {g.mean():.2f} max {g.max():.2f}; net exposure avg {netexp.mean():+.3f}; turnover {turn.sum() / (len(turn) / 365):.1f}x/yr; BTC leg avg {wl.get('BTC-USD', pd.Series(0)).mean():+.3f}")
print("yearly:", S.yearly(n).round(2).to_dict())
beta_btc = np.cov(n, inp["btc_close"].pct_change().reindex(n.index).fillna(0))[0, 1] / inp["btc_close"].pct_change().reindex(n.index).var()
print("beta to BTC:", round(beta_btc, 3))
# costs
for c in (0, 5, 20, 30):
    nc, _ = rl.backtest_xs(w, px, c, 365); print(f"cost {c}bp:", {k: round(v, 2) for k, v in S.row(nc).items() if k in ('full', 'IS', 'OOS')})
# short carry: annual rate charged daily on short notional (alts and BTC)
short = (-wl.clip(upper=0)).sum(axis=1).shift(1).fillna(0)
for rate in (0.05, 0.10, 0.20):
    nc = n - short * rate / 365
    print(f"short carry {rate:.0%}/yr:", {k: round(v, 2) for k, v in S.row(nc).items() if k in ('full', 'IS', 'OOS')}, f"avg short notional {short.mean():.2f}")
# block bootstrap (30d blocks)
rng = np.random.default_rng(7); x = n.values; B = 30; nb = len(x) // B
bs = []
for _ in range(2000):
    idx = np.concatenate([np.arange(s, s + B) for s in rng.integers(0, len(x) - B, nb)])
    y = x[idx]; bs.append(y.mean() / y.std() * np.sqrt(365))
bs = np.array(bs)
print(f"bootstrap: mean {bs.mean():.2f}, 5-95% [{np.percentile(bs, 5):.2f}, {np.percentile(bs, 95):.2f}], P(Sh>1) {np.mean(bs > 1):.2f}, P(Sh>0) {np.mean(bs > 0):.2f}")
ps = rl.perf_stats(n)
for trials in (10, 50, 200):
    print(f"deflated Sharpe @ {trials} trials:", round(rl.deflated_sharpe(ps['Sharpe'], len(n), trials, ps['Skew'], ps['Kurt'] + 3), 3))
# truncation lookahead test: rebuild every input from data cut at T and compare the last row
import cmc
for T in ("2021-06-30", "2022-11-20", "2024-08-05", "2026-03-31"):
    T = pd.Timestamp(T)
    it = {k: (v.loc[:T] if isinstance(v, (pd.DataFrame, pd.Series)) else v) for k, v in inp.items()}
    it["circ_supply"] = cmc.wide("circulatingSupply", cmc.yahoo_map(inp["close"]), cmc.load_weekly().query("date <= @T"), inp["close"].loc[:T].index)
    wt = ST.blend_weights(it).iloc[-1]
    wf = w.loc[T].reindex(wt.index).fillna(0)
    print("truncation", T.date(), "max|diff| =", float((wt - wf).abs().max()))
w.to_parquet("weights_final.parquet")
pd.DataFrame({"net": net, "gross": w.abs().sum(axis=1), "net_exposure": w.sum(axis=1)}).to_parquet(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "alphas", "crypto-alts", "alt-sleeve-blend", "backtest_series.parquet"))
