"""Lookahead-free generalisation of the IS-frozen weights: in calendar year Y each active
sleeve gets k_i = (target/sqrt(n_active)) / sigma_i, sigma_i = std of its net daily returns over
all history through Dec 31 of Y-1 (expanding). Weights constant within the year. Applied to
CORE4 and to WF7 (sleeve active in Y iff expanding net Sharpe through Y-1 > 0 and >= 3y history).
Also: bootstrap, DSR, per-year P&L, beta, cost stress."""
import sys, os
_H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, _H)
import blend as B  # noqa
import numpy as np, pandas as pd
import sxlib as sx

R, SL, c = B.R, B.SL, B.c

def yearly_weights(names, select):
    K = pd.DataFrame(0.0, index=c.index, columns=names)
    for Y in range(2002, c.index[-1].year + 1):
        past = R.loc[: f"{Y-1}-12-31", names]
        act = []
        for n in names:
            x = past[n].loc[SL[n].abs().sum(axis=1).loc[past.index].gt(0).idxmax():]  # since sleeve first traded
            ok = len(x) > 756 and (not select or x.mean() > 0)
            act.append((n, x.std() * np.sqrt(252) if ok else np.nan))
        act = [(n, v) for n, v in act if v == v]
        for n, v in act:
            K.loc[str(Y), n] = (B.TARGET / np.sqrt(len(act))) / v
    return K

rows, nets = [], {}
for nm, names, sel in [("CORE4-slow", ["ON", "CAL", "DIP", "RATE"], False),
                       ("CORE3-slow", ["ON", "CAL", "DIP"], False),
                       ("ALL7-slow", ["ON", "CAL", "DIP", "RATE", "REV", "BAB", "SEAS"], False),
                       ("WF7-slow", ["ON", "CAL", "DIP", "RATE", "REV", "BAB", "SEAS"], True)]:
    K = yearly_weights(names, sel)
    Wt = sum(SL[n].mul(K[n], axis=0) for n in names)
    for cost in [2, 5]:
        st, net = sx.summary_rf(Wt, c, name=f"{nm}@{cost}bp", cost_bps=cost, start="2002-01-01")
        rows.append(st)
        if cost == 2: nets[nm] = net; KK = K
    if nm == "WF7-slow":
        print("\n#### WF7 active sleeves by year:")
        print((K.groupby(K.index.year).mean() > 0).astype(int).loc[2002:].T.to_string())
print("\n#### results (excess of T-bills, 2002+)")
print(sx.fmt(pd.DataFrame(rows).rename(columns={"CAGRx": "CAGR"})))
net = nets["CORE4-slow"]
spy = c["SPY"].pct_change().loc[net.index]
print(f"CORE4-slow beta {net.cov(spy)/spy.var():.2f}, corr {net.corr(spy):.2f}")
rng = np.random.default_rng(1); x = net.values; n = len(x); out = []
for _ in range(2000):
    idx = []; i = rng.integers(n)
    while len(idx) < n:
        idx.append(i); i = (i + 1) % n if rng.random() > 1 / 21 else rng.integers(n)
    y = x[idx]; out.append(y.mean() / y.std() * np.sqrt(252))
out = np.array(out)
print(f"bootstrap 5/50/95: {np.percentile(out,5):.2f}/{np.percentile(out,50):.2f}/{np.percentile(out,95):.2f}  P(>1) {np.mean(out>1):.2f}")
sr = net.mean() / net.std() * np.sqrt(252)
for N in [20, 100, 700]:
    print(f"DSR N={N}: {sx.dsr(sr, len(net), N, net.skew(), net.kurtosis()+3):.3f}")
print("per-year %:", (net.groupby(net.index.year).sum() * 100).round(1).to_dict())
pd.DataFrame(nets).to_parquet(os.path.join(_H, "slowvol_returns.parquet"))
