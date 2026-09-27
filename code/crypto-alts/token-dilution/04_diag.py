"""Diagnostics for the base dilution book: long vs short leg, per-coin contribution,
young-vs-old interaction (Guo: premium concentrated in the first year), and a truncation
lookahead test (weights recomputed on data cut at T must equal full-sample weights at T)."""
from common import *
d = S.load(); c, m = d["c_alt"], d["mask"]
idmap, W = supply_panels(c)
circ = W["circulatingSupply"].where(W["circulatingSupply"] > 0).reindex(columns=c.columns)
ret = d["ret"]; beta = S.ewm_beta(ret, d["btc"].pct_change(), 60)
mm = m & circ.notna()
sig = -np.log(circ / circ.shift(84)).clip(-1, 2)
w = rl.linear_weights(rl.rank_xs(sig, mm), mm)
L, Sh = w.clip(lower=0), w.clip(upper=0)
for nm, ww in (("long leg (low dilution)", L), ("short leg (high dilution)", Sh)):
    wb = ww.assign(**{"BTC-USD": -(ww * beta).sum(axis=1)})
    net, _ = S.bt(S.tranche(wb, 30), d["close"])
    r = S.row(net, nm); print(nm, {k: round(r[k], 2) for k in ("full", "IS", "OOS", "bear")})
wb = S.tranche(w.assign(**{"BTC-USD": -(w * beta).sum(axis=1)}), 30)
contrib = (wb.shift(1) * d["close"][wb.columns].pct_change()).fillna(0)
for seg, (a, b) in (("IS", S.IS), ("OOS", S.OOS)):
    cs = contrib.loc[a:b].sum().sort_values()
    print(seg, "worst:", cs.head(5).round(3).to_dict()); print(seg, "best:", cs.tail(5).round(3).to_dict())
# average dilution of legs
print("avg 12w dilution, in-universe cross-section median:", (np.log(circ / circ.shift(84)).where(mm).median(axis=1)).groupby(c.index.year).mean().round(3).dropna().to_dict())
# young vs old (age from CMC dateAdded, static)
added = W["dateAdded"]; first_add = pd.to_datetime(added.bfill().iloc[-1])
age = pd.DataFrame({t: (c.index - first_add[t]).days for t in added.columns}, index=c.index).reindex(columns=c.columns)
for nm, sub in (("age<2y", age < 730), ("age>=2y", age >= 730)):
    msk = mm & sub
    ok = msk.sum(axis=1) >= 5
    ww = rl.linear_weights(rl.rank_xs(sig, msk), msk).where(ok, 0.0)
    ww = S.tranche(ww.assign(**{"BTC-USD": -(ww * beta).sum(axis=1)}), 30)
    net, _ = S.bt(ww, d["close"]); r = S.row(net, nm)
    print(nm, "names/day", round(msk.sum(axis=1)[ok].mean(), 1), {k: round(r[k], 2) for k in ("full", "IS", "OOS")})

# truncation lookahead test on the full pipeline
import cmc
snaps = cmc.load_weekly()
def weights_asof(T):
    import study as S2
    cT = c.loc[:T]; mT = m.loc[:T]
    s2 = snaps[snaps["date"] <= T]
    circT = cmc.wide("circulatingSupply", idmap, s2, cT.index)
    circT = circT.where(circT > 0).reindex(columns=cT.columns)
    mmT = mT & circT.notna()
    sg = -np.log(circT / circT.shift(84)).clip(-1, 2)
    wT = rl.linear_weights(rl.rank_xs(sg, mmT), mmT)
    bT = S.ewm_beta(cT.pct_change(), d["btc"].loc[:T].pct_change(), 60)
    return S.tranche(wT.assign(**{"BTC-USD": -(wT * bT).sum(axis=1)}), 30)
for T in ("2019-06-30", "2021-05-15", "2022-11-20", "2024-03-10", "2025-12-31"):
    T = pd.Timestamp(T); wT = weights_asof(T).iloc[-1]; wF = wb.loc[T].reindex(wT.index)
    print("truncation", T.date(), "max |diff| =", float((wT - wF).abs().max()))
