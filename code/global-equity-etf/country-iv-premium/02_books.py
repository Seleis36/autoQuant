"""Re-framing: abnormal country fear (RELIV = log(IV_i/VIX) minus 252d mean, IV lagged 1 session).
(a) horizon 63 sessions; (b) extreme events (|z| > 1.5) only;
(c) books, month-end rebalance, hedged spreads (ETF_i - beta_i SPY), 5 bp ETF / 1 bp SPY:
    XS: long the 2 highest-RELIV / short the 2 lowest (hedged, dollar-neutral across spreads)
    TS: each spread long when its RELIV z > 0 (fear premium), equal risk, 10 % vol target."""
import sys, os
import numpy as np, pandas as pd
from iv_lib import load, hedged, NAMES, SPL
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
import xs

C, R, IV = load()
H, B = hedged(R)
lr = np.log(IV[NAMES].div(IV["SPY"], axis=0))
rel = lr - lr.rolling(252, min_periods=126).mean()
z = rel / lr.rolling(252, min_periods=126).std()
for h in [63]:
    fwd = np.log1p(H).rolling(h).sum().shift(-h); dates = C.index[::h]
    for pn, (a, b) in SPL.items():
        dd = dates[(dates >= a) & (dates <= b)]
        d_ = pd.concat([z.reindex(dd).stack(), fwd.reindex(dd).stack()], axis=1).dropna()
        X = d_.iloc[:, 0] - d_.iloc[:, 0].mean(); Y = d_.iloc[:, 1]
        bt = (X * Y).sum() / (X ** 2).sum(); res = Y - Y.mean() - bt * X
        print(f"RELIV z -> hedged next {h}: {pn} {bt*1e4:6.1f}bp t {bt / np.sqrt((res ** 2).sum() / (len(d_) - 2) / (X ** 2).sum()):5.2f} n {len(d_)}")
fwd21 = np.log1p(H).rolling(21).sum().shift(-21)
for pn, (a, b) in SPL.items():
    zz, yy = z.loc[a:b], fwd21.loc[a:b]
    hi = yy[zz > 1.5].stack().mean() * 1e4; lo = yy[zz < -1.5].stack().mean() * 1e4; al = yy.stack().mean() * 1e4
    print(f"events {pn}: z>1.5 next-21 hedged {hi:6.1f}bp (n {int((zz > 1.5).sum().sum())}), z<-1.5 {lo:6.1f}bp (n {int((zz < -1.5).sum().sum())}), all {al:5.1f}bp")

reb = xs.rebalance_dates(C.index, "M")
ret = R[NAMES + ["SPY"]]
def to_etf(pos):   # spread positions -> ETF + SPY weights at rebalance dates
    w = pos.copy(); w["SPY"] = -(pos * B.reindex(pos.index)[NAMES].fillna(1.0)).sum(axis=1); return w
def report(w_reb, name):
    w = xs.vol_target_book(w_reb, ret, target=0.10, cap=3.0)
    net, gross, turn, We = xs.run(w, C.loc["2011-03-16":, NAMES + ["SPY"]], cost_bps=5.0, spy_cost_bps=1.0, name=name)
    s = {pn: round(net.loc[a:b].mean() / net.loc[a:b].std() * np.sqrt(252), 2) for pn, (a, b) in SPL.items()}
    print(f"{name:40s} {s}  turn/yr {turn.sum() / (len(turn) / 252):.1f}")
    return net
zr = z.reindex(reb)
avail = zr.notna()
nets = {}
nets["XS top2-bottom2 RELIV (long fear)"] = report(to_etf(xs.tercile_weights(zr, avail, k=2)), "XS top2-bottom2 RELIV (long fear)")
nets["XS rank-linear RELIV"] = report(to_etf(xs.rank_weights(zr, avail)), "XS rank-linear RELIV")
vol = H.rolling(126, min_periods=60).std().reindex(reb) * np.sqrt(252)
nets["TS sign(z) equal risk"] = report(to_etf((np.sign(zr) / vol).where(avail, 0.0).fillna(0.0)), "TS sign(z) equal risk")
nets["TS clip(z)/2 equal risk"] = report(to_etf((zr.clip(-2, 2) / 2 / vol).where(avail, 0.0).fillna(0.0)), "TS clip(z)/2 equal risk")
pd.DataFrame(nets).to_parquet(os.path.join(os.path.dirname(os.path.abspath(__file__)), "nets_02.parquet"))
