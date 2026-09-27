"""Robustness of the pre-registered dilution book (12-week supply growth, bn, hold 30):
window ensemble, terciles, inverse-vol, hold 60, universe 10/15/30, cost 20/30 bp,
Fama-MacBeth partials vs size / age / beta / 30d return, per-year and per-bear."""
from common import *
d = S.load(); c, m = d["c_alt"], d["mask"]
idmap, W = supply_panels(c)
circ = W["circulatingSupply"].where(W["circulatingSupply"] > 0).reindex(columns=c.columns)
mcap = W["marketCap"].reindex(columns=c.columns)
bab = S.bab_reference(); ret = d["ret"]
beta = S.ewm_beta(ret, d["btc"].pct_change(), 60)
dil = lambda wk: np.log(circ / circ.shift(7 * wk)).clip(-1, 2)


def book(sig, mask, hold=30, scheme="linear", invvol=False):
    mask = mask & circ.notna()
    w = rl.linear_weights(rl.rank_xs(sig, mask), mask) if scheme == "linear" else rl.quantile_weights(sig, mask, 0.3)
    if invvol:
        w = w / ret.rolling(60).std(); w = w.div(w.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    w = w.assign(**{"BTC-USD": -(w * beta).sum(axis=1)})
    return S.tranche(w, hold)


rows, nets = [], {}
def run(w, name, cost=10):
    net, st = S.bt(w, d["close"], cost=cost)
    r = S.row(net, name); r.update(turn=st["Turnover_ann"], rho_bab=net.corr(bab)); rows.append(r); nets[name] = net
    return net

base = run(book(-dil(12), m), "BASE dil12w|h30|bn")
ens = sum(rl.rank_xs(-dil(wk), m & circ.notna()).fillna(0) for wk in (4, 12, 26, 52)).where(m & circ.notna())
run(book(ens, m), "ensemble 4/12/26/52w")
run(book(-dil(12), m, scheme="tercile"), "terciles")
run(book(-dil(12), m, invvol=True), "inverse-vol")
run(book(-dil(12), m, hold=60), "hold 60")
run(book(-dil(8), m), "dil8w"); run(book(-dil(16), m), "dil16w")
for cost in (20, 30):
    run(book(-dil(12), m), f"cost {cost}bp", cost=cost)
for n in (10, 15, 30):
    dn = S.load(n_top=n)
    run(book(-dil(12), dn["mask"]), f"universe {n}")
res = pd.DataFrame(rows).set_index("name")
pd.set_option("display.width", 250)
print(res.round(2).to_string()); res.to_csv("robust_03.csv"); pd.DataFrame(nets).to_parquet("robust_03_nets.parquet")
print("\nyearly BASE:", S.yearly(base).round(2).dropna().to_dict())

# Fama-MacBeth (rank on rank), weekly samples, fwd 30d XS return
fwd = c.shift(-30) / c - 1
mm = m & circ.notna()
sub = c.index[::7]
added = W["dateAdded"]; first_add = pd.to_datetime(added.bfill().iloc[-1])
age = pd.DataFrame({t: (c.index - first_add[t]).days for t in added.columns}, index=c.index).reindex(columns=c.columns)
X = {"dil12w": -dil(12), "logmcap": np.log(mcap), "age": age, "neg_beta": -beta, "ret30": c.pct_change(30)}
Y = fwd.loc[sub].where(mm.loc[sub]).rank(axis=1, pct=True)
Xs = {k: v.loc[sub].where(mm.loc[sub]).rank(axis=1, pct=True) for k, v in X.items()}
B = []
for dt in sub:
    yy = Y.loc[dt]; XX = pd.concat({k: v.loc[dt] for k, v in Xs.items()}, axis=1)
    ok = yy.notna() & XX.notna().all(axis=1)
    if ok.sum() < 10: continue
    A = np.column_stack([np.ones(ok.sum()), XX[ok].values - 0.5])
    b = np.linalg.lstsq(A, yy[ok].values - 0.5, rcond=None)[0]
    B.append(pd.Series(b[1:], index=list(Xs), name=dt))
B = pd.DataFrame(B)
for k, (a, bb) in S.SPLITS.items():
    seg = B.loc[a:bb]
    print(k, {c_: f"{seg[c_].mean():+.3f} (t {rl.newey_west_t(seg[c_].values, 4):+.1f})" for c_ in seg})
