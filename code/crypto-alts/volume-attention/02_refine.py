"""Refinements of the abnormal-volume book (all beta-neutral with a BTC leg, hold 30):
selection-free ensemble over (k, base), return-orthogonalised volume, up-move-only volume
(Miller: disagreement + optimism), volatility-adjusted volume, quantile vs linear, inverse-vol."""
from common import *

d = S.load(); c, v, m = d["c_alt"], d["v_alt"], d["mask"]
btc = d["btc"]; bab = S.bab_reference(); ret = d["ret"]
beta = S.ewm_beta(ret, btc.pct_change(), 60)
KS, BASES = (7, 14, 30, 60, 90), (180, 365)


def book(sig, hold=30, hedge=True, scheme="linear", invvol=False, mask=m):
    if scheme == "linear":
        w = rl.linear_weights(rl.rank_xs(sig, mask), mask)
    else:
        w = rl.quantile_weights(sig, mask, q=0.3)
    if invvol:
        iv = 1 / ret.rolling(60).std()
        w = w * iv
        w = w.div(w.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    if hedge:
        w = w.assign(**{"BTC-USD": -(w * beta).sum(axis=1)})
    return S.tranche(w, hold)


def ens(fn):
    """Average of cross-sectional ranks over the 10 (k, base) cells."""
    rs = [rl.rank_xs(fn(k, b), m) for k in KS for b in BASES]
    return sum(r.fillna(0) for r in rs).where(m) / len(rs)


def av(k, b):
    return abn_volume(v, k, b)


def av_res(k, b):
    a = S.xs_zscore(av(k, b), m); r = S.xs_zscore(c.pct_change(k), m)
    beta_ = (a * r).sum(axis=1) / (r ** 2).sum(axis=1)
    return a - r.mul(beta_, axis=0)


def av_volres(k, b):
    a = S.xs_zscore(av(k, b), m)
    rv = np.log(ret.abs().rolling(k).mean() / ret.abs().rolling(b, min_periods=b // 3).mean().shift(k))
    r = S.xs_zscore(rv, m)
    beta_ = (a * r).sum(axis=1) / (r ** 2).sum(axis=1)
    return a - r.mul(beta_, axis=0)


def av_up(k, b):
    """abnormal volume on up days only (optimistic disagreement)"""
    vu = v.where(ret > 0, 0.0)
    return np.log(vu.rolling(k).mean() / v.rolling(b, min_periods=b // 3).mean().shift(k))


def av_dn(k, b):
    vd = v.where(ret <= 0, 0.0)
    return np.log(vd.rolling(k).mean() / v.rolling(b, min_periods=b // 3).mean().shift(k))


cands = {
    "ens_av": -ens(av),
    "ens_av_resret": -ens(av_res),
    "ens_av_resvol": -ens(av_volres),
    "ens_av_up": -ens(av_up),
    "ens_av_dn": -ens(av_dn),
    "ctrl_mom30": c.pct_change(30),          # controls, same construction
    "ctrl_rev30": -c.pct_change(30),
    "ctrl_absvol": -np.log(ret.abs().rolling(30).mean() / ret.abs().rolling(180).mean().shift(30)),
}
rows, nets = [], {}
for name, s in cands.items():
    for scheme, invvol in (("linear", False), ("quantile", False), ("linear", True)):
        tag = f"{name}|{scheme}{'|iv' if invvol else ''}"
        net, st = S.bt(book(s, scheme=scheme, invvol=invvol), d["close"])
        r = S.row(net, tag); r.update(turn=st["Turnover_ann"], rho_bab=net.corr(bab)); rows.append(r); nets[tag] = net
# universe-size sensitivity of the plain ensemble
for n in (10, 15, 30):
    dn = S.load(n_top=n)
    s = -sum(rl.rank_xs(abn_volume(dn["v_alt"], k, b), dn["mask"]).fillna(0) for k in KS for b in BASES).where(dn["mask"])
    net, st = S.bt(book(s, mask=dn["mask"]), dn["close"])
    r = S.row(net, f"ens_av|univ{n}"); r.update(turn=st["Turnover_ann"], rho_bab=net.corr(bab)); rows.append(r)
res = pd.DataFrame(rows).set_index("name")
pd.set_option("display.width", 250)
print(res.round(2).to_string())
res.to_csv("refine_02.csv"); pd.DataFrame(nets).to_parquet("refine_02_nets.parquet")
# correlation of the ensemble book with controls
N = pd.DataFrame(nets)
print(N[[c_ for c_ in N if c_.endswith("|linear")]].corr().round(2).to_string())
